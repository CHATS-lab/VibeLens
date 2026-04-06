"""Share request, response, and metadata models."""

from datetime import datetime

from pydantic import BaseModel, Field


class ShareRequest(BaseModel):
    """Request to create a shareable link for a session."""

    session_id: str = Field(description="Session ID to share.")


class ShareResponse(BaseModel):
    """Response containing the shareable link details."""

    session_id: str = Field(description="Session ID used as the share token.")
    url: str = Field(description="Full shareable URL.")
    title: str = Field(description="Session title extracted from first message.")
    created_at: datetime = Field(description="When the share was created.")


class ShareMeta(BaseModel):
    """Metadata for a shared session."""

    session_id: str = Field(description="Session ID (also serves as share token).")
    title: str = Field(description="Session title from first message.")
    created_at: datetime = Field(description="When the share was created.")
