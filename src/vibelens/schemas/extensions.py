"""Extension API schemas — unified for all types + catalog-specific."""

from typing import Literal

from pydantic import BaseModel, Field

from vibelens.models.enums import AgentExtensionType


class SyncTargetResponse(BaseModel):
    """Unified sync target for all extension types."""

    agent: str = Field(description="Agent identifier (e.g. 'claude').")
    count: int = Field(description="Number of extensions of this type in agent.")
    dir: str = Field(description="Agent directory or settings path.")


class ExtensionInstallRequest(BaseModel):
    """Install a new file-based extension."""

    name: str = Field(description="Kebab-case extension name.")
    content: str = Field(description="Full file content.")
    sync_to: list[str] = Field(
        default_factory=list, description="Agent keys to sync to after install."
    )
    link_type: Literal["symlink", "copy"] = Field(
        default="symlink",
        description="Whether to symlink (default) or copy when syncing to agents.",
    )


class ExtensionModifyRequest(BaseModel):
    """Update extension content."""

    content: str = Field(description="New file content.")
    link_type: Literal["symlink", "copy"] = Field(
        default="symlink",
        description="Used when re-syncing the modified extension to agents that already have it.",
    )


class ExtensionSyncRequest(BaseModel):
    """Sync extension to specific agents."""

    agents: list[str] = Field(description="Agent keys to sync to.")
    link_type: Literal["symlink", "copy"] = Field(
        default="symlink",
        description="Whether to symlink (default) or copy when syncing.",
    )


class ExtensionDetailResponse(BaseModel):
    """Full extension detail including content."""

    item: dict = Field(description="Extension metadata (Skill/Command/Subagent/Hook).")
    content: str = Field(description="Raw file text.")
    path: str = Field(description="Central store path.")


class ExtensionListResponse(BaseModel):
    """Paginated extension listing with sync targets. Used by all types."""

    items: list[dict] = Field(description="Page of extensions.")
    total: int = Field(description="Total matching.")
    page: int = Field(description="Current page.")
    page_size: int = Field(description="Items per page.")
    sync_targets: list[SyncTargetResponse] = Field(description="Agent platforms available.")


class ExtensionTreeEntry(BaseModel):
    """One entry in an on-disk extension file tree."""

    path: str = Field(description="Path relative to the extension root, posix-style.")
    kind: Literal["file", "dir"] = Field(description="Entry kind.")
    size: int | None = Field(default=None, description="File byte size (None for dirs).")


class ExtensionTreeResponse(BaseModel):
    """On-disk file tree rooted at the extension's central store dir."""

    name: str = Field(description="Extension name.")
    root: str = Field(description="Absolute on-disk root directory.")
    entries: list[ExtensionTreeEntry] = Field(description="Flat listing of files and dirs.")
    truncated: bool = Field(
        default=False, description="True when the walk was capped at the entry limit."
    )


class ExtensionFileResponse(BaseModel):
    """Raw text content of a single file inside an extension directory."""

    path: str = Field(description="Path relative to the extension root, posix-style.")
    content: str = Field(description="UTF-8 text content; empty string for binaries.")
    truncated: bool = Field(
        default=False, description="True when the file exceeded the read cap."
    )


class CatalogListResponse(BaseModel):
    """Paginated catalog listing response."""

    items: list[dict] = Field(description="Summary-projected extension items.")
    total: int = Field(description="Total matching items.")
    page: int = Field(description="Current page number.")
    per_page: int = Field(description="Items per page.")


class CatalogInstallRequest(BaseModel):
    """Request body for installing from catalog."""

    target_platforms: list[str] = Field(
        min_length=1, description="Target agent platforms for installation."
    )
    overwrite: bool = Field(
        default=False, description="Overwrite existing file if it already exists."
    )


class CatalogInstallResult(BaseModel):
    """Result of installing to a single platform."""

    success: bool = Field(description="Whether installation succeeded.")
    installed_path: str = Field(default="", description="Path where installed.")
    message: str = Field(default="", description="Status message.")


class CatalogInstallResponse(BaseModel):
    """Response after installing from catalog."""

    success: bool = Field(description="Whether all installations succeeded.")
    installed_path: str = Field(default="", description="Path of first successful install.")
    message: str = Field(default="", description="Status message.")
    results: dict[str, CatalogInstallResult] = Field(
        default_factory=dict, description="Per-platform results."
    )


class ExtensionMetaResponse(BaseModel):
    """Catalog metadata for frontend filter/sort options."""

    topics: list[str] = Field(description="Unique topics across the catalog.")
    has_profile: bool = Field(description="Whether a user profile exists for relevance sorting.")


class AgentCapability(BaseModel):
    """Per-agent capability entry."""

    key: str = Field(description="AgentType value, e.g. 'claude'.")
    installed: bool = Field(description="Whether the agent's root directory exists.")
    supported_types: list[str] = Field(description="Extension types this agent can install.")


class AgentCapabilitiesResponse(BaseModel):
    """Response for GET /extensions/agents."""

    agents: list[AgentCapability] = Field(description="All known platforms.")


class CollectionItemSchema(BaseModel):
    """One extension reference inside a collection."""

    extension_type: AgentExtensionType = Field(description="Extension type.")
    name: str = Field(description="Kebab-case extension name.")
    pinned_version: str | None = Field(default=None, description="Optional version pin.")


class CollectionCreateRequest(BaseModel):
    """Body for POST /extensions/collections."""

    name: str = Field(description="Kebab-case collection name.")
    description: str = Field(default="", description="Description.")
    items: list[CollectionItemSchema] = Field(default_factory=list, description="Items.")
    tags: list[str] = Field(default_factory=list, description="Tags.")


class CollectionUpdateRequest(BaseModel):
    """Body for PUT /extensions/collections/{name}. Fields left None are kept."""

    description: str | None = Field(default=None, description="New description.")
    items: list[CollectionItemSchema] | None = Field(default=None, description="New items.")
    tags: list[str] | None = Field(default=None, description="New tags.")


class CollectionInstallRequest(BaseModel):
    """Body for POST /extensions/collections/{name}/install."""

    agents: list[str] = Field(description="Agent keys to install to.")
    link_type: Literal["symlink", "copy"] = Field(
        default="symlink", description="Install method."
    )


class CollectionImportRequest(BaseModel):
    """Body for POST /extensions/collections/import."""

    payload: dict = Field(description="Exported collection JSON payload.")


class CollectionResponse(BaseModel):
    """Single collection in the API."""

    name: str = Field(description="Kebab-case collection name.")
    description: str = Field(description="Human description of the collection.")
    items: list[CollectionItemSchema] = Field(description="Ordered list of references.")
    tags: list[str] = Field(description="Free-form tags for discovery.")
    created_at: str = Field(description="Creation timestamp (ISO 8601 UTC).")
    updated_at: str = Field(description="Last-modified timestamp (ISO 8601 UTC).")


class CollectionListResponse(BaseModel):
    """Response for GET /extensions/collections."""

    items: list[CollectionResponse] = Field(description="Collections in the response page.")
    total: int = Field(description="Total number of collections.")


class CollectionInstallResponse(BaseModel):
    """Response for POST /extensions/collections/{name}/install."""

    name: str = Field(description="Collection name that was installed.")
    results: dict[str, dict[str, str]] = Field(
        description="Per-item, per-agent install outcome: 'ok' | 'missing' | 'failed' | error."
    )
