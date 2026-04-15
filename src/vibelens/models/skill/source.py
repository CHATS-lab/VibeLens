"""Source metadata for extensions."""

from pydantic import BaseModel, Field

from vibelens.models.enums import ExtensionSource


class ExtensionSourceInfo(BaseModel):
    """One source from which an extension is available or was loaded."""

    source_type: ExtensionSource = Field(description="Source/store type for this extension.")
    source_path: str = Field(description="Local path or URL for the source.")
