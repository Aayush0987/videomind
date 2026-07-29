"""Tests for the HTTP API surface (§14, Phase 8 DoD).

`TestClient` happy paths plus the required edges: a cache hit returns 200 with
zero background scheduling, malformed URLs 400, unknown ids 404, an oversized
body 413, and the ask endpoint returns a cited answer with its agent trace.
Every response carries an `X-Request-ID` (§14.3). No test makes a real network
or LLM call — the scheduler and the Q&A graph are faked at the boundary.
"""

from collections.abc import Iterator

import pytest
from app import config
from app.api import routes_qa, routes_videos
from app.core import db, embedder
from app.core.errors import LLMAuthError
from app.core.llm import LLMConfig
from app.schemas.chapters import Chapter
from app.schemas.enrichment import EnrichmentNote
from app.schemas.qa import AnswerDraft, Citation, CitationRef
from app.schemas.transcript import TranscriptCue
from fastapi.testclient import TestClient

_URL = "https://youtu.be/dQw4w9WgXcQ"
_VIDEO_ID = "dQw4w9WgXcQ"


class FakeEmbedder:
    name = "gemini-embedding-001"
    dim = 768

    async def embed_query(self, text: str) -> list[float]:
        return [1.0] + [0.0] * (self.dim - 1)  # unit norm — passes the startup probe

    async def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [[1.0] + [0.0] * (self.dim - 1) for _ in texts]


class FakeVectorStore:
    def __init__(self, embedder: object) -> None:
        self.deleted: list[str] = []

    def delete_video(self, video_id: str) -> None:
        self.deleted.append(video_id)


@pytest.fixture
def scheduled() -> list[tuple[str, str]]:
    return []


