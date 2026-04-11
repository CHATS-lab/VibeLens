"""In-memory async job tracker for background LLM analysis tasks."""

import asyncio
import time
from collections.abc import Coroutine
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Optional

from vibelens.utils.log import get_logger

logger = get_logger(__name__)


class JobStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AnalysisJob:
    job_id: str
    status: JobStatus
    task: asyncio.Task[Any]
    analysis_id: Optional[str] = None
    error_message: Optional[str] = None
    created_at: float = field(default_factory=time.monotonic)


_jobs: dict[str, AnalysisJob] = {}


def submit_job(job_id: str, coro: Coroutine[Any, Any, Any]) -> AnalysisJob:
    """Wrap a coroutine in an asyncio.Task and register it."""
    task = asyncio.create_task(coro)
    job = AnalysisJob(job_id=job_id, status=JobStatus.RUNNING, task=task)
    _jobs[job_id] = job
    logger.info("Job %s submitted", job_id)
    return job


def get_job(job_id: str) -> Optional[AnalysisJob]:
    """Return the job for *job_id*, or None."""
    return _jobs.get(job_id)


def cancel_job(job_id: str) -> bool:
    """Cancel a running job. Returns True if cancellation was requested."""
    job = _jobs.get(job_id)
    if not job or job.status != JobStatus.RUNNING:
        return False
    job.task.cancel()
    job.status = JobStatus.CANCELLED
    logger.info("Job %s cancelled", job_id)
    return True


def mark_completed(job_id: str, analysis_id: str) -> None:
    """Mark a job as completed with its result analysis_id."""
    job = _jobs.get(job_id)
    if not job:
        return
    job.status = JobStatus.COMPLETED
    job.analysis_id = analysis_id
    logger.info("Job %s completed → analysis %s", job_id, analysis_id)


def mark_failed(job_id: str, error: str) -> None:
    """Mark a job as failed with an error message."""
    job = _jobs.get(job_id)
    if not job:
        return
    job.status = JobStatus.FAILED
    job.error_message = error
    logger.warning("Job %s failed: %s", job_id, error)


def cleanup_stale(max_age_s: float = 3600) -> int:
    """Remove finished jobs older than *max_age_s*. Returns count removed."""
    now = time.monotonic()
    stale = [
        jid
        for jid, j in _jobs.items()
        if j.status != JobStatus.RUNNING and (now - j.created_at) > max_age_s
    ]
    for jid in stale:
        del _jobs[jid]
    if stale:
        logger.info("Cleaned up %d stale jobs", len(stale))
    return len(stale)
