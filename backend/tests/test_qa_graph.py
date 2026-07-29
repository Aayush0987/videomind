"""Tests for graphs/qa_graph.py (§13, Phase 7 DoD).

The four required scenarios:

1. single-pass — a sufficient first retrieval flows straight to a cited answer.
2. retry-with-different-strategy — an insufficient first pass escalates the
   planner from `direct` (top_k 8) to `decompose` (top_k 12), and the retry is a
   genuinely different query, not a repeat.
3. insufficient — two insufficient passes end at the honest-failure node with no
   answer LLM call.
4. hallucinated-chunk-id dropped — a citation naming a chunk that was never
   retrieved is dropped and its marker stripped before the user sees it.
"""

from collections import defaultdict, deque

import pytest
from app.config import (
    INSUFFICIENT_MESSAGE,
    LOW_CONFIDENCE_HEDGE,
    settings,
)
from app.core import tracing
from app.core.llm import LLMConfig
from app.graphs import qa_graph as qa
from app.schemas.qa import AnswerDraft, ChunkGrade, CitationRef, GradingOutput, QueryPlan

from fakes.fake_llm import FakeLLM  # noqa: F401 -- kept importable for parity

_VIDEO_ID = "abcdefghijk"


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class ScriptedLLM:
    """Returns canned structured outputs by schema name, in order. The last
    queued response for a schema sticks, so a single plan can cover every pass
    while grades vary pass to pass."""

    def __init__(self) -> None:
        self._queues: dict[str, deque] = defaultdict(deque)
        self.call_log: list[str] = []

    def script(self, *responses: object) -> None:
        for r in responses:
            self._queues[type(r).__name__].append(r)

    async def generate_structured(self, prompt, cfg, schema, *, system=None, repair_attempts=1):
        self.call_log.append(schema.__name__)
        tracing.record_llm_call()
        q = self._queues[schema.__name__]
        if not q:
            raise KeyError(f"ScriptedLLM has no canned {schema.__name__} response.")
        return q.popleft() if len(q) > 1 else q[0]


class FakeEmbedder:
    name = "fake-embed"
    dim = 8

    async def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [[1.0] + [0.0] * (self.dim - 1) for _ in texts]

    async def embed_query(self, text: str) -> list[float]:
        return [1.0] + [0.0] * (self.dim - 1)


class FakeVectorStore:
    def __init__(self, embedder: object) -> None:
        self.embedder = embedder


def _chunk(cid: str, start: float, *, title: str = "Topic A", text: str = "some content") -> dict:
    return {
        "chunk_id": cid,
        "distance": 0.1,
        "metadata": {
            "video_id": _VIDEO_ID,
            "chapter_id": "ch00",
            "chapter_idx": 0,
            "chapter_title": title,
            "start": start,
            "end": start + 10.0,
            "unit_start_idx": 0,
            "unit_end_idx": 1,
        },
        "document": f"{title}\n{text}",
    }


def _wire(monkeypatch, llm: ScriptedLLM, retrieve_sets: list[list[dict]]) -> list[int]:
    """Patch every boundary and return a live list capturing the `top_k` used on
    each retrieval call, in order — the escalation ladder is observable there."""
    from app.agents import answerer, grader, query_planner

    monkeypatch.setattr(settings, "MLFLOW_ENABLED", False)
    for mod in (query_planner, grader, answerer):
        monkeypatch.setattr(mod, "generate_structured", llm.generate_structured)
    monkeypatch.setattr(qa, "get_embedder", lambda: FakeEmbedder())
    monkeypatch.setattr(qa, "VectorStore", FakeVectorStore)

    top_ks: list[int] = []
    sets = deque(retrieve_sets)

    def fake_retrieve(store, query_embedding, video_id, top_k):
        top_ks.append(top_k)
        return sets.popleft() if len(sets) > 1 else (sets[0] if sets else [])

    monkeypatch.setattr(qa, "retrieve", fake_retrieve)
    return top_ks


async def _run(state: dict):
    async with tracing.run_context("videomind-qa", {}) as metrics:
        result = await qa._graph().ainvoke(state, config={"recursion_limit": 50})
    return result, metrics


