"""Typed domain errors surfaced across ingestion, LLM calls, and retrieval.

The full closed set of `error_code` strings is defined in the build spec
§14.1 and owned by the API layer (Phase 8). This module only defines the
error classes that Phase 1 code (`core/llm.py`, `core/ratelimit.py`) raises;
later phases add their own subclasses here as they need them.
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
