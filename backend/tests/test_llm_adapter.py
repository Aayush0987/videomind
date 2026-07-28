"""Tests for app.core.llm (§7, §18.2).

No test may make a real network call -- litellm.acompletion is always
mocked. Tests reference `litellm.acompletion` only via string-based
monkeypatch targets (`monkeypatch.setattr("litellm.acompletion", ...)`),
never a top-level `import litellm`, so this file itself respects the same
import boundary it's asserting on `app/`.
"""

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.core import llm
from app.core.errors import LLMAuthError, LLMUnavailableError, StructuredOutputError
from pydantic import BaseModel

_APP_DIR = Path(__file__).resolve().parent.parent / "app"
_LLM_MODULE = _APP_DIR / "core" / "llm.py"


class _Widget(BaseModel):
    value: int


class _ProviderError(Exception):
    """Stands in for a litellm/provider exception. `_is_transient` and
    `_is_fatal_client_error` classify primarily via `.status_code`, so tests
    never need litellm's real exception classes."""

    def __init__(self, status_code: int, message: str = "boom") -> None:
        super().__init__(message)
        self.status_code = status_code


def _response(content: str) -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


# --- provider -> model-string mapping -----------------------------------


@pytest.mark.parametrize(
    ("provider", "model"),
    [
        ("gemini", "gemini-2.5-flash"),
        ("openai", "gpt-4o-mini"),
        ("anthropic", "claude-3-5-sonnet"),
        ("custom", "local-model"),
    ],
)
async def test_provider_model_string_mapping(
    monkeypatch: pytest.MonkeyPatch, provider: str, model: str
) -> None:
    mock_acompletion = AsyncMock(return_value=_response("hello"))
    monkeypatch.setattr("litellm.acompletion", mock_acompletion)
    cfg = llm.LLMConfig(provider=provider, model=model, api_key="k")

    result = await llm.generate("hi", cfg)

    assert result == "hello"
    assert mock_acompletion.await_args.kwargs["model"] == llm._PREFIX[provider] + model
    assert mock_acompletion.await_args.kwargs["base_url"] == cfg.base_url


# --- generate_structured happy path + fence stripping --------------------


async def test_generate_structured_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    widget = _Widget(value=5)
    mock_acompletion = AsyncMock(return_value=_response(widget.model_dump_json()))
    monkeypatch.setattr("litellm.acompletion", mock_acompletion)
    cfg = llm.LLMConfig(api_key="k")

    result = await llm.generate_structured("prompt", cfg, _Widget)

    assert result == widget


async def test_markdown_fence_stripping(monkeypatch: pytest.MonkeyPatch) -> None:
    widget = _Widget(value=7)
    fenced = f"```json\n{widget.model_dump_json()}\n```"
    mock_acompletion = AsyncMock(return_value=_response(fenced))
    monkeypatch.setattr("litellm.acompletion", mock_acompletion)
    cfg = llm.LLMConfig(api_key="k")

    result = await llm.generate_structured("prompt", cfg, _Widget)

    assert result == widget


# --- repair loop -----------------------------------------------------------


async def test_repair_attempt_then_success(monkeypatch: pytest.MonkeyPatch) -> None:
    widget = _Widget(value=9)
    mock_acompletion = AsyncMock(
        side_effect=[_response("not valid json"), _response(widget.model_dump_json())]
    )
    monkeypatch.setattr("litellm.acompletion", mock_acompletion)
    cfg = llm.LLMConfig(api_key="k")

    result = await llm.generate_structured("prompt", cfg, _Widget, repair_attempts=1)

    assert result == widget
    assert mock_acompletion.await_count == 2


async def test_repair_exhausted_raises_structured_output_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_acompletion = AsyncMock(
        side_effect=[_response("not valid json"), _response("still not valid")]
    )
    monkeypatch.setattr("litellm.acompletion", mock_acompletion)
    cfg = llm.LLMConfig(api_key="k")

    with pytest.raises(StructuredOutputError):
        await llm.generate_structured("prompt", cfg, _Widget, repair_attempts=1)

    assert mock_acompletion.await_count == 2


# --- response_format rejection fallback -------------------------------------