@pytest.fixture
def client(tmp_path, monkeypatch: pytest.MonkeyPatch, scheduled: list) -> Iterator[TestClient]:
    monkeypatch.setattr(config.settings, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(embedder, "_embedder", FakeEmbedder())
    # Never fire a real background analysis; just record what would have run.
    monkeypatch.setattr(
        routes_videos.jobs, "schedule", lambda job_id, url, llm: scheduled.append((job_id, url))
    )
    monkeypatch.setattr(routes_videos, "VectorStore", FakeVectorStore)
    import app.main

    with TestClient(app.main.app) as test_client:
        # Lifespan ran the embedding probe against FakeEmbedder (unit-norm-safe).
        yield test_client


def _seed_video(*, ready: bool = True) -> None:
    conn = db.get_connection()
    db.init_schema(conn)
    db.upsert_video(
        conn,
        video_id=_VIDEO_ID,
        url=_URL,
        title="A Title",
        channel="A Channel",
        duration=1834.0,
        thumbnail_url="https://img/x.jpg",
        published_at=None,
        transcript_source="captions",
        language="en",
    )
    db.upsert_chapters(
        conn,
        _VIDEO_ID,
        [
            Chapter(
                chapter_id=f"{_VIDEO_ID}:ch00",
                idx=0,
                start=0.0,
                end=213.5,
                title="Intro",
                summary="A summary long enough.",
                key_points=["a", "b"],
            )
        ],
    )
    db.upsert_enrichments(
        conn,
        _VIDEO_ID,
        [
            EnrichmentNote(
                entity="LangGraph",
                kind="technology",
                blurb="A graph runtime.",
                source_url="https://example/langgraph",
                first_mention=412.0,
            )
        ],
    )
    db.upsert_transcript(
        conn,
        _VIDEO_ID,
        [
            TranscriptCue(start=0.0, end=8.2, text="hello"),
            TranscriptCue(start=8.2, end=16.0, text="world"),
        ],
    )


# --- POST /api/videos ----------------------------------------------------


def test_analyze_cache_hit_returns_200_and_does_not_schedule(client, scheduled) -> None:
    _seed_video()
    resp = client.post("/api/videos", json={"url": _URL})
    assert resp.status_code == 200
    assert resp.json() == {"cached": True, "video_id": _VIDEO_ID, "job_id": None}
    assert scheduled == []  # zero background work on a hit
    assert "X-Request-ID" in resp.headers


def test_analyze_miss_returns_202_and_schedules(client, scheduled) -> None:
    resp = client.post("/api/videos", json={"url": _URL})
    assert resp.status_code == 202
    body = resp.json()
    assert body["cached"] is False
    assert body["video_id"] == _VIDEO_ID
    assert body["job_id"]
    assert scheduled == [(body["job_id"], _URL)]


def test_analyze_force_refresh_reruns_even_when_cached(client, scheduled) -> None:
    _seed_video()
    resp = client.post("/api/videos", json={"url": _URL, "force_refresh": True})
    assert resp.status_code == 202
    assert resp.json()["cached"] is False
    assert len(scheduled) == 1


def test_analyze_malformed_url_returns_400(client) -> None:
    resp = client.post("/api/videos", json={"url": "not-a-youtube-url"})
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "invalid_url"


# --- GET /api/videos/{id} -----------------------------------------------


def test_get_video_returns_full_analysis(client) -> None:
    _seed_video()
    resp = client.get(f"/api/videos/{_VIDEO_ID}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["video_id"] == _VIDEO_ID
    assert body["title"] == "A Title"
    assert len(body["chapters"]) == 1
    assert body["chapters"][0]["chapter_id"] == f"{_VIDEO_ID}:ch00"
    assert body["enrichments"][0]["entity"] == "LangGraph"
    assert body["verification"] == {"valid": True, "repaired": False, "issues": []}


def test_get_video_unknown_returns_404(client) -> None:
    resp = client.get("/api/videos/nope")
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "video_not_found"


def test_get_video_embedding_mismatch_returns_409(client, monkeypatch) -> None:
    _seed_video()
    monkeypatch.setattr(config.settings, "EMBEDDING_MODEL", "some-other-model")
    resp = client.get(f"/api/videos/{_VIDEO_ID}")
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "embedding_mismatch"


# --- GET /api/videos/{id}/transcript ------------------------------------


def test_get_transcript_returns_units(client) -> None:
    _seed_video()
    resp = client.get(f"/api/videos/{_VIDEO_ID}/transcript")
    assert resp.status_code == 200
    units = resp.json()["units"]
    assert [u["idx"] for u in units] == [0, 1]
    assert units[0]["text"] == "hello"


def test_get_transcript_unknown_returns_404(client) -> None:
    resp = client.get("/api/videos/nope/transcript")
    assert resp.status_code == 404


# --- DELETE /api/videos/{id} --------------------------------------------


def test_delete_video_returns_204_then_404(client) -> None:
    _seed_video()
    resp = client.delete(f"/api/videos/{_VIDEO_ID}")
    assert resp.status_code == 204
    assert client.get(f"/api/videos/{_VIDEO_ID}").status_code == 404


def test_delete_unknown_returns_404(client) -> None:
    assert client.delete("/api/videos/nope").status_code == 404


# --- GET /api/jobs/{id} --------------------------------------------------


def test_get_job_returns_status_and_stage_label(client) -> None:
    from app.services import jobs

    jobs.update(
        "job-1",
        video_id=_VIDEO_ID,
        status="running",
        stage="title_and_summarize",
        progress=0.65,
        retries={"segmentation": 1},
    )
    resp = client.get("/api/jobs/job-1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "running"
    assert body["stage"] == "title_and_summarize"
    assert body["stage_label"] == "Writing chapter summaries"
    assert body["progress"] == 0.65
    assert body["retries"] == {"segmentation": 1}


def test_get_job_unknown_returns_404(client) -> None:
    resp = client.get("/api/jobs/nope")
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "job_not_found"


# --- POST /api/videos/{id}/ask ------------------------------------------


def test_ask_returns_answer_citations_and_trace(client, monkeypatch) -> None:
    _seed_video()

    async def fake_run_qa(video_id, question, llm, *, history=None):
        return {
            "answer": "They dropped it [[c0]].",
            "citations": [
                Citation(
                    marker="c0",
                    chunk_id=f"{_VIDEO_ID}:c0012",
                    start=271.0,
                    end=302.5,
                    quote="…",
                    chapter_title="Cost of the naive approach",
                )
            ],
            "draft": AnswerDraft(
                answer="They dropped it [[c0]].",
                citations=[CitationRef(chunk_id=f"{_VIDEO_ID}:c0012", quote="…")],
                confidence="high",
            ),
            "trace": {
                "strategy": "decompose",
                "retrieval_attempts": 2,
                "chunks_retrieved": 12,
                "chunks_kept": 5,
                "dropped_citations": 1,
                "nodes": ["plan_query", "retrieve", "grade_chunks", "answer", "validate_citations"],
                "latency_ms": 4120,
            },
        }

    monkeypatch.setattr(routes_qa, "run_qa", fake_run_qa)
    resp = client.post(f"/api/videos/{_VIDEO_ID}/ask", json={"question": "Why?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == "They dropped it [[c0]]."
    assert body["confidence"] == "high"
    assert body["citations"][0]["chunk_id"] == f"{_VIDEO_ID}:c0012"
    assert body["citations"][0]["start"] == 271.0
    assert body["trace"]["strategy"] == "decompose"
    assert body["trace"]["chunks_kept"] == 5


def test_ask_unknown_video_returns_404(client) -> None:
    resp = client.post("/api/videos/nope/ask", json={"question": "Why?"})
    assert resp.status_code == 404


def test_ask_question_too_long_returns_422(client) -> None:
    _seed_video()
    resp = client.post(f"/api/videos/{_VIDEO_ID}/ask", json={"question": "x" * 1001})
    assert resp.status_code == 422  # pydantic validation on the request model


# --- POST /api/llm/ping --------------------------------------------------


def test_llm_ping_ok(client, monkeypatch) -> None:
    async def fake_generate(prompt, cfg, *, system=None):
        return "pong"

    monkeypatch.setattr(routes_qa, "generate", fake_generate)
    resp = client.post("/api/llm/ping", json={})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "error": None}


def test_llm_ping_reports_auth_error(client, monkeypatch) -> None:
    async def fake_generate(prompt, cfg, *, system=None):
        raise LLMAuthError("Check your API key / model name in Settings.")

    monkeypatch.setattr(routes_qa, "generate", fake_generate)
    resp = client.post("/api/llm/ping", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert "API key" in body["error"]


# --- GET /api/health -----------------------------------------------------


def test_health_reports_embedder_and_collection(client) -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["embedder"] == "gemini-embedding-001"
    assert body["embedding_dim"] == 768
    assert body["collection"] == "chunks__gemini_embedding_001_768"


# --- Cross-cutting -------------------------------------------------------


def test_oversized_body_returns_413(client) -> None:
    resp = client.post("/api/videos", json={"url": "x" * 40_000})
    assert resp.status_code == 413


def test_every_response_carries_request_id(client) -> None:
    resp = client.get("/api/health")
    assert resp.headers.get("X-Request-ID")


def test_no_llm_config_uses_server_defaults() -> None:
    from app.api.deps import resolve_llm_config

    cfg = resolve_llm_config(None)
    assert isinstance(cfg, LLMConfig)
    assert cfg.provider == config.settings.DEFAULT_LLM_PROVIDER
    assert cfg.model == config.settings.DEFAULT_LLM_MODEL
