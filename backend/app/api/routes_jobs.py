"""Job status and progress polling endpoints (§14.2, §15)."""

from fastapi import APIRouter

from app.config import STAGE_LABELS
from app.core.errors import JobNotFound
from app.schemas.api import JobResponse
from app.services import jobs

router = APIRouter()


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str) -> JobResponse:
    job = jobs.get(job_id)
    if job is None:
        raise JobNotFound("No job with that id.")
    return JobResponse(
        job_id=job.job_id,
        video_id=job.video_id,
        status=job.status,
        stage=job.stage,
        stage_label=STAGE_LABELS.get(job.stage) if job.stage else None,
        progress=job.progress,
        retries=job.retries,
        error_code=job.error_code,
        error_message=job.error_message,
    )
