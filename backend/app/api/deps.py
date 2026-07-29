"""Per-request LLMConfig resolution: request body override, else server defaults (§7.3)."""

from app.config import settings
from app.core.llm import LLMConfig
from app.schemas.api import LLMConfigIn

_SERVER_KEYS = {
    "gemini": lambda: settings.GEMINI_API_KEY,
    "openai": lambda: settings.OPENAI_API_KEY,
    "anthropic": lambda: settings.ANTHROPIC_API_KEY,
    "custom": lambda: None,
}


def resolve_llm_config(llm: LLMConfigIn | None) -> LLMConfig:
    """Merge a per-request override (§7.3) over the server-side defaults. A
    field the caller leaves unset falls back to config; the API key falls back
    to the provider's server key so the demo works without a user key."""
    provider = llm.provider if llm and llm.provider else settings.DEFAULT_LLM_PROVIDER
    model = llm.model if llm and llm.model else settings.DEFAULT_LLM_MODEL
    api_key = llm.api_key if llm and llm.api_key else _SERVER_KEYS[provider]()
    base_url = llm.base_url if llm and llm.base_url else settings.CUSTOM_LLM_BASE_URL
    return LLMConfig(provider=provider, model=model, api_key=api_key, base_url=base_url)
