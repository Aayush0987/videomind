"""LangGraph analysis pipeline: ingestion through segmentation, verification,
titling, and indexing (§10.1-10.3).

Every node's first action reports progress via `jobs.update`. Nodes are wrapped
with `@traced` so the run's `RunMetrics` records the node path and latencies.
The failure policy is repair-before-resegment (§10.2): deterministic repair is
tried first, and only structural failures escalate to a fresh LLM segmentation,
capped at `MAX_SEGMENTATION_ATTEMPTS`.
"""

import dataclasses

from langgraph.graph import END, START, StateGraph

from app.agents import enrichment, segmentation, titling, verification
from app.agents import entities as entities_agent
from app.config import MAX_SEGMENTATION_ATTEMPTS, STAGE_WEIGHTS
from app.core import db, tracing
from app.core.chunking import ChapterRange, build_chunks
from app.core.embedder import get_embedder
from app.core.llm import LLMConfig
from app.core.vectorstore import VectorStore
from app.graphs.state import AnalysisState
from app.ingestion.youtube import fetch_metadata, parse_video_id
from app.schemas.transcript import TranscriptCue
from app.services import jobs
from app.services.pipeline import acquire_transcript

# Cumulative progress per stage, in pipeline order (§10.3). A node reports the
# cumulative weight up to and including its stage.
_STAGE_ORDER = list(STAGE_WEIGHTS)
_CUMULATIVE: dict[str, float] = {}
_running = 0.0
for _stage in _STAGE_ORDER:
    _running += STAGE_WEIGHTS[_stage]
    _CUMULATIVE[_stage] = round(_running, 6)


def _progress(job_id: str, stage: str) -> None:
    jobs.update(job_id, stage=stage, progress=_CUMULATIVE[stage])


# --- Nodes ---------------------------------------------------------------


@tracing.traced("resolve_source")
async def resolve_source(state: AnalysisState) -> dict:
    _progress(state["job_id"], "resolve_source")
    video_id = parse_video_id(state["url"])
    metadata = fetch_metadata(video_id)
    return {"video_id": video_id, "metadata": dataclasses.asdict(metadata)}


@tracing.traced("fetch_transcript")
async def fetch_transcript(state: AnalysisState) -> dict:
    _progress(state["job_id"], "fetch_transcript")
    metadata = state["metadata"]
    transcript = acquire_transcript(state["video_id"], state["url"], metadata["duration"])
    return {"transcript": transcript}


@tracing.traced("normalize_transcript")
async def normalize_transcript(state: AnalysisState) -> dict:
    _progress(state["job_id"], "normalize")
    transcript = state["transcript"]
    embedder = get_embedder()
    unit_embeddings = await embedder.embed_passages([u.text for u in transcript.units])
    return {"unit_embeddings": unit_embeddings}


@tracing.traced("propose_boundaries")
async def propose_boundaries(state: AnalysisState) -> dict:
    _progress(state["job_id"], "propose_boundaries")
    transcript = state["transcript"]
    metadata = state["metadata"]
    attempts = state.get("segmentation_attempts", 0) + 1
    # A re-segmentation surfaces as an amber retry indicator in the UI (§16.4).
    if attempts > 1:
        jobs.update(state["job_id"], retries={"segmentation": attempts - 1})
    boundaries = await segmentation.propose_boundaries(
        transcript.units,
        state["unit_embeddings"],
        state["llm"],
        title=metadata["title"],
        duration=transcript.duration,
    )
    # Reset the repair flag so a fresh segmentation gets its own repair attempt.
    return {
        "boundaries": boundaries,
        "segmentation_attempts": attempts,
        "verification": None,
    }


@tracing.traced("build_chapters")
async def build_chapters(state: AnalysisState) -> dict:
    _progress(state["job_id"], "propose_boundaries")
    transcript = state["transcript"]
    chapters = segmentation.build_chapters(
        state["video_id"], state["boundaries"], transcript.units, transcript.duration
    )
    return {"chapters": chapters}


@tracing.traced("verify_chapters")
async def verify_chapters(state: AnalysisState) -> dict:
    _progress(state["job_id"], "verify_repair")
    transcript = state["transcript"]
    report = verification.verify_chapters(state["chapters"], transcript.duration, transcript.units)
    prev = state.get("verification")
    if prev is not None and prev.repaired:
        report = report.model_copy(update={"repaired": True})
    return {"verification": report}


@tracing.traced("repair_chapters")
async def repair_chapters(state: AnalysisState) -> dict:
    _progress(state["job_id"], "verify_repair")
    transcript = state["transcript"]
    chapters, report = verification.repair_chapters(
        state["chapters"], transcript.duration, transcript.units
    )
    return {"chapters": chapters, "verification": report}


@tracing.traced("title_and_summarize")
async def title_and_summarize(state: AnalysisState) -> dict:
    _progress(state["job_id"], "title_and_summarize")
    transcript = state["transcript"]
    metadata = state["metadata"]
    chapters = await titling.title_and_summarize(
        state["chapters"], transcript.units, state["llm"], video_title=metadata["title"]
    )
    return {"chapters": chapters}


@tracing.traced("extract_entities")
async def extract_entities(state: AnalysisState) -> dict:
    _progress(state["job_id"], "entities")
    extraction = await entities_agent.extract_entities(state["chapters"], state["llm"])
    return {"entities": extraction.entities}


@tracing.traced("enrich")
async def enrich(state: AnalysisState) -> dict:
    _progress(state["job_id"], "enrich")
    notes = await enrichment.enrich(state["entities"], state["llm"])
    return {"enrichment": notes}


