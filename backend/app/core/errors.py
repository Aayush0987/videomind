"""Typed domain errors surfaced across ingestion, LLM calls, and retrieval.

The full closed set of `error_code` strings is defined in the build spec
§14.1 and owned by the API layer (Phase 8). This module only defines the
error classes that Phase 1 (`core/llm.py`, `core/ratelimit.py`) and Phase 2
(`ingestion/*.py`, `services/pipeline.py`) code raises; later phases add
their own subclasses here as they need them.
"""


class VideoMindError(Exception):
    """Base class for typed domain errors. `error_code` is a class attribute
    because it identifies the error kind, not a particular raise site."""

    error_code: str

    def __init__(self, message: str, *, detail: str | None = None) -> None:
        self.message = message
        self.detail = detail
        super().__init__(message)


class LLMAuthError(VideoMindError):
    """401/403 (bad key) or 400 (bad request) from the provider — not retryable."""

    error_code = "llm_auth_failed"


class LLMUnavailableError(VideoMindError):
    """Transient errors (429/500/502/503/timeout) exhausted all retries."""

    error_code = "llm_unavailable"


class StructuredOutputError(VideoMindError):
    """generate_structured failed to produce valid JSON after its one repair attempt."""

    error_code = "structured_output_failed"


class DailyQuotaExhausted(VideoMindError):
    """RateLimiter.acquire hit the configured daily quota (rpd)."""

    error_code = "quota_exhausted"


class UnsupportedSourceError(VideoMindError):
    """`parse_video_id` could not extract a video id from the given URL."""

    error_code = "invalid_url"


class VideoTooLongError(VideoMindError):
    """Video duration exceeds `settings.MAX_VIDEO_DURATION`."""

    error_code = "video_too_long"


class MetadataUnavailableError(VideoMindError):
    """Both the YouTube Data API and the yt-dlp metadata fallback failed."""

    error_code = "metadata_unavailable"


class TranscriptUnavailableError(VideoMindError):
    """All four transcript acquisition rungs (§9.3) failed."""

    error_code = "transcript_unavailable"


class EmbeddingBackendUnavailable(VideoMindError):
    """Embedding API connection failure or non-2xx response."""

    error_code = "embedding_backend_unavailable"


class VideoNotFound(VideoMindError):
    """No analysis row exists for the requested `video_id` (§14.2)."""

    error_code = "video_not_found"


class JobNotFound(VideoMindError):
    """No job row exists for the requested `job_id` (§14.2)."""

    error_code = "job_not_found"


class EmbeddingMismatch(VideoMindError):
    """A cached video was indexed with a different embedder than the one now
    configured (§7.6) — `GET /api/videos/{id}` returns 409."""

    error_code = "embedding_mismatch"
