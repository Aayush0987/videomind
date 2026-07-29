"""LangGraph Q&A pipeline: query planning, retrieval, grading, and answering
with citation escalation (§13).

The corrective-RAG loop is real, not cosmetic: when the grader marks a retrieval
insufficient the planner escalates strategy (§13.3), so a retry genuinely
changes the query rather than repeating it. The grader (§13.2) is the precision
layer that gates the answer; `validate_citations` (§13.5) is a deterministic
guardrail that drops any citation the model invented before the user sees it.
"""

import re

from langgraph.graph import END, START, StateGraph

from app.agents import answerer, grader, query_planner
from app.config import (
    INSUFFICIENT_MESSAGE,
    INSUFFICIENT_SUGGESTION_PREFIX,
    LOW_CONFIDENCE_HEDGE,
    MAX_RETRIEVAL_ATTEMPTS,
    MIN_RELEVANT_CHUNKS,
    RELEVANCE_THRESHOLD,
)
from app.core import tracing
from app.core.embedder import get_embedder
from app.core.llm import LLMConfig
from app.core.vectorstore import VectorStore, retrieve
from app.graphs.state import QAState
from app.schemas.qa import Citation

_MARKER_RE = re.compile(r"\[\[c(\d+)\]\]")


def _kept_chunk_ids(state: QAState) -> set[str]:
    grades = state["grades"]
    return {g.chunk_id for g in grades.grades if g.relevant and g.score >= RELEVANCE_THRESHOLD}


# --- Nodes ---------------------------------------------------------------


@tracing.traced("plan_query")
async def plan_query(state: QAState) -> dict:
    attempt = state.get("retrieval_attempts", 0)
    grades = state.get("grades")
    plan = await query_planner.plan_query(
        state["question"],
        state.get("history", []),
        attempt,
        state["llm"],
        missing_information=grades.missing_information if grades is not None else None,
    )
    return {"plan": plan, "retrieval_attempts": attempt + 1}


@tracing.traced("retrieve")
async def retrieve_node(state: QAState) -> dict:
    plan = state["plan"]
    embedder = get_embedder()
    store = VectorStore(embedder)
    queries = (
        plan.sub_queries
        if plan.strategy == "decompose" and plan.sub_queries
        else [plan.rewritten_query]
    )
    merged: dict[str, dict] = {}
    for query in queries:
        query_vec = await embedder.embed_query(query)
        for item in retrieve(store, query_vec, state["video_id"], plan.top_k):
            cid = item["chunk_id"]
            if cid not in merged or item["distance"] < merged[cid]["distance"]:
                merged[cid] = item
    chunks = sorted(merged.values(), key=lambda x: x["metadata"]["start"])
    return {"chunks": chunks}


@tracing.traced("grade_chunks")
async def grade_chunks(state: QAState) -> dict:
    grades = await grader.grade_chunks(state["question"], state["chunks"], state["llm"])
    return {"grades": grades}


@tracing.traced("answer")
async def answer_node(state: QAState) -> dict:
    keep_ids = _kept_chunk_ids(state)
    kept = [c for c in state["chunks"] if c["chunk_id"] in keep_ids]
    draft = await answerer.answer(state["question"], state.get("history", []), kept, state["llm"])
    return {"draft": draft}


