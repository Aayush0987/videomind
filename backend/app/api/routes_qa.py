"""Q&A endpoint: runs the Q&A graph and returns cited answers (§13, §14.2)."""

from fastapi import APIRouter

from app.api.deps import resolve_llm_config
from app.config import QA_HISTORY_TURNS
from app.core import db
from app.core.errors import VideoMindError, VideoNotFound
from app.core.llm import generate
from app.graphs.qa_graph import run_qa
from app.schemas.api import (
    AskRequest,
    AskResponse,
    CitationOut,
    LLMConfigIn,
    PingResponse,
    TraceOut,
)

router = APIRouter()


@router.post("/videos/{video_id}/ask", response_model=AskResponse)
async def ask(video_id: str, req: AskRequest) -> AskResponse:
    conn = db.get_connection()
    db.init_schema(conn)
    video = db.get_video(conn, video_id)
    if video is None or video.status != "ready":
        raise VideoNotFound("No analysis exists for that video.")

    llm = resolve_llm_config(req.llm)
    result = await run_qa(
        video_id,
        req.question,
        llm,
        history=req.history[-QA_HISTORY_TURNS:],
    )
    draft = result.get("draft")
    confidence = draft.confidence if draft is not None else "low"
    trace = result["trace"]
    return AskResponse(
        answer=result["answer"],
        citations=[
            CitationOut(
                marker=c.marker,
                chunk_id=c.chunk_id,
                start=c.start,
                end=c.end,
                quote=c.quote,
                chapter_title=c.chapter_title,
            )
            for c in result["citations"]
        ],
        confidence=confidence,
        trace=TraceOut(**trace),
    )


@router.post("/llm/ping", response_model=PingResponse)
async def ping(llm: LLMConfigIn | None = None) -> PingResponse:
    """One tiny 5-token generate to verify provider connectivity (§16.7)."""
    cfg = resolve_llm_config(llm).model_copy(update={"max_tokens": 5})
    try:
        await generate("ping", cfg)
    except VideoMindError as exc:
        return PingResponse(ok=False, error=exc.message)
    return PingResponse(ok=True)