def _plan() -> QueryPlan:
    # strategy/top_k are overwritten deterministically by the escalation ladder.
    return QueryPlan(rewritten_query="what is X", sub_queries=[], strategy="direct", top_k=8)


def _base_state() -> dict:
    return {
        "video_id": _VIDEO_ID,
        "question": "What is X?",
        "llm": LLMConfig(),
        "history": [],
        "retrieval_attempts": 0,
    }


# ---------------------------------------------------------------------------
# 1. Single-pass
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_pass_sufficient_answers_with_citations(monkeypatch) -> None:
    llm = ScriptedLLM()
    llm.script(
        _plan(),
        GradingOutput(
            grades=[
                ChunkGrade(chunk_id="v:c0000", relevant=True, score=0.9),
                ChunkGrade(chunk_id="v:c0001", relevant=True, score=0.85),
            ],
            sufficient=True,
        ),
        AnswerDraft(
            answer="X is the first thing [[c0]] and also the second [[c1]].",
            citations=[
                CitationRef(chunk_id="v:c0000", quote="first thing"),
                CitationRef(chunk_id="v:c0001", quote="second"),
            ],
            confidence="high",
        ),
    )
    chunks = [_chunk("v:c0000", 10.0), _chunk("v:c0001", 30.0, title="Topic B")]
    _wire(monkeypatch, llm, [chunks])

    result, metrics = await _run(_base_state())

    assert metrics.node_path == [
        "plan_query",
        "retrieve",
        "grade_chunks",
        "answer",
        "validate_citations",
    ]
    assert result["insufficient"] is False
    assert len(result["citations"]) == 2
    assert [c.marker for c in result["citations"]] == ["c0", "c1"]
    # Timestamps are server-resolved from chunk metadata, never the model.
    assert result["citations"][0].start == 10.0
    assert result["citations"][1].chapter_title == "Topic B"
    assert "[[c0]]" in result["answer"] and "[[c1]]" in result["answer"]


# ---------------------------------------------------------------------------
# 2. Retry with a different strategy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_escalates_strategy(monkeypatch) -> None:
    llm = ScriptedLLM()
    llm.script(_plan())
    llm.script(
        # pass 1 — insufficient, nothing clears the relevance threshold
        GradingOutput(
            grades=[ChunkGrade(chunk_id="v:c0000", relevant=False, score=0.4)],
            sufficient=False,
            missing_information="need the definition of X",
        ),
        # pass 2 — sufficient after decomposition
        GradingOutput(
            grades=[
                ChunkGrade(chunk_id="v:c0000", relevant=True, score=0.9),
                ChunkGrade(chunk_id="v:c0001", relevant=True, score=0.8),
                ChunkGrade(chunk_id="v:c0002", relevant=True, score=0.75),
            ],
            sufficient=True,
        ),
    )
    llm.script(
        AnswerDraft(
            answer="X means this [[c0]] and that [[c1]].",
            citations=[
                CitationRef(chunk_id="v:c0000", quote="this"),
                CitationRef(chunk_id="v:c0001", quote="that"),
            ],
            confidence="high",
        )
    )
    pass1 = [_chunk("v:c0000", 10.0)]
    pass2 = [_chunk("v:c0000", 10.0), _chunk("v:c0001", 30.0), _chunk("v:c0002", 50.0)]
    top_ks = _wire(monkeypatch, llm, [pass1, pass2])

    result, metrics = await _run(_base_state())

    assert metrics.node_path.count("plan_query") == 2
    # Escalation ladder (§13.3): direct→top_k 8, then decompose→top_k 12.
    assert top_ks == [8, 12]
    assert metrics.node_path[-1] == "validate_citations"
    assert result["insufficient"] is False
    assert len(result["citations"]) == 2


