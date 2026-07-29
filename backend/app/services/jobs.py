"""In-memory job registry and background runner for async video analysis (§15).

Phase 6 needs only a process-local registry so the analysis graph can report
`stage`/`progress` as it runs; Phase 8 backs this with the SQLite `jobs` table.
Progress is clamped monotonically — the timeline (§16.4) never moves backwards,
even when the graph loops back to an earlier stage on a re-segment.
"""

from dataclasses import dataclass


@dataclass
class Job:
    job_id: str
    url: str = ""
    video_id: str | None = None
    status: str = "running"
    stage: str | None = None
    progress: float = 0.0
    error_code: str | None = None
    error_message: str | None = None


_jobs: dict[str, Job] = {}


def create(job_id: str, url: str = "") -> Job:
    job = Job(job_id=job_id, url=url)
    _jobs[job_id] = job
    return job


def update(job_id: str, **fields: object) -> Job:
    job = _jobs.get(job_id)
    if job is None:
        job = create(job_id)
    if "progress" in fields:
        fields["progress"] = max(job.progress, float(fields["progress"]))  # type: ignore[arg-type]
    for key, value in fields.items():
        setattr(job, key, value)
    return job


def get(job_id: str) -> Job | None:
    return _jobs.get(job_id)


def reset() -> None:
    """Test-only: clear the registry between tests."""
    _jobs.clear()
