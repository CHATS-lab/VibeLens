"""Analysis prompt template model for LLM-powered session analysis."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, Template
from pydantic import BaseModel, ConfigDict, Field

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "llm" / "prompts" / "templates"

_jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    keep_trailing_newline=False,
    trim_blocks=True,
    lstrip_blocks=True,
)


def load_template(name: str) -> Template:
    """Load a Jinja2 template from the prompts/templates directory.

    Args:
        name: Template filename (e.g. 'highlights_system.j2').

    Returns:
        Compiled Jinja2 Template.
    """
    return _jinja_env.get_template(name)


class AnalysisPrompt(BaseModel):
    """Template for a specific LLM analysis task.

    Decouples prompt content from inference transport. Adding a new
    analysis type requires only a new AnalysisPrompt instance, a pair
    of .j2 template files, and a Pydantic output model.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)
    task_id: str = Field(
        description="Unique identifier for this analysis type (e.g. 'highlights')."
    )
    system_template: Template = Field(description="Jinja2 template for the system prompt.")
    user_template: Template = Field(description="Jinja2 template for the user prompt.")
    output_model: type[BaseModel] = Field(
        description="Pydantic model class for parsing structured LLM output."
    )

    def render_system(self, **kwargs: object) -> str:
        """Render the system prompt template with the given variables.

        Args:
            **kwargs: Template variables.

        Returns:
            Rendered system prompt string.
        """
        return self.system_template.render(**kwargs)

    def render_user(self, **kwargs: object) -> str:
        """Render the user prompt template with the given variables.

        Args:
            **kwargs: Template variables.

        Returns:
            Rendered user prompt string.
        """
        return self.user_template.render(**kwargs)
