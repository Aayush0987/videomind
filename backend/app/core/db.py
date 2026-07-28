"""sqlite3 connection, schema init, and typed row helpers (§5)."""

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.config import CURRENT_ANALYSIS_VERSION, settings
from app.schemas.transcript import TranscriptCue

_SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    video_id        TEXT PRIMARY KEY,
    url             TEXT NOT NULL,
    title           TEXT NOT NULL,
    channel         TEXT,
    duration        REAL NOT NULL,
    thumbnail_url   TEXT,
    published_at    TEXT,
    transcript_source TEXT NOT NULL,
    language        TEXT NOT NULL,
    status          TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    analysis_version INTEGER NOT NULL DEFAULT 1,
    embedding_model TEXT NOT NULL,
    embedding_dim   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS transcripts (
    video_id  TEXT PRIMARY KEY REFERENCES videos(video_id) ON DELETE CASCADE,
    cues_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chapters (
    video_id    TEXT NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,
    chapter_id  TEXT NOT NULL,
    idx         INTEGER NOT NULL,
    start       REAL NOT NULL,
    end         REAL NOT NULL,
    title       TEXT NOT NULL,
    summary     TEXT NOT NULL,
    key_points_json TEXT NOT NULL,
    PRIMARY KEY (video_id, chapter_id)
);

CREATE TABLE IF NOT EXISTS enrichments (
    video_id    TEXT NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,
    entity      TEXT NOT NULL,
    kind        TEXT NOT NULL,
    blurb       TEXT NOT NULL,
    source_url  TEXT,
    first_mention REAL NOT NULL,
    PRIMARY KEY (video_id, entity)
);

CREATE TABLE IF NOT EXISTS jobs (
    job_id      TEXT PRIMARY KEY,
    video_id    TEXT,
    url         TEXT NOT NULL,
    status      TEXT NOT NULL,
    stage       TEXT,
    progress    REAL NOT NULL DEFAULT 0.0,
    error_code  TEXT,
    error_message TEXT,
    retries_json TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chapters_video ON chapters(video_id, idx);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
"""


@dataclass
class VideoRow:
    video_id: str
    url: str
    title: str
    channel: str | None
    duration: float
    thumbnail_url: str | None
    published_at: str | None
    transcript_source: str
    language: str
    status: str
    created_at: str
    analysis_version: int
    embedding_model: str
    embedding_dim: int


_connection: sqlite3.Connection | None = None


def get_connection() -> sqlite3.Connection:
    global _connection
    if _connection is None:
        db_path = Path(settings.DATA_DIR) / "videomind.sqlite3"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _connection = sqlite3.connect(str(db_path), check_same_thread=False)
        _connection.row_factory = sqlite3.Row
        _connection.execute("PRAGMA journal_mode=WAL")
    return _connection


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    conn.commit()


def reset_connection() -> None:
    """Test-only: closes and clears the module-level connection singleton so
    a monkeypatched `settings.DATA_DIR` takes effect on the next
    `get_connection()` call, and so state doesn't bleed across tests."""
    global _connection
    if _connection is not None:
        _connection.close()
        _connection = None


def upsert_video(
    conn: sqlite3.Connection,
    *,
    video_id: str,
    url: str,
    title: str,
    channel: str | None,
    duration: float,
    thumbnail_url: str | None,
    published_at: str | None,
    transcript_source: str,
    language: str,
) -> None:
    conn.execute(
        """
        INSERT INTO videos (
            video_id, url, title, channel, duration, thumbnail_url,
            published_at, transcript_source, language, status, created_at,
            analysis_version, embedding_model, embedding_dim
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(video_id) DO UPDATE SET
            url=excluded.url, title=excluded.title, channel=excluded.channel,
            duration=excluded.duration, thumbnail_url=excluded.thumbnail_url,
            published_at=excluded.published_at,
            transcript_source=excluded.transcript_source,
            language=excluded.language, status=excluded.status,
            analysis_version=excluded.analysis_version,
            embedding_model=excluded.embedding_model,
            embedding_dim=excluded.embedding_dim
        """,
        (
            video_id,
            url,
            title,
            channel,
            duration,
            thumbnail_url,
            published_at,
            transcript_source,
            language,
            "ready",
            datetime.now(UTC).isoformat(),
            CURRENT_ANALYSIS_VERSION,
            settings.EMBEDDING_MODEL,
            settings.EMBEDDING_DIM,
        ),
    )
    conn.commit()


def get_video(conn: sqlite3.Connection, video_id: str) -> VideoRow | None:
    row = conn.execute("SELECT * FROM videos WHERE video_id = ?", (video_id,)).fetchone()
    if row is None:
        return None
    return VideoRow(**dict(row))


def upsert_transcript(conn: sqlite3.Connection, video_id: str, cues: list[TranscriptCue]) -> None:
    cues_json = json.dumps([cue.model_dump() for cue in cues])
    conn.execute(
        """
        INSERT INTO transcripts (video_id, cues_json) VALUES (?, ?)
        ON CONFLICT(video_id) DO UPDATE SET cues_json=excluded.cues_json
        """,
        (video_id, cues_json),
    )
    conn.commit()


def get_transcript_cues(conn: sqlite3.Connection, video_id: str) -> list[TranscriptCue] | None:
    row = conn.execute(
        "SELECT cues_json FROM transcripts WHERE video_id = ?", (video_id,)
    ).fetchone()
    if row is None:
        return None
    return [TranscriptCue(**cue) for cue in json.loads(row["cues_json"])]
