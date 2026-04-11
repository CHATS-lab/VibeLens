"""Phase segment model for conversation phase detection results."""

from datetime import datetime

from pydantic import BaseModel, Field

from vibelens.models.enums import SessionPhase


class PhaseSegment(BaseModel):
    """A contiguous range of steps sharing the same phase."""

    phase: SessionPhase = Field(description="Detected phase for this segment.")
    start_index: int = Field(description="First message index (inclusive).")
    end_index: int = Field(description="Last message index (inclusive).")
    start_time: datetime | None = Field(default=None, description="Timestamp of first message.")
    end_time: datetime | None = Field(default=None, description="Timestamp of last message.")
    dominant_tool_category: str = Field(
        default="", description="Most frequent tool category in this segment."
    )
    tool_call_count: int = Field(default=0, description="Total tool calls in this segment.")
