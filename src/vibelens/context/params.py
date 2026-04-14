"""Context extraction parameters — configurable detail levels for LLM prompts.

Defines ``ContextParams`` with four frozen presets controlling how session
trajectories are compressed into LLM-ready text. Each analysis mode selects
its own preset:

- **PRESET_RECOMMENDATION** — maximum compression for recommendation profile generation
- **PRESET_CONCISE** — tight truncation for quick overviews (skill retrieval)
- **PRESET_MEDIUM** — balanced detail for skill creation and evolvement
- **PRESET_DETAIL** — full detail for friction analysis (matches legacy defaults)
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ContextParams:
    """Configurable parameters for context extraction.

    Controls truncation limits, observation inclusion, and path display
    when compressing trajectories into LLM prompt text.
    """

    # -- User prompt truncation --
    # Max total chars for a user message before head/tail splitting
    user_prompt_max_chars: int
    # Number of chars to keep from the start when truncating
    user_prompt_head_chars: int
    # Number of chars to keep from the end when truncating
    user_prompt_tail_chars: int

    # -- Tool argument display --
    # Max chars for Bash command arguments
    bash_command_max_chars: int
    # Max chars for non-Bash tool argument values
    tool_arg_max_chars: int

    # -- Error and observation truncation --
    # Max chars for error observation content
    error_truncate_chars: int
    # Whether to include non-error tool output in context
    include_non_error_obs: bool
    # Max chars for non-error output (ignored when include_non_error_obs is False)
    observation_max_chars: int

    # -- Agent message truncation --
    # Max total chars for an agent text message before head/tail splitting (0 = skip)
    agent_message_max_chars: int
    # Number of chars to keep from the start when truncating
    agent_message_head_chars: int
    # Number of chars to keep from the end when truncating
    agent_message_tail_chars: int

    # -- Path display --
    # Replace $HOME prefix with ~ for shorter file paths
    shorten_home_prefix: bool
    # Keep only the last N path segments (0 = show full path)
    path_max_segments: int


# Maximum compression for recommendation profile generation
PRESET_RECOMMENDATION = ContextParams(
    user_prompt_max_chars=500,
    user_prompt_head_chars=400,
    user_prompt_tail_chars=100,
    bash_command_max_chars=0,
    tool_arg_max_chars=0,
    error_truncate_chars=200,
    include_non_error_obs=False,
    observation_max_chars=0,
    agent_message_max_chars=0,
    agent_message_head_chars=0,
    agent_message_tail_chars=0,
    shorten_home_prefix=True,
    path_max_segments=2,
)

# Tight truncation for quick overviews (skill retrieval)
PRESET_CONCISE = ContextParams(
    user_prompt_max_chars=800,
    user_prompt_head_chars=600,
    user_prompt_tail_chars=200,
    bash_command_max_chars=120,
    tool_arg_max_chars=80,
    error_truncate_chars=300,
    include_non_error_obs=False,
    observation_max_chars=0,
    agent_message_max_chars=200,
    agent_message_head_chars=150,
    agent_message_tail_chars=50,
    shorten_home_prefix=True,
    path_max_segments=2,
)

# Balanced detail for skill creation and evolvement proposal
PRESET_MEDIUM = ContextParams(
    user_prompt_max_chars=1500,
    user_prompt_head_chars=1100,
    user_prompt_tail_chars=400,
    bash_command_max_chars=160,
    tool_arg_max_chars=120,
    error_truncate_chars=600,
    include_non_error_obs=False,
    observation_max_chars=0,
    agent_message_max_chars=500,
    agent_message_head_chars=350,
    agent_message_tail_chars=150,
    shorten_home_prefix=True,
    path_max_segments=3,
)

# Full detail for friction analysis and skill creation and evolvement
PRESET_DETAIL = ContextParams(
    user_prompt_max_chars=2000,
    user_prompt_head_chars=1500,
    user_prompt_tail_chars=500,
    bash_command_max_chars=200,
    tool_arg_max_chars=200,
    error_truncate_chars=1000,
    include_non_error_obs=True,
    observation_max_chars=150,
    agent_message_max_chars=800,
    agent_message_head_chars=600,
    agent_message_tail_chars=200,
    shorten_home_prefix=True,
    path_max_segments=4,
)
