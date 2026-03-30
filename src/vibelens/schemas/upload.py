"""Upload result model."""

from pydantic import BaseModel, Field


class UploadResult(BaseModel):
    """Result of a file upload operation."""

    files_received: int = Field(default=0, description="Number of files received in the request.")
    sessions_parsed: int = Field(default=0, description="Number of sessions successfully parsed.")
    steps_stored: int = Field(default=0, description="Total steps stored across all sessions.")
    skipped: int = Field(default=0, description="Number of sessions skipped (already exist).")
    secrets_redacted: int = Field(default=0, description="Total credential patterns redacted.")
    paths_anonymized: int = Field(default=0, description="Total path usernames hashed.")
    pii_redacted: int = Field(default=0, description="Total PII items redacted.")
    errors: list[dict] = Field(
        default_factory=list, description="Per-file error details for failed uploads."
    )
