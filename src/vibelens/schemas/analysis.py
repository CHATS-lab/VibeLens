"""Shared response models for background analysis jobs."""

from pydantic import BaseModel


class AnalysisJobResponse(BaseModel):
    """Returned by POST endpoints that launch background analysis."""

    job_id: str
    status: str
    analysis_id: str | None = None


class AnalysisJobStatus(BaseModel):
    """Returned by job polling and cancel endpoints."""

    job_id: str
    status: str
    analysis_id: str | None = None
    error_message: str | None = None
