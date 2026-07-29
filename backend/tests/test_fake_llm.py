"""Tests for tests/fakes/fake_llm.py (§18.1). FakeLLM never touches the
network -- it's the double every later phase's agent tests inject in place
of app.core.llm.generate/generate_structured.
"""

import pytest
from app.core.errors import StructuredOutputError
from app.core.llm import LLMConfig
from pydantic import BaseModel

from fakes.fake_llm import FakeLLM


class _Widget(BaseModel):
    value: int


async def test_generate_returns_canned_string_and_logs_call() -> None:
    fake = FakeLLM()
    fake.responses["hello prompt"] = "hello response"

    result = await fake.generate("hello prompt", LLMConfig())

    assert result == "hello response"
    assert len(fake.call_log) == 1
    assert fake.call_log[0].kind == "generate"
    assert fake.call_log[0].prompt == "hello prompt"


async def test_generate_structured_returns_canned_pydantic_instance() -> None:
    fake = FakeLLM()
    widget = _Widget(value=42)
    fake.responses["widget prompt"] = widget

    result = await fake.generate_structured("widget prompt", LLMConfig(), _Widget)

    assert result == widget
    assert result is widget
    assert fake.call_log[0].kind == "generate_structured"
    assert fake.call_log[0].schema is _Widget


async def test_generate_structured_accepts_raw_json_string() -> None:
    fake = FakeLLM()
    fake.responses["widget prompt"] = '{"value": 7}'

    result = await fake.generate_structured("widget prompt", LLMConfig(), _Widget)

    assert result == _Widget(value=7)


async def test_generate_structured_falls_back_to_schema_name_lookup() -> None:
    fake = FakeLLM()
    widget = _Widget(value=1)
    fake.responses[_Widget.__name__] = widget

    result = await fake.generate_structured("some unrelated prompt text", LLMConfig(), _Widget)

    assert result == widget


async def test_fail_next_raises_once() -> None:
    fake = FakeLLM()
    fake.responses["p"] = "ok"
    fake.fail_next(RuntimeError("injected failure"))

    with pytest.raises(RuntimeError, match="injected failure"):
        await fake.generate("p", LLMConfig())

    # consumed -- second call proceeds normally
    result = await fake.generate("p", LLMConfig())
    assert result == "ok"


async def test_return_invalid_json_next_raises_structured_output_error_once() -> None:
    fake = FakeLLM()
    fake.responses[_Widget.__name__] = _Widget(value=1)
    fake.return_invalid_json_next()

    with pytest.raises(StructuredOutputError):
        await fake.generate_structured("p", LLMConfig(), _Widget)

    result = await fake.generate_structured("p", LLMConfig(), _Widget)
    assert result == _Widget(value=1)


async def test_return_schema_violation_next_raises_structured_output_error_once() -> None:
    fake = FakeLLM()
    fake.responses[_Widget.__name__] = _Widget(value=1)
    fake.return_schema_violation_next()

    with pytest.raises(StructuredOutputError):
        await fake.generate_structured("p", LLMConfig(), _Widget)

    result = await fake.generate_structured("p", LLMConfig(), _Widget)
    assert result == _Widget(value=1)


async def test_missing_response_raises_key_error() -> None:
    fake = FakeLLM()

    with pytest.raises(KeyError):
        await fake.generate("unregistered prompt", LLMConfig())
