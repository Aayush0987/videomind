"""Tests for graphs/analysis_graph.py (§10.1-10.3, §17, Phase 6 DoD).

The full-pipeline test asserts the node path and that a batched, hybrid run
stays cheap: `llm_calls_total <= 9`. Repair-before-resegment is exercised by
forcing invalid segmentation once (repair) and twice (a second
`propose_boundaries`, then terminate).
"""

import pytest
from app.agents import enrichment, segmentation, titling
from app.agents import entities as entities_agent
from app.config import settings
from app.core.llm import LLMConfig
from app.core.wikipedia import WikiSummary
from app.graphs import analysis_graph as g
from app.ingestion.youtube import VideoMetadata
from app.schemas.chapters import ChapterCard, ProposedBoundary, SegmentationOutput, TitlingOutput
from app.schemas.enrichment import BlurbDraft, EnrichmentDrafts, Entity, EntityExtraction
from app.schemas.transcript import SentenceUnit, Transcript

from fakes.fake_llm import FakeLLM

_URL = "https://youtu.be/abcdefghijk"
_VIDEO_ID = "abcdefghijk"
_DURATION = 600.0
_SUMMARY = "S" * 25


class FakeEmbedder:
    name = "fake-embed"
    dim = 8

    async def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [[1.0] + [0.0] * (self.dim - 1) for _ in texts]

    async def embed_query(self, text: str) -> list[float]:
        return [1.0] + [0.0] * (self.dim - 1)


class FakeVectorStore:
    def __init__(self, embedder: object) -> None:
        self.upserted: list = []

    def upsert(self, chunks: list, embeddings: list) -> None:
        self.upserted.append((chunks, embeddings))


def _metadata() -> VideoMetadata:
    return VideoMetadata(
        video_id=_VIDEO_ID,
        title="Test Video",
        channel="A Channel",
        duration=_DURATION,
        thumbnail_url=None,
        published_at=None,
        source="yt_dlp",
    )


def _transcript() -> Transcript:
    units = [
        SentenceUnit(idx=i, start=float(i * 10), end=float(i * 10 + 10), text=f"sentence {i}")
        for i in range(60)
    ]
    return Transcript(
        video_id=_VIDEO_ID, source="captions", language="en", duration=_DURATION, units=units
    )


def _fake(seg_boundaries: list[float], *, needs_enrichment: bool = True) -> FakeLLM:
    fake = FakeLLM()
    fake.responses["SegmentationOutput"] = SegmentationOutput(
        boundaries=[ProposedBoundary(start=b, reason="topic shift") for b in seg_boundaries]
    )
    # A superset of cards; each batch filters to its requested indices.
    fake.responses["TitlingOutput"] = TitlingOutput(
        cards=[
            ChapterCard(idx=i, title=f"Topic {i}", summary=_SUMMARY, key_points=["a", "b"])
            for i in range(8)
        ]
    )
    fake.responses["EntityExtraction"] = EntityExtraction(
        entities=[
            Entity(
                name="Backprop",
                kind="concept",
                first_mention=10.0,
                needs_enrichment=needs_enrichment,
            )
        ]
    )
    fake.responses["EnrichmentDrafts"] = EnrichmentDrafts(
        notes=[BlurbDraft(entity="Backprop", blurb="The chain rule for gradients.")]
    )
    return fake


async def _fake_summary(name: str) -> WikiSummary:
    return WikiSummary(
        title=name, extract=f"About {name}.", url=f"https://en.wikipedia.org/wiki/{name}"
    )


def _wire(
    monkeypatch: pytest.MonkeyPatch, fake: FakeLLM, tmp_path, *, mlflow_enabled: bool
) -> list[float]:
    """Patch all boundaries (network, embedding, vector store, LLM) and return a
    live list that captures the progress reported to jobs.update, in order."""
    monkeypatch.setattr(settings, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "MLFLOW_ENABLED", mlflow_enabled)

    monkeypatch.setattr(g, "fetch_metadata", lambda vid: _metadata())
    monkeypatch.setattr(g, "acquire_transcript", lambda vid, url, dur: _transcript())
    monkeypatch.setattr(g, "get_embedder", lambda: FakeEmbedder())
    monkeypatch.setattr(g, "VectorStore", FakeVectorStore)

    for mod in (segmentation, titling, entities_agent, enrichment):
        monkeypatch.setattr(mod, "generate_structured", fake.generate_structured)
    monkeypatch.setattr(enrichment, "fetch_summary", _fake_summary)

    progress_seq: list[float] = []
    original_update = g.jobs.update

    def spy(job_id: str, **fields: object):
        job = original_update(job_id, **fields)
        if "progress" in fields:
            progress_seq.append(job.progress)
        return job

    monkeypatch.setattr(g.jobs, "update", spy)
    return progress_seq


