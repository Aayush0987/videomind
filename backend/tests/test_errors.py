"""Tests for app.core.errors."""

import pytest
from app.core.errors import (
    DailyQuotaExhausted,
    LLMAuthError,
    LLMUnavailableError,
    StructuredOutputError,
    VideoMindError,
)


@pytest.mark.parametrize(
    ("error_cls", "expected_code"),
    [
        (LLMAuthError, "llm_auth_failed"),
        (LLMUnavailableError, "llm_unavailable"),
        (StructuredOutputError, "structured_output_failed"),
        (DailyQuotaExhausted, "quota_exhausted"),
    ],
)
def test_error_carries_expected_error_code(
    error_cls: type[VideoMindError], expected_code: str
) -> None:
    exc = error_cls("something went wrong")

    assert exc.error_code == expected_code
    assert isinstance(exc, VideoMindError)
    assert isinstance(exc, Exception)
    assert exc.message == "something went wrong"
    assert str(exc) == "something went wrong"


@pytest.mark.parametrize(
    "error_cls", [LLMAuthError, LLMUnavailableError, StructuredOutputError, DailyQuotaExhausted]
)
def test_error_detail_defaults_to_none_and_is_settable(error_cls: type[VideoMindError]) -> None:
    assert error_cls("msg").detail is None
    assert error_cls("msg", detail="extra context").detail == "extra context"


def test_error_can_be_raised_and_caught_as_base_class() -> None:
    with pytest.raises(VideoMindError):
        raise StructuredOutputError("bad json")
