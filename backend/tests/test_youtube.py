"""Tests for app.ingestion.youtube.parse_video_id (§9.1). Pure function,
no network -- the 12-URL-form table the spec asks for."""

import pytest
from app.core.errors import UnsupportedSourceError
from app.ingestion.youtube import parse_video_id

_VALID_CASES = [
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://m.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s", "dQw4w9WgXcQ"),
    (
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLxyz&index=3",
        "dQw4w9WgXcQ",
    ),
    ("https://youtu.be/dQw4w9WgXcQ/", "dQw4w9WgXcQ"),
    ("www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
]


@pytest.mark.parametrize("url,expected_id", _VALID_CASES)
def test_parse_video_id_valid_forms(url: str, expected_id: str) -> None:
    assert parse_video_id(url) == expected_id


_INVALID_CASES = [
    "https://www.example.com/watch?v=dQw4w9WgXcQ",
    "https://www.youtube.com/",
    "https://www.youtube.com/watch?v=short",
    "not a url at all",
    "https://www.youtube.com/channel/UCxyz",
]


@pytest.mark.parametrize("url", _INVALID_CASES)
def test_parse_video_id_invalid_forms_raise(url: str) -> None:
    with pytest.raises(UnsupportedSourceError):
        parse_video_id(url)
