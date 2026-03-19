"""Content models for multimodal ATIF trajectories.

Added in ATIF v1.6 to support multimodal content (images, PDFs, etc.)
in trajectories.
"""

from pydantic import BaseModel, Field, model_validator

from vibelens.models.enums import ContentType


class Base64Source(BaseModel):
    """Non-text content source with optional inline base64 encoding.

    Base model for all file-based content sources. Supports inline
    base64 data from agent APIs (e.g. Anthropic's image content blocks)
    and path-based file references.
    """

    media_type: str = Field(
        description="MIME type of the content (e.g. 'image/png', 'application/pdf')."
    )
    base64: str = Field(default="", description="[VibeLens] Base64-encoded content data.")


class ImageSource(Base64Source):
    """Image source specification (ATIF v1.6 compatible).

    ATIF v1.6 uses path-based file references. VibeLens extends with
    optional base64 for inline content from agent APIs via Base64Source.
    """

    path: str = Field(
        default="", description="Location of the image: relative/absolute file path, or URL."
    )


class ContentPart(BaseModel):
    """A single content part within a multimodal message (ATIF v1.6).

    Used when a message or observation contains mixed content types
    (text, images, PDFs, etc.). For text-only content, a plain string
    is used instead of a ContentPart array.
    """

    type: ContentType = Field(description="The type of content.")
    text: str | None = Field(default=None, description="Text content. Required when type='text'.")
    source: Base64Source | None = Field(
        default=None, description="Content source reference. Required when type is not 'text'."
    )

    @model_validator(mode="after")
    def validate_content_type(self) -> "ContentPart":
        """Ensure correct fields are present for each content type."""
        if self.type == ContentType.TEXT:
            if self.text is None:
                raise ValueError("'text' field is required when type='text'")
            if self.source is not None:
                raise ValueError("'source' field is not allowed when type='text'")
        else:
            if self.source is None:
                raise ValueError(f"'source' field is required when type='{self.type}'")
            if self.text is not None:
                raise ValueError(f"'text' field is not allowed when type='{self.type}'")
        return self
