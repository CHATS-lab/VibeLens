"""Upload result model."""

from datetime import datetime

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
    upload_id: str = Field(default="", description="Identifier of this upload directory.")
    zip_sha256: str = Field(default="", description="SHA-256 of the uploaded zip bytes.")
    deduplicated: bool = Field(
        default=False,
        description="True if this zip's content was already imported under the same agent_type.",
    )
    original_upload_id: str | None = Field(
        default=None,
        description="When deduplicated, the upload_id that originally imported this content.",
    )
    original_uploaded_at: datetime | None = Field(
        default=None,
        description="When deduplicated, when the original was imported.",
    )
