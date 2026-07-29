"""SQLite-backed job registry and background runner for async analysis (§15).

Job state lives in the `jobs` table, not a process dict, so a restart mid-job
leaves an honest record: `cleanup_stale` marks any interrupted row `failed`.
A module-level `asyncio.Semaphore(MAX_CONCURRENT_JOBS)` serialises analyses so a
free-tier box never runs two Whisper jobs at once. Progress is clamped
monotonically — the timeline (§16.4) never moves backwards, even when the graph
loops back to an earlier stage on a re-segment.
"""

import asyncio
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.config import INTERRUPTED_MESSAGE, MAX_CONCURRENT_JOBS
from app.core import db
from app.core.errors import VideoMindError
from app.core.llm import LLMConfig


@dataclass
class Job:
    job_id: str
    url: str = ""
    video_id: str | None = None
    status: str = "running"
    stage: str | None = None
    progress: float = 0.0
    retries: dict[str, int] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None


_semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)
_initialized_conn: sqlite3.Connection | None = None


def _conn() -> sqlite3.Connection:
    """Return the shared connection, initialising the schema once per distinct
    connection object (it changes when tests reset `settings.DATA_DIR`)."""
    global _initialized_conn  # noqa: PLW0603
    conn = db.get_connection()
    if conn is not _initialized_conn:
        db.init_schema(conn)
        _initialized_conn = conn
    return conn


def _row_to_job(row: sqlite3.Row) -> Job:
    return Job(
        job_id=row["job_id"],
        url=row["url"],
        video_id=row["video_id"],
        status=row["status"],
        stage=row["stage"],
        progress=row["progress"],
        retries=json.loads(row["retries_json"]),
        error_code=row["error_code"],
        error_message=row["error_message"],
    )


def _write(conn: sqlite3.Connection, job: Job, now: str) -> None:
    existing = conn.execute(
        "SELECT created_at FROM jobs WHERE job_id = ?", (job.job_id,)
    ).fetchone()
    created_at = existing["created_at"] if existing is not None else now
    conn.execute(
        """
        INSERT INTO jobs (
            job_id, video_id, url, status, stage, progress,
            error_code, error_message, retries_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(job_id) DO UPDATE SET
            video_id=excluded.video_id, url=excluded.url, status=excluded.status,
            stage=excluded.stage, progress=excluded.progress,
            error_code=excluded.error_code, error_message=excluded.error_message,
            retries_json=excluded.retries_json, updated_at=excluded.updated_at
        """,
        (
            job.job_id,
            job.video_id,
            job.url,
            job.status,
            job.stage,
            job.progress,
            job.error_code,
            job.error_message,
            json.dumps(job.retries),
            created_at,
            now,
        ),
    )
    conn.commit()


def create(job_id: str, url: str = "") -> Job:
    """Insert a fresh `queued` job row (§15)."""
    return update(job_id, url=url, status="queued", progress=0.0)


def update(job_id: str, **fields: object) -> Job:
    conn = _conn()
    row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
    job = _row_to_job(row) if row is not None else Job(job_id=job_id)
    if "progress" in fields:
        fields["progress"] = max(job.progress, float(fields["progress"]))  # type: ignore[arg-type]
    for key, value in fields.items():
        setattr(job, key, value)
    _write(conn, job, datetime.now(UTC).isoformat())
    return job


def get(job_id: str) -> Job | None:
    row = _conn().execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
    return _row_to_job(row) if row is not None else None


def cleanup_stale() -> None:
    """On startup, mark any job left `running`/`queued` by a crash as `failed`
    with an honest interrupted message (§15)."""
    conn = _conn()
    conn.execute(
        """
        UPDATE jobs
        SET status='failed', error_code='internal_error', error_message=?, updated_at=?
        WHERE status IN ('running', 'queued')
        """,
        (INTERRUPTED_MESSAGE, datetime.now(UTC).isoformat()),
    )
    conn.commit()


def schedule(job_id: str, url: str, llm: LLMConfig) -> None:
    """Fire-and-forget the analysis under the concurrency semaphore (§15)."""
    asyncio.create_task(_run_job(job_id, url, llm))


async def _run_job(job_id: str, url: str, llm: LLMConfig) -> None:
    # Imported lazily: analysis_graph imports this module, so a top-level import
    # would be circular.
    from app.graphs.analysis_graph import run_analysis

    async with _semaphore:
        try:
            await run_analysis(job_id, url, llm)
        except VideoMindError as exc:
            update(job_id, status="failed", error_code=exc.error_code, error_message=exc.message)
        except Exception as exc:  # noqa: BLE001 -- honest-failure record, not masking
            update(job_id, status="failed", error_code="internal_error", error_message=str(exc))


def reset() -> None:
    """Test-only: forget which connection was schema-initialised."""
    global _initialized_conn  # noqa: PLW0603
    _initialized_conn = None
