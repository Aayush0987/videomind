"""Request/response models for the HTTP API surface (§6, §14, §15)."""

from typing import Literal

from pydantic import BaseModel, Field

# --- Shared (§14.1) ------------------------------------------------------


class LLMConfigIn(BaseModel):
    provider: Literal["gemini", "openai", "anthropic", "custom"] | None = None
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None


class ErrorResponse(BaseModel):
    error_code: str
    message: str
    detail: str | None = None


# --- POST /api/videos ----------------------------------------------------


class AnalyzeRequest(BaseModel):
    url: str
    llm: LLMConfigIn | None = None
    force_refresh: bool = False


class AnalyzeResponse(BaseModel):
    cached: bool
    video_id: str
    job_id: str | None = None


# --- GET /api/jobs/{job_id} ---------------------------------------------


class JobResponse(BaseModel):
    job_id: str
    video_id: str | None = None
    status: str
    stage: str | None = None
    stage_label: str | None = None
    progress: float
    retries: dict[str, int] = Field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None


# --- GET /api/videos/{video_id} -----------------------------------------


class ChapterOut(BaseModel):
    chapter_id: str
    idx: int
    start: float
    end: float
    title: str
    summary: str
    key_points: list[str]


class EnrichmentOut(BaseModel):
    entity: str
    kind: str
    blurb: str
    source_url: str | None = None
    first_mention: float


class VerificationOut(BaseModel):
    valid: bool
    repaired: bool
    issues: list[str]


class VideoResponse(BaseModel):
    video_id: str
    url: str
    title: str
    channel: str | None = None
    duration: float
    thumbnail_url: str | None = None
    transcript_source: str
    language: str
    chapters: list[ChapterOut]
    enrichments: list[EnrichmentOut]
    verification: VerificationOut


# --- GET /api/videos/{video_id}/transcript ------------------------------


class TranscriptUnitOut(BaseModel):
    idx: int
    start: float
    end: float
    text: str


class TranscriptResponse(BaseModel):
    units: list[TranscriptUnitOut]


# --- POST /api/videos/{video_id}/ask ------------------------------------


class AskRequest(BaseModel):
    question: str = Field(max_length=1000)
    history: list[dict] = Field(default_factory=list)
    llm: LLMConfigIn | None = None


class CitationOut(BaseModel):
    marker: str
    chunk_id: str
    start: float
    end: float
    quote: str
    chapter_title: str


class TraceOut(BaseModel):
    strategy: str
    retrieval_attempts: int
    chunks_retrieved: int
    chunks_kept: int
    dropped_citations: int
    nodes: list[str]
    latency_ms: int


class AskResponse(BaseModel):
    answer: str
    citations: list[CitationOut]
    confidence: Literal["high", "medium", "low"]
    trace: TraceOut


# --- POST /api/llm/ping (§16.7) -----------------------------------------


class PingResponse(BaseModel):
    ok: bool
    error: str | None = None


# --- GET /api/health -----------------------------------------------------


class HealthResponse(BaseModel):
    status: str
    version: str
    embedder: str
    embedding_dim: int
    collection: str
    whisper_enabled: bool
    videos_cached: int
