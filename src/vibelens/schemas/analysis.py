"""Shared response models for background analysis jobs."""

from typing import Optional

from pydantic import BaseModel


class AnalysisJobResponse(BaseModel):
    """Returned by POST endpoints that launch background analysis."""

    job_id: str
    status: str
    analysis_id: Optional[str] = None


class AnalysisJobStatus(BaseModel):
    """Returned by job polling and cancel endpoints."""

    job_id: str
    status: str
    analysis_id: Optional[str] = None
    error_message: Optional[str] = None