# ---------------------------------------------------------------------------
# 3. Insufficient — honest failure, no answer LLM call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_two_insufficient_passes_end_at_insufficient_node(monkeypatch) -> None:
    llm = ScriptedLLM()
    llm.script(_plan())
    llm.script(
        GradingOutput(
            grades=[ChunkGrade(chunk_id="v:c0000", relevant=False, score=0.3)],
            sufficient=False,
            missing_information="not covered",
        )
    )
    chunks = [_chunk("v:c0000", 10.0, title="Topic A")]
    _wire(monkeypatch, llm, [chunks])

    result, metrics = await _run(_base_state())

    assert metrics.node_path.count("plan_query") == 2  # one retry, then give up
    assert metrics.node_path[-1] == "insufficient"
    assert "answer" not in metrics.node_path
    assert "AnswerDraft" not in llm.call_log  # the answer agent never ran
    assert result["insufficient"] is True
    assert result["answer"].startswith(INSUFFICIENT_MESSAGE)
    assert "Topic A" in result["answer"]  # closest topic surfaced as a suggestion
    assert result["citations"] == []


# ---------------------------------------------------------------------------
# 4. Hallucinated chunk id dropped
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hallucinated_chunk_id_is_dropped(monkeypatch) -> None:
    llm = ScriptedLLM()
    llm.script(
        _plan(),
        GradingOutput(
            grades=[
                ChunkGrade(chunk_id="v:c0000", relevant=True, score=0.9),
                ChunkGrade(chunk_id="v:c0001", relevant=True, score=0.8),
            ],
            sufficient=True,
        ),
        AnswerDraft(
            answer="A real grounded claim [[c0]] and a fabricated one [[c1]].",
            citations=[
                CitationRef(chunk_id="v:c0000", quote="real grounded claim"),
                CitationRef(chunk_id="v:c9999", quote="fabricated, never retrieved"),
            ],
            confidence="high",
        ),
    )
    chunks = [_chunk("v:c0000", 10.0), _chunk("v:c0001", 30.0)]
    _wire(monkeypatch, llm, [chunks])

    result, metrics = await _run(_base_state())

    assert len(result["citations"]) == 1
    assert result["citations"][0].chunk_id == "v:c0000"
    assert result["citations"][0].marker == "c0"
    assert "v:c9999" not in {c.chunk_id for c in result["citations"]}
    # The dangling marker for the dropped citation is stripped from the text.
    assert "[[c1]]" not in result["answer"]
    assert "[[c0]]" in result["answer"]
    assert metrics.dropped_citations == 1


@pytest.mark.asyncio
async def test_zero_surviving_citations_hedges_and_downgrades(monkeypatch) -> None:
    llm = ScriptedLLM()
    llm.script(
        _plan(),
        GradingOutput(
            grades=[
                ChunkGrade(chunk_id="v:c0000", relevant=True, score=0.9),
                ChunkGrade(chunk_id="v:c0001", relevant=True, score=0.8),
            ],
            sufficient=True,
        ),
        AnswerDraft(
            answer="Everything here is ungrounded [[c0]].",
            citations=[CitationRef(chunk_id="v:c9999", quote="ungrounded")],
            confidence="high",
        ),
    )
    chunks = [_chunk("v:c0000", 10.0), _chunk("v:c0001", 30.0)]
    _wire(monkeypatch, llm, [chunks])

    result, metrics = await _run(_base_state())

    assert result["citations"] == []
    assert result["answer"].startswith(LOW_CONFIDENCE_HEDGE)
    assert "[[c0]]" not in result["answer"]
    assert metrics.dropped_citations == 1


@pytest.mark.asyncio
async def test_run_qa_wrapper_returns_answer(monkeypatch) -> None:
    llm = ScriptedLLM()
    llm.script(
        _plan(),
        GradingOutput(
            grades=[
                ChunkGrade(chunk_id="v:c0000", relevant=True, score=0.9),
                ChunkGrade(chunk_id="v:c0001", relevant=True, score=0.85),
            ],
            sufficient=True,
        ),
        AnswerDraft(
            answer="X is defined here [[c0]].",
            citations=[CitationRef(chunk_id="v:c0000", quote="defined here")],
            confidence="medium",
        ),
    )
    chunks = [_chunk("v:c0000", 10.0), _chunk("v:c0001", 30.0)]
    _wire(monkeypatch, llm, [chunks])

    result = await qa.run_qa(_VIDEO_ID, "What is X?", LLMConfig())

    assert result["insufficient"] is False
    assert len(result["citations"]) == 1
    assert "[[c0]]" in result["answer"]