async def test_response_format_rejection_falls_back_to_prompt_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    widget = _Widget(value=3)
    reject_exc = _ProviderError(400, "response_format is not supported for this model")
    mock_acompletion = AsyncMock(side_effect=[reject_exc, _response(widget.model_dump_json())])
    monkeypatch.setattr("litellm.acompletion", mock_acompletion)
    cfg = llm.LLMConfig(provider="custom", model="local-model", api_key="k")

    result = await llm.generate_structured("prompt", cfg, _Widget)

    assert result == widget
    assert mock_acompletion.await_count == 2
    first_kwargs = mock_acompletion.await_args_list[0].kwargs
    second_kwargs = mock_acompletion.await_args_list[1].kwargs
    assert first_kwargs["response_format"] is not None
    assert second_kwargs["response_format"] is None
    system_messages = [m["content"] for m in second_kwargs["messages"] if m["role"] == "system"]
    assert any("schema" in content.lower() for content in system_messages)


# --- retry semantics (§7.4) -------------------------------------------------


async def test_retries_on_transient_429_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_acompletion = AsyncMock(side_effect=[_ProviderError(429, "rate limited"), _response("ok")])
    monkeypatch.setattr("litellm.acompletion", mock_acompletion)
    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr(llm.asyncio, "sleep", fake_sleep)
    cfg = llm.LLMConfig(api_key="k")

    result = await llm.generate("prompt", cfg)

    assert result == "ok"
    assert mock_acompletion.await_count == 2
    assert len(sleep_calls) == 1
    assert 1.0 <= sleep_calls[0] <= 1.0 + llm._JITTER_SECONDS


async def test_retry_exhausted_raises_llm_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_acompletion = AsyncMock(
        side_effect=[_ProviderError(503, "unavailable")] * llm._MAX_ATTEMPTS
    )
    monkeypatch.setattr("litellm.acompletion", mock_acompletion)

    async def fake_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr(llm.asyncio, "sleep", fake_sleep)
    cfg = llm.LLMConfig(api_key="k")

    with pytest.raises(LLMUnavailableError):
        await llm.generate("prompt", cfg)

    assert mock_acompletion.await_count == llm._MAX_ATTEMPTS


async def test_auth_error_fails_immediately_no_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_acompletion = AsyncMock(side_effect=_ProviderError(401, "bad key"))
    monkeypatch.setattr("litellm.acompletion", mock_acompletion)
    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr(llm.asyncio, "sleep", fake_sleep)
    cfg = llm.LLMConfig(api_key="bad")

    with pytest.raises(LLMAuthError):
        await llm.generate("prompt", cfg)

    assert mock_acompletion.await_count == 1
    assert sleep_calls == []


async def test_bad_request_fails_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_acompletion = AsyncMock(side_effect=_ProviderError(400, "bad request"))
    monkeypatch.setattr("litellm.acompletion", mock_acompletion)
    cfg = llm.LLMConfig(api_key="k")

    with pytest.raises(LLMAuthError):
        await llm.generate("prompt", cfg)

    assert mock_acompletion.await_count == 1


# --- LLMConfig.__repr__ never leaks the key ---------------------------------


def test_repr_hides_api_key() -> None:
    cfg = llm.LLMConfig(api_key="super-secret-value")

    rendered = repr(cfg)

    assert "super-secret-value" not in rendered
    assert "key=set" in rendered
    assert "key=unset" in repr(llm.LLMConfig())


# --- rate limiter wiring -----------------------------------------------------


async def test_rate_limiter_acquired_once_per_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    class _CountingLimiter:
        def __init__(self) -> None:
            self.acquire_count = 0

        async def acquire(self) -> None:
            self.acquire_count += 1

    stub = _CountingLimiter()
    monkeypatch.setattr(llm, "get_rate_limiter", lambda *args, **kwargs: stub)
    mock_acompletion = AsyncMock(
        side_effect=[_ProviderError(503, "unavailable")] * llm._MAX_ATTEMPTS
    )
    monkeypatch.setattr("litellm.acompletion", mock_acompletion)

    async def fake_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr(llm.asyncio, "sleep", fake_sleep)
    cfg = llm.LLMConfig(api_key="k")

    with pytest.raises(LLMUnavailableError):
        await llm.generate("prompt", cfg)

    assert stub.acquire_count == llm._MAX_ATTEMPTS


# --- import boundary: only core/llm.py may import litellm ------------------


def _imported_top_level_modules(py_file: Path) -> set[str]:
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module.split(".")[0])
    return modules


def test_only_core_llm_module_imports_litellm() -> None:
    offenders = [
        py_file
        for py_file in _APP_DIR.rglob("*.py")
        if py_file != _LLM_MODULE and "litellm" in _imported_top_level_modules(py_file)
    ]
    assert offenders == []


def test_core_llm_module_actually_imports_litellm() -> None:
    """Sanity check that the scan above isn't vacuously true."""
    assert "litellm" in _imported_top_level_modules(_LLM_MODULE)
