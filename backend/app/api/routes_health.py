"""Health check endpoint, used by the frontend to warm the backend (§21.2 D4)."""

from fastapi import APIRouter

from app.config import APP_VERSION, settings
from app.core import db
from app.core.embedder import get_embedder
from app.core.vectorstore import slug
from app.schemas.api import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    embedder = get_embedder()
    conn = db.get_connection()
    db.init_schema(conn)
    return HealthResponse(
        status="ok",
        version=APP_VERSION,
        embedder=embedder.name,
        embedding_dim=embedder.dim,
        collection=f"chunks__{slug(embedder.name)}_{embedder.dim}",
        whisper_enabled=settings.ENABLE_WHISPER,
        videos_cached=db.count_videos(conn),
    )
