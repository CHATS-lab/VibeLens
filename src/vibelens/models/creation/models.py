"""Generalized element creation models for any file-based element type."""

from pydantic import BaseModel, Field

from vibelens.models.enums import ElementType


class ElementCreationProposal(BaseModel):
    """A lightweight creation proposal before deep content generation.

    Produced by the proposal LLM step. The user approves proposals
    before the deep-creation step generates full file content.
    """

    element_type: ElementType = Field(description="Type of element to create.")
    name: str = Field(description="Proposed element name in kebab-case.")
    description: str = Field(description="What the element would do. Max 30 words.")
    rationale: str = Field(
        description=(
            "One sentence (max 15 words), then 1-2 bullets "
            "starting with '\\n- ' (max 10 words each)."
        )
    )
    addressed_patterns: list[str] = Field(
        default_factory=list, description="Workflow pattern titles this proposal addresses."
    )
    relevant_session_indices: list[int] = Field(
        default_factory=list, description="0-indexed session indices relevant to this proposal."
    )
    confidence: float = Field(
        default=0.0, description="Confidence this addresses a real recurring need. 0.0-1.0."
    )


class ElementCreation(BaseModel):
    """A fully generated element from detected workflow patterns.

    Produced by the deep-creation LLM step. Contains complete file content
    ready to write to disk.
    """

    element_type: ElementType = Field(description="Type of element being created.")
    name: str = Field(description="Element name in kebab-case.")
    description: str = Field(description="What it does, plain language. Max 30 words.")
    file_content: str = Field(description="Full file content to write.")
    target_path: str = Field(
        description="Suggested install path, e.g. ~/.claude/commands/foo.md."
    )
    rationale: str = Field(
        description=(
            "One sentence (max 15 words), then 1-2 bullets "
            "starting with '\\n- ' (max 10 words each)."
        )
    )
    tools_used: list[str] = Field(
        default_factory=list, description="Tool names referenced (e.g. Read, Edit, Bash)."
    )
    addressed_patterns: list[str] = Field(
        default_factory=list, description="Workflow pattern titles addressed."
    )
    confidence: float = Field(
        default=0.0, description="Confidence score 0.0-1.0."
    )
