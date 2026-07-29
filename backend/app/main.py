"""FastAPI application entrypoint: app instance, routers, and lifespan.

The lifespan handler performs schema init, embedder warm-up, and stale-job
cleanup on startup (§8.2), and configures CORS and the per-IP analyze rate
limiter (§14, §15).
"""

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.api import routes_health, routes_jobs, routes_qa, routes_videos
from app.config import settings
from app.core import db
from app.core.embedder import get_embedder, probe_embedder
from app.core.errors import VideoMindError
from app.schemas.api import ErrorResponse
from app.services import jobs

_MAX_BODY_BYTES = 32 * 1024  # §14.3 — 32 KB request cap.

# error_code → HTTP status (§14.1). Anything unmapped is a 500.
_STATUS_BY_CODE: dict[str, int] = {
    "invalid_url": 400,
    "video_too_long": 400,
    "transcript_unavailable": 422,
    "metadata_unavailable": 422,
    "embedding_backend_unavailable": 503,
    "embedding_mismatch": 409,
    "llm_auth_failed": 401,
    "llm_unavailable": 503,
    "quota_exhausted": 429,
    "structured_output_failed": 502,
    "video_not_found": 404,
    "job_not_found": 404,
    "internal_error": 500,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = db.get_connection()
    db.init_schema(conn)
    jobs.cleanup_stale()
    await probe_embedder(get_embedder())
    yield


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Enforce the body-size cap and stamp every response with an X-Request-ID
    (the same id is the MLflow run tag, §14.3)."""

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length is not None and int(content_length) > _MAX_BODY_BYTES:
            return JSONResponse(
                status_code=413,
                content=ErrorResponse(
                    error_code="internal_error",
                    message="Request body too large (max 32 KB).",
                ).model_dump(),
            )
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


app = FastAPI(title="VideoMind", lifespan=lifespan)

app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.FRONTEND_ORIGIN.split(",") if o.strip()],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(VideoMindError)
async def videomind_error_handler(request: Request, exc: VideoMindError) -> JSONResponse:
    status = _STATUS_BY_CODE.get(exc.error_code, 500)
    return JSONResponse(
        status_code=status,
        content=ErrorResponse(
            error_code=exc.error_code, message=exc.message, detail=exc.detail
        ).model_dump(),
    )


app.include_router(routes_videos.router, prefix="/api")
app.include_router(routes_jobs.router, prefix="/api")
app.include_router(routes_qa.router, prefix="/api")
app.include_router(routes_health.router, prefix="/api")