@tracing.traced("validate_citations")
async def validate_citations(state: QAState) -> dict:
    """Deterministic guardrail (§13.5): drop invented citations, resolve
    timestamps from chunk metadata, renumber markers, and hedge when nothing
    survives."""
    draft = state["draft"]
    chunks_by_id = {c["chunk_id"]: c for c in state["chunks"]}

    # 1-3. Keep only citations whose chunk_id was actually retrieved; resolve
    # their real time ranges and renumber contiguously.
    citations: list[Citation] = []
    old_to_new: dict[int, str] = {}
    dropped = 0
    for old_idx, ref in enumerate(draft.citations):
        chunk = chunks_by_id.get(ref.chunk_id)
        if chunk is None:  # unknown id → hallucinated → drop it
            dropped += 1
            continue
        meta = chunk["metadata"]
        new_marker = f"c{len(citations)}"
        old_to_new[old_idx] = new_marker
        citations.append(
            Citation(
                marker=new_marker,
                chunk_id=ref.chunk_id,
                start=meta["start"],
                end=meta["end"],
                quote=ref.quote,
                chapter_title=meta["chapter_title"],
            )
        )

    # Rewrite markers: survivors get their new number; dropped citations and
    # dangling markers (§13.5.4) are stripped.
    def _sub(match: re.Match) -> str:
        old_n = int(match.group(1))
        new = old_to_new.get(old_n)
        return f"[[{new}]]" if new is not None else ""

    text = _MARKER_RE.sub(_sub, draft.answer)
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text).strip()

    # 5. Nothing survived → downgrade confidence and hedge.
    if not citations and draft.confidence != "low":
        text = f"{LOW_CONFIDENCE_HEDGE} {text}"

    # 6. Record the drop count on the trace — a prompt-quality signal.
    metrics = tracing.current_metrics()
    if metrics is not None:
        metrics.dropped_citations += dropped

    return {"answer": text, "citations": citations, "insufficient": False}


@tracing.traced("insufficient")
async def insufficient_node(state: QAState) -> dict:
    """No LLM call (§13.6). Fixed honest-failure message plus the closest chapter
    titles drawn from whatever was retrieved."""
    titles: list[str] = []
    for chunk in state.get("chunks", []):
        title = chunk["metadata"]["chapter_title"]
        if title and title not in titles:
            titles.append(title)
        if len(titles) == 3:
            break
    if titles:
        answer = f"{INSUFFICIENT_MESSAGE} {INSUFFICIENT_SUGGESTION_PREFIX} {', '.join(titles)}."
    else:
        answer = INSUFFICIENT_MESSAGE
    return {"answer": answer, "citations": [], "insufficient": True}


# --- Routers -------------------------------------------------------------


def route_after_grading(state: QAState) -> str:
    grades = state["grades"]
    kept = [g for g in grades.grades if g.relevant and g.score >= RELEVANCE_THRESHOLD]
    if grades.sufficient and len(kept) >= MIN_RELEVANT_CHUNKS:
        return "answer"
    if state.get("retrieval_attempts", 0) < MAX_RETRIEVAL_ATTEMPTS:
        return "retry"
    return "answer" if kept else "insufficient"


# --- Graph ---------------------------------------------------------------


def build_graph():
    g = StateGraph(QAState)
    g.add_node("plan_query", plan_query)
    g.add_node("retrieve", retrieve_node)
    g.add_node("grade_chunks", grade_chunks)
    g.add_node("answer", answer_node)
    g.add_node("validate_citations", validate_citations)
    g.add_node("insufficient", insufficient_node)

    g.add_edge(START, "plan_query")
    g.add_edge("plan_query", "retrieve")
    g.add_edge("retrieve", "grade_chunks")
    g.add_conditional_edges(
        "grade_chunks",
        route_after_grading,
        {
            "answer": "answer",
            "retry": "plan_query",
            "insufficient": "insufficient",
        },
    )
    g.add_edge("answer", "validate_citations")
    g.add_edge("validate_citations", END)
    g.add_edge("insufficient", END)

    return g.compile()


_GRAPH = None


def _graph():
    global _GRAPH  # noqa: PLW0603
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH


async def run_qa(
    video_id: str,
    question: str,
    llm: LLMConfig,
    *,
    history: list[dict] | None = None,
) -> QAState:
    """Run the Q&A graph end to end, wrapped in one MLflow run (§17)."""
    params = {"video_id": video_id, "provider": llm.provider, "model": llm.model}
    async with tracing.run_context("videomind-qa", params):
        state: QAState = {
            "video_id": video_id,
            "question": question,
            "llm": llm,
            "history": history or [],
            "retrieval_attempts": 0,
        }
        result: QAState = await _graph().ainvoke(state, config={"recursion_limit": 50})
    return result