# ---------------------------------------------------------------------------
# The headline full-pipeline assertion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_pipeline_node_path_and_llm_budget(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    fake = _fake([200.0, 400.0])
    progress = _wire(monkeypatch, fake, tmp_path, mlflow_enabled=False)

    async with g.tracing.run_context("videomind-analysis", {}) as metrics:
        result = await g._graph().ainvoke(
            {"job_id": "job1", "url": _URL, "llm": LLMConfig(), "segmentation_attempts": 0},
            config={"recursion_limit": 50},
        )

    assert metrics.node_path == [
        "resolve_source",
        "fetch_transcript",
        "normalize_transcript",
        "propose_boundaries",
        "build_chapters",
        "verify_chapters",
        "title_and_summarize",
        "extract_entities",
        "enrich",
        "index_transcript",
        "persist",
    ]
    # propose(1) + title(1) + entities(1) + enrich condense(1) = 4.
    assert metrics.llm_calls_total == 4
    assert metrics.llm_calls_total <= 9

    assert result["verification"].valid
    assert len(result["chapters"]) == 3
    assert all(ch.title for ch in result["chapters"])
    assert len(result["enrichment"]) == 1

    # Progress is monotonically non-decreasing and terminates at 1.0.
    assert progress == sorted(progress)
    assert progress[-1] == 1.0
    assert g.jobs.get("job1").status == "ready"


# ---------------------------------------------------------------------------
# Failure policy: repair-before-resegment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_segmentation_triggers_repair(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    # A boundary at 580 yields a 20s final chapter [580,600] (R7); deterministic
    # repair merges it into its neighbour. (Boundaries closer than
    # MIN_CHAPTER_SECONDS are already coalesced inside the segmentation agent,
    # so the defect has to come from a short chapter against the video end.)
    fake = _fake([200.0, 400.0, 580.0])
    _wire(monkeypatch, fake, tmp_path, mlflow_enabled=False)

    async with g.tracing.run_context("videomind-analysis", {}) as metrics:
        result = await g._graph().ainvoke(
            {"job_id": "job2", "url": _URL, "llm": LLMConfig(), "segmentation_attempts": 0},
            config={"recursion_limit": 50},
        )

    assert "repair_chapters" in metrics.node_path
    assert metrics.node_path.count("propose_boundaries") == 1
    assert result["verification"].valid
    assert result["verification"].repaired
    assert result["segmentation_attempts"] == 1


@pytest.mark.asyncio
async def test_twice_invalid_resegments_then_terminates(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    # Empty boundaries → a single chapter → R9 (too few), unrepairable → resegment.
    fake = _fake([], needs_enrichment=False)
    _wire(monkeypatch, fake, tmp_path, mlflow_enabled=False)

    async with g.tracing.run_context("videomind-analysis", {}) as metrics:
        result = await g._graph().ainvoke(
            {"job_id": "job3", "url": _URL, "llm": LLMConfig(), "segmentation_attempts": 0},
            config={"recursion_limit": 50},
        )

    assert metrics.node_path.count("propose_boundaries") == 2
    assert metrics.node_path[-1] == "persist"  # give_up still ships best-effort
    assert result["segmentation_attempts"] == 2
    assert metrics.llm_calls_total <= 9


@pytest.mark.asyncio
async def test_no_enrichment_skips_enrich_node(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    fake = _fake([200.0, 400.0], needs_enrichment=False)
    _wire(monkeypatch, fake, tmp_path, mlflow_enabled=False)

    async with g.tracing.run_context("videomind-analysis", {}) as metrics:
        result = await g._graph().ainvoke(
            {"job_id": "job4", "url": _URL, "llm": LLMConfig(), "segmentation_attempts": 0},
            config={"recursion_limit": 50},
        )

    assert "enrich" not in metrics.node_path
    assert "index_transcript" in metrics.node_path
    assert result.get("enrichment") in (None, [])
    # propose(1) + title(1) + entities(1) = 3, no enrich call.
    assert metrics.llm_calls_total == 3


# ---------------------------------------------------------------------------
# Observability: MLflow enabled writes a run; disabled is a clean no-op
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mlflow_run_written_when_enabled(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    tracking_uri = f"file:{tmp_path}/mlruns"
    monkeypatch.setattr(settings, "MLFLOW_TRACKING_URI", tracking_uri)
    fake = _fake([200.0, 400.0])
    _wire(monkeypatch, fake, tmp_path, mlflow_enabled=True)

    result = await g.run_analysis("job5", _URL, LLMConfig())
    assert result["verification"].valid

    import mlflow

    mlflow.set_tracking_uri(tracking_uri)
    runs = mlflow.search_runs(experiment_names=["videomind-analysis"])
    assert len(runs) >= 1
    assert runs.iloc[0]["metrics.llm_calls_total"] == 4.0


@pytest.mark.asyncio
async def test_mlflow_cleanly_skipped_when_disabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    tracking_uri = f"file:{tmp_path}/mlruns"
    monkeypatch.setattr(settings, "MLFLOW_TRACKING_URI", tracking_uri)
    fake = _fake([200.0, 400.0])
    _wire(monkeypatch, fake, tmp_path, mlflow_enabled=False)

    result = await g.run_analysis("job6", _URL, LLMConfig())
    assert result["verification"].valid
    assert g.tracing.current_metrics() is None  # context cleaned up
    # Disabled means no run dir was ever created under the tracking backend.
    assert not (tmp_path / "mlruns").exists()