@tracing.traced("index_transcript")
async def index_transcript(state: AnalysisState) -> dict:
    _progress(state["job_id"], "index")
    transcript = state["transcript"]
    ranges = [
        ChapterRange(
            chapter_id=ch.chapter_id,
            chapter_idx=ch.idx,
            chapter_title=ch.title,
            start=ch.start,
            end=ch.end,
        )
        for ch in state["chapters"]
    ]
    chunks = build_chunks(state["video_id"], transcript.units, ranges)
    embedder = get_embedder()
    embeddings = await embedder.embed_passages([c.doc_text for c in chunks])
    store = VectorStore(embedder)
    store.upsert(chunks, embeddings)
    return {}


@tracing.traced("persist")
async def persist(state: AnalysisState) -> dict:
    _progress(state["job_id"], "index")
    conn = db.get_connection()
    db.init_schema(conn)
    metadata = state["metadata"]
    transcript = state["transcript"]
    db.upsert_video(
        conn,
        video_id=state["video_id"],
        url=state["url"],
        title=metadata["title"],
        channel=metadata.get("channel"),
        duration=transcript.duration,
        thumbnail_url=metadata.get("thumbnail_url"),
        published_at=metadata.get("published_at"),
        transcript_source=transcript.source,
        language=transcript.language,
    )
    db.upsert_transcript(
        conn,
        state["video_id"],
        [TranscriptCue(start=u.start, end=u.end, text=u.text) for u in transcript.units],
    )
    db.upsert_chapters(conn, state["video_id"], state["chapters"])
    db.upsert_enrichments(conn, state["video_id"], state.get("enrichment", []))
    jobs.update(state["job_id"], status="ready", video_id=state["video_id"], progress=1.0)
    return {}


# --- Routers -------------------------------------------------------------


def route_after_verify(state: AnalysisState) -> str:
    report = state["verification"]
    if report.valid:
        return "ok"
    if not report.repaired:
        return "repair"  # deterministic fix first
    if state.get("segmentation_attempts", 0) < MAX_SEGMENTATION_ATTEMPTS:
        return "resegment"
    return "give_up"


def route_after_entities(state: AnalysisState) -> str:
    return "enrich" if any(e.needs_enrichment for e in state.get("entities", [])) else "skip"


# --- Graph ---------------------------------------------------------------


def build_graph():
    g = StateGraph(AnalysisState)
    g.add_node("resolve_source", resolve_source)
    g.add_node("fetch_transcript", fetch_transcript)
    g.add_node("normalize_transcript", normalize_transcript)
    g.add_node("propose_boundaries", propose_boundaries)
    g.add_node("build_chapters", build_chapters)
    g.add_node("verify_chapters", verify_chapters)
    g.add_node("repair_chapters", repair_chapters)
    g.add_node("title_and_summarize", title_and_summarize)
    g.add_node("extract_entities", extract_entities)
    g.add_node("enrich", enrich)
    g.add_node("index_transcript", index_transcript)
    g.add_node("persist", persist)

    g.add_edge(START, "resolve_source")
    g.add_edge("resolve_source", "fetch_transcript")
    g.add_edge("fetch_transcript", "normalize_transcript")
    g.add_edge("normalize_transcript", "propose_boundaries")
    g.add_edge("propose_boundaries", "build_chapters")
    g.add_edge("build_chapters", "verify_chapters")

    g.add_conditional_edges(
        "verify_chapters",
        route_after_verify,
        {
            "ok": "title_and_summarize",
            "repair": "repair_chapters",
            "resegment": "propose_boundaries",
            "give_up": "title_and_summarize",
        },
    )
    g.add_edge("repair_chapters", "verify_chapters")
    g.add_edge("title_and_summarize", "extract_entities")

    g.add_conditional_edges(
        "extract_entities",
        route_after_entities,
        {"enrich": "enrich", "skip": "index_transcript"},
    )
    g.add_edge("enrich", "index_transcript")
    g.add_edge("index_transcript", "persist")
    g.add_edge("persist", END)

    return g.compile()


_GRAPH = None


def _graph():
    global _GRAPH  # noqa: PLW0603
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH


async def run_analysis(job_id: str, url: str, llm: LLMConfig) -> AnalysisState:
    """Run the analysis graph end to end, wrapped in one MLflow run (§17)."""
    from app.config import CURRENT_ANALYSIS_VERSION, settings

    jobs.update(job_id, url=url, status="running", progress=0.0)
    params = {
        "provider": llm.provider,
        "model": llm.model,
        "request_id": job_id,
        "embedding_backend": settings.EMBEDDING_BACKEND,
        "embedding_model": settings.EMBEDDING_MODEL,
        "embedding_dim": settings.EMBEDDING_DIM,
        "analysis_version": CURRENT_ANALYSIS_VERSION,
    }
    async with tracing.run_context("videomind-analysis", params) as metrics:
        state: AnalysisState = {
            "job_id": job_id,
            "url": url,
            "llm": llm,
            "segmentation_attempts": 0,
            "errors": [],
        }
        result: AnalysisState = await _graph().ainvoke(state, config={"recursion_limit": 50})
        report = result.get("verification")
        metrics.verification_report = report
        metrics.verification_issues = len(report.issues) if report is not None else 0
        metrics.chapters_final = len(result.get("chapters", []))
        metrics.segmentation_attempts = result.get("segmentation_attempts", 0)
        transcript = result.get("transcript")
        metrics.params.update(
            {
                "video_id": result.get("video_id"),
                "duration": transcript.duration if transcript is not None else None,
                "transcript_source": transcript.source if transcript is not None else None,
            }
        )
    return result
