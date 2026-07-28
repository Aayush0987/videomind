"""Application settings, loaded from environment variables (§19).

Nothing else in the codebase reads `os.environ` directly — every value
flows through the `Settings` singleton defined here. Tuning constants
(chunking thresholds, MMR lambda, etc.) are added to this module by the
phase that introduces them; none exist yet.
"""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- LLM ---
    DEFAULT_LLM_PROVIDER: Literal["gemini", "openai", "anthropic", "custom"] = "gemini"
    DEFAULT_LLM_MODEL: str = "gemini-2.5-flash"
    GEMINI_API_KEY: str | None = None
    OPENAI_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None
    CUSTOM_LLM_BASE_URL: str | None = None

    # --- Rate limits ---
    GEMINI_RPM: int = 10
    GEMINI_RPD: int = 1000
    OPENAI_RPM: int = 60
    ANTHROPIC_RPM: int = 50
    CUSTOM_RPM: int = 60

    # --- YouTube ---
    YOUTUBE_API_KEY: str | None = None
    YTDLP_COOKIES_FILE: str | None = None
    YTDLP_PROXY: str | None = None

    # --- Transcription ---
    ENABLE_WHISPER: bool = True
    WHISPER_MODEL: str = "base"
    MAX_VIDEO_DURATION: int = 5400

    # --- Embeddings ---
    EMBEDDING_BACKEND: Literal["gemini", "sentence_transformers"] = "gemini"
    EMBEDDING_MODEL: str = "gemini-embedding-001"
    EMBEDDING_DIM: int = 768
    EMBEDDING_BATCH_SIZE: int = 64
    GEMINI_EMBED_RPM: int = 100

    # --- Storage ---
    DATA_DIR: str = "./data"

    # --- Observability ---
    MLFLOW_ENABLED: bool = True
    MLFLOW_TRACKING_URI: str = "file:./data/mlruns"

    # --- Server ---
    FRONTEND_ORIGIN: str = "http://localhost:3000"
    ANALYZE_RATE_PER_HOUR: int = 20
    LOG_LEVEL: str = "INFO"


settings = Settings()

# --- Tuning constants (code-level, not environment-configurable; bump in
# code review, not via .env) ---
CURRENT_ANALYSIS_VERSION = 1
UNIT_MAX_SECONDS = 15.0
UNIT_MAX_CHARS = 350
