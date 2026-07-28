"""Shared fixtures. No test may make a real network call (§18.1)."""

from collections.abc import Iterator

import pytest
from app import config
from app.core import ratelimit

# Deliberately no top-level `import litellm` here -- this file lives under
# `tests/`, which is also covered by the ruff litellm import ban (§7). The
# fixture below reaches litellm.acompletion via a string target instead, so
# it patches the real module without adding a syntactic `import litellm`.


class BlockedNetworkCall(RuntimeError):
    """Raised when a test reaches litellm.acompletion without mocking it."""


async def _raise_on_network_call(*args: object, **kwargs: object) -> None:
    raise BlockedNetworkCall(
        "litellm.acompletion was called without being mocked. "
        "No test may make a real network call -- patch this or use FakeLLM."
    )


@pytest.fixture(autouse=True)
def _no_network_no_real_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "sk-test-bogus-not-a-real-key")
    monkeypatch.setattr(config.settings, "GEMINI_API_KEY", "sk-test-bogus-not-a-real-key")
    monkeypatch.setattr("litellm.acompletion", _raise_on_network_call)


@pytest.fixture(autouse=True)
def _reset_rate_limiter_registry() -> Iterator[None]:
    ratelimit.reset_registry()
    yield
    ratelimit.reset_registry()
