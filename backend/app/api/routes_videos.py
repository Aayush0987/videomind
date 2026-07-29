"""Video ingestion and analysis endpoints (§14.2)."""

import uuid

from fastapi import APIRouter, Request, Response

from app.api.deps import resolve_llm_config
from app.config import CURRENT_ANALYSIS_VERSION, settings
from app.core import db
from app.core.embedder import get_embedder
from app.core.errors import DailyQuotaExhausted, EmbeddingMismatch, VideoNotFound
from app.core.ratelimit import get_ip_limiter
from app.core.vectorstore import VectorStore
from app.ingestion.youtube import parse_video_id
from app.schemas.api import (
    AnalyzeRequest,
    AnalyzeResponse,
    ChapterOut,
    EnrichmentOut,
    TranscriptResponse,
    TranscriptUnitOut,
    VerificationOut,
    VideoResponse,
)
from app.services import jobs

router = APIRouter()


@router.post("/videos", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest, request: Request, response: Response) -> AnalyzeResponse:
    client_ip = request.client.host if request.client else "unknown"
    if not get_ip_limiter().allow(client_ip):
        raise DailyQuotaExhausted("Too many analyses from this address. Try again later.")

    video_id = parse_video_id(req.url)  # raises invalid_url synchronously → 400
    conn = db.get_connection()
    db.init_schema(conn)
    existing = db.get_video(conn, video_id)
    cache_hit = (
        existing is not None
        and existing.status == "ready"
        and not req.force_refresh
        and existing.analysis_version == CURRENT_ANALYSIS_VERSION
        and existing.embedding_model == settings.EMBEDDING_MODEL
        and existing.embedding_dim == settings.EMBEDDING_DIM
    )
    if cache_hit:
        return AnalyzeResponse(cached=True, video_id=video_id, job_id=None)

    job_id = uuid.uuid4().hex
    jobs.create(job_id, url=req.url)
    jobs.schedule(job_id, req.url, resolve_llm_config(req.llm))
    response.status_code = 202
    return AnalyzeResponse(cached=False, video_id=video_id, job_id=job_id)


@router.get("/videos/{video_id}", response_model=VideoResponse)
async def get_video(video_id: str) -> VideoResponse:
    conn = db.get_connection()
    db.init_schema(conn)
    video = db.get_video(conn, video_id)
    if video is None or video.status != "ready":
        raise VideoNotFound("No analysis exists for that video.")
    embedder_changed = (
        video.embedding_model != settings.EMBEDDING_MODEL
        or video.embedding_dim != settings.EMBEDDING_DIM
    )
    if embedder_changed:
        raise EmbeddingMismatch(
            "This video was indexed with a different embedding model. "
            "Re-analyze it, or switch EMBEDDING_BACKEND back."
        )
    chapters = db.get_chapters(conn, video_id)
    enrichments = db.get_enrichments(conn, video_id)
    return VideoResponse(
        video_id=video.video_id,
        url=video.url,
        title=video.title,
        channel=video.channel,
        duration=video.duration,
        thumbnail_url=video.thumbnail_url,
        transcript_source=video.transcript_source,
        language=video.language,
        chapters=[
            ChapterOut(
                chapter_id=ch.chapter_id,
                idx=ch.idx,
                start=ch.start,
                end=ch.end,
                title=ch.title,
                summary=ch.summary,
                key_points=ch.key_points,
            )
            for ch in chapters
        ],
        enrichments=[
            EnrichmentOut(
                entity=n.entity,
                kind=n.kind,
                blurb=n.blurb,
                source_url=n.source_url,
                first_mention=n.first_mention,
            )
            for n in enrichments
        ],
        verification=VerificationOut(valid=True, repaired=False, issues=[]),
    )


@router.get("/videos/{video_id}/transcript", response_model=TranscriptResponse)
async def get_transcript(video_id: str) -> TranscriptResponse:
    conn = db.get_connection()
    db.init_schema(conn)
    cues = db.get_transcript_cues(conn, video_id)
    if cues is None:
        raise VideoNotFound("No transcript exists for that video.")
    return TranscriptResponse(
        units=[
            TranscriptUnitOut(idx=i, start=cue.start, end=cue.end, text=cue.text)
            for i, cue in enumerate(cues)
        ]
    )


@router.delete("/videos/{video_id}", status_code=204)
async def delete_video(video_id: str) -> Response:
    conn = db.get_connection()
    db.init_schema(conn)
    if db.get_video(conn, video_id) is None:
        raise VideoNotFound("No analysis exists for that video.")
    VectorStore(get_embedder()).delete_video(video_id)
    db.delete_video(conn, video_id)
    return Response(status_code=204)
