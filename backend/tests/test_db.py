"""Tests for app.core.db (§5): schema init, row upsert/get roundtrips."""

from pathlib import Path

import pytest
from app import config
from app.core import db
from app.schemas.transcript import TranscriptCue


@pytest.fixture(autouse=True)
def _data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.settings, "DATA_DIR", str(tmp_path))


def test_init_schema_is_idempotent() -> None:
    conn = db.get_connection()
    db.init_schema(conn)
    db.init_schema(conn)  # second call must not raise


def test_upsert_video_and_get_video_roundtrip() -> None:
    conn = db.get_connection()
    db.init_schema(conn)

    db.upsert_video(
        conn,
        video_id="abc123",
        url="https://youtu.be/abc123",
        title="A Title",
        channel="A Channel",
        duration=120.5,
        thumbnail_url="https://img.example/abc123.jpg",
        published_at="2024-01-01",
        transcript_source="captions",
        language="en",
    )

    row = db.get_video(conn, "abc123")
    assert row is not None
    assert row.video_id == "abc123"
    assert row.url == "https://youtu.be/abc123"
    assert row.title == "A Title"
    assert row.channel == "A Channel"
    assert row.duration == 120.5
    assert row.thumbnail_url == "https://img.example/abc123.jpg"
    assert row.published_at == "2024-01-01"
    assert row.transcript_source == "captions"
    assert row.language == "en"
    assert row.status == "ready"
    assert row.analysis_version == config.CURRENT_ANALYSIS_VERSION
    assert row.embedding_model == config.settings.EMBEDDING_MODEL
    assert row.embedding_dim == config.settings.EMBEDDING_DIM


def test_upsert_video_conflict_updates_existing_row() -> None:
    conn = db.get_connection()
    db.init_schema(conn)

    db.upsert_video(
        conn,
        video_id="abc123",
        url="https://youtu.be/abc123",
        title="Old Title",
        channel=None,
        duration=100.0,
        thumbnail_url=None,
        published_at=None,
        transcript_source="captions",
        language="en",
    )
    db.upsert_video(
        conn,
        video_id="abc123",
        url="https://youtu.be/abc123",
        title="New Title",
        channel=None,
        duration=100.0,
        thumbnail_url=None,
        published_at=None,
        transcript_source="whisper",
        language="es",
    )

    row = db.get_video(conn, "abc123")
    assert row is not None
    assert row.title == "New Title"
    assert row.transcript_source == "whisper"
    assert row.language == "es"


def test_get_video_returns_none_for_unknown_id() -> None:
    conn = db.get_connection()
    db.init_schema(conn)

    assert db.get_video(conn, "does-not-exist") is None


def test_upsert_transcript_and_get_transcript_cues_roundtrip() -> None:
    conn = db.get_connection()
    db.init_schema(conn)

    db.upsert_video(
        conn,
        video_id="abc123",
        url="https://youtu.be/abc123",
        title="A Title",
        channel=None,
        duration=10.0,
        thumbnail_url=None,
        published_at=None,
        transcript_source="captions",
        language="en",
    )
    cues = [
        TranscriptCue(start=0.0, end=1.5, text="Hello there."),
        TranscriptCue(start=1.5, end=3.0, text="General Kenobi."),
    ]
    db.upsert_transcript(conn, "abc123", cues)

    fetched = db.get_transcript_cues(conn, "abc123")
    assert fetched == cues


def test_get_transcript_cues_returns_none_for_unknown_video() -> None:
    conn = db.get_connection()
    db.init_schema(conn)

    assert db.get_transcript_cues(conn, "does-not-exist") is None
