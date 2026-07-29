"""LLM provider abstraction (§7). The only module in the repo allowed to
import litellm.

Exposes exactly two async functions, `generate` and `generate_structured`,
plus the `LLMConfig` model. Provider selection, retries, and structured
output repair are handled here.
"""

import asyncio
import json
import random
import re
from collections.abc import Callable
from json import JSONDecodeError
from typing import Any, Literal, TypeVar

import litellm  # noqa: TID251 -- this file is the sanctioned litellm boundary
from pydantic import BaseModel, ValidationError

from app.config import settings
from app.core import tracing
from app.core.errors import LLMAuthError, LLMUnavailableError, StructuredOutputError
from app.core.ratelimit import get_rate_limiter

T = TypeVar("T", bound=BaseModel)

_PREFIX = {
    "gemini": "gemini/",
    "openai": "openai/",
    "anthropic": "anthropic/",
    "custom": "openai/",  # any OpenAI-compatible endpoint, requires base_url
}

_LIMITS_BY_PROVIDER: dict[str, Callable[[], tuple[int, int | None]]] = {
    "gemini": lambda: (settings.GEMINI_RPM, settings.GEMINI_RPD),
    "openai": lambda: (settings.OPENAI_RPM, None),
    "anthropic": lambda: (settings.ANTHROPIC_RPM, None),
    "custom": lambda: (settings.CUSTOM_RPM, None),
}

_RETRY_BACKOFF_SECONDS = (1.0, 4.0, 12.0)  # one delay per retry (§7.4)
_MAX_ATTEMPTS = 1 + len(_RETRY_BACKOFF_SECONDS)  # 1 initial + 3 retries
_JITTER_SECONDS = 0.5
_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```$", re.DOTALL)


class LLMConfig(BaseModel):
    provider: Literal["gemini", "openai", "anthropic", "custom"] = "gemini"
    model: str = "gemini-2.5-flash"
    api_key: str | None = None  # NEVER logged, NEVER persisted, NEVER echoed
    base_url: str | None = None
    temperature: float = 0.0
    max_tokens: int = 2048

    def __repr__(self) -> str:  # defensive: keys never leak via repr/traceback
        key_state = "set" if self.api_key else "unset"
        return f"LLMConfig(provider={self.provider}, model={self.model}, key={key_state})"


class _ResponseFormatRejected(Exception):
    """Internal sentinel: the provider rejected `response_format`. Caught only
    by `generate_structured`, which falls back to prompt-embedded schema
    instructions. Never escapes this module."""


async def generate(prompt: str, cfg: LLMConfig, *, system: str | None = None) -> str:
    response = await _complete(_build_messages(prompt, system), cfg)
    return str(response.choices[0].message.content)


async def generate_structured(
    prompt: str,
    cfg: LLMConfig,
    schema: type[T],
    *,
    system: str | None = None,
    repair_attempts: int = 1,
) -> T:
    messages = _build_messages(prompt, system)
    response_format = _json_schema_format(schema)
    structured_mode = "json_schema"
    try:
        raw = await _complete(messages, cfg, response_format=response_format)
    except _ResponseFormatRejected:
        structured_mode = "prompt"
        messages = _with_schema_instructions(messages, schema)
        raw = await _complete(messages, cfg)
    text = raw.choices[0].message.content

    attempt = 0
    while True:
        try:
            return schema.model_validate_json(_strip_markdown_fences(text))
        except (ValidationError, JSONDecodeError) as exc:
            if attempt >= repair_attempts:
                raise StructuredOutputError(
                    f"Model failed to produce valid {schema.__name__} JSON "
                    f"after {repair_attempts} repair attempt(s)."
                ) from exc
            attempt += 1
            messages = [
                *messages,
                {"role": "assistant", "content": text},
                {
                    "role": "user",
                    "content": f"{exc}\n\nReturn only valid JSON matching the schema.",
                },
            ]
            fmt = response_format if structured_mode == "json_schema" else None
            raw = await _complete(messages, cfg, response_format=fmt)
            text = raw.choices[0].message.content


def _json_schema_format(schema: type[BaseModel]) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": schema.__name__,
            "schema": schema.model_json_schema(),
            "strict": True,
        },
    }


def _build_messages(prompt: str, system: str | None) -> list[dict[str, str]]:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    return messages


def _with_schema_instructions(
    messages: list[dict[str, str]], schema: type[BaseModel]
) -> list[dict[str, str]]:
    instructions = (
        "Respond with ONLY valid JSON matching this schema, no markdown fences:\n"
        f"{json.dumps(schema.model_json_schema())}"
    )
    result = list(messages)
    if result and result[0]["role"] == "system":
        result[0] = {"role": "system", "content": result[0]["content"] + "\n\n" + instructions}
    else:
        result.insert(0, {"role": "system", "content": instructions})
    return result


def _strip_markdown_fences(text: str) -> str:
    stripped = text.strip()
    match = _FENCE_RE.match(stripped)
    return match.group(1).strip() if match else stripped


def _rejects_response_format(exc: Exception) -> bool:
    message = str(exc).lower()
    return "response_format" in message or "json_schema" in message


def _is_transient(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    if status in (429, 500, 502, 503):
        return True
    return isinstance(exc, (litellm.exceptions.APIConnectionError, litellm.exceptions.Timeout))


def _is_fatal_client_error(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    if status in (400, 401, 403):
        return True
    return isinstance(
        exc, (litellm.exceptions.AuthenticationError, litellm.exceptions.BadRequestError)
    )


async def _complete(
    messages: list[dict[str, str]], cfg: LLMConfig, *, response_format: dict[str, Any] | None = None
) -> Any:
    rpm, rpd = _LIMITS_BY_PROVIDER[cfg.provider]()
    limiter = get_rate_limiter(cfg.provider, cfg.model, rpm=rpm, rpd=rpd)
    tracing.record_llm_call()
    last_exc: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        await limiter.acquire()
        try:
            return await litellm.acompletion(
                model=_PREFIX[cfg.provider] + cfg.model,
                messages=messages,
                api_key=cfg.api_key,
                base_url=cfg.base_url,
                temperature=cfg.temperature,
                max_tokens=cfg.max_tokens,
                response_format=response_format,
            )
        except Exception as exc:
            if response_format is not None and _rejects_response_format(exc):
                raise _ResponseFormatRejected from exc
            if _is_fatal_client_error(exc):
                raise LLMAuthError("Check your API key / model name in Settings.") from exc
            if not _is_transient(exc):
                raise
            last_exc = exc
            if attempt < _MAX_ATTEMPTS:
                delay = _RETRY_BACKOFF_SECONDS[attempt - 1] + random.uniform(0, _JITTER_SECONDS)
                await asyncio.sleep(delay)
    raise LLMUnavailableError(
        "The LLM provider is temporarily unavailable. Try again shortly."
    ) from last_exc
