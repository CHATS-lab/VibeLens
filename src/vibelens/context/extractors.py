"""Concrete context extractor implementations.

Provides three subclasses of ContextExtractor, each targeting a different
analysis use case:

- **MetadataExtractor** — metadata header + first user prompt only.
  Concise compression for recommendation profile generation.
- **SummaryExtractor** — uses compaction summaries as TLDRs when available.
  Falls back to all user prompts when no compaction agents exist.
- **DetailExtractor** — full step-by-step detail with tool calls and
  error observations. Used for friction analysis and deep inspection.
"""

from vibelens.context.base import (
    ContextExtractor,
    _format_steps_available,
    _IndexTracker,
)
from vibelens.context.formatter import (
    build_metadata_block,
    format_agent_message,
    format_user_prompt,
    summarize_tool_args,
)
from vibelens.context.params import PRESET_CONCISE, PRESET_MEDIUM, ContextParams
from vibelens.models.context import SessionContext
from vibelens.models.enums import StepSource
from vibelens.models.trajectories import Trajectory
from vibelens.models.trajectories.step import Step
from vibelens.utils.content import content_to_text


class MetadataExtractor(ContextExtractor):
    """Extracts only the metadata block and first user prompt.

    Designed for recommendation profile generation where concise compression
    is required. Ignores compaction agents entirely.
    """

    def __init__(self, params: ContextParams = PRESET_CONCISE) -> None:
        """Store extraction parameters.

        Args:
            params: Context extraction parameters. Defaults to PRESET_CONCISE.
        """
        super().__init__(params=params)

    def extract(
        self, trajectory_group: list[Trajectory], session_index: int | None = None
    ) -> SessionContext:
        """Extract metadata block and first user prompt only.

        Skips compaction handling entirely. Returns a SessionContext with
        a compact representation suitable for recommendation generation.

        Args:
            trajectory_group: All trajectories for one session.
            session_index: Optional 0-based index within the analysis batch.

        Returns:
            SessionContext with metadata header and first prompt only.
        """
        main = self._find_main_trajectory(trajectory_group)
        tracker = _IndexTracker()

        header = build_metadata_block(main, session_index=session_index)
        first_prompt = self._find_first_user_prompt(main)
        prompt_block = f"FIRST PROMPT: {first_prompt}" if first_prompt else ""

        parts = [header]
        if prompt_block:
            parts.append(prompt_block)
        full_text = "\n\n".join(parts)

        return SessionContext(
            session_id=main.session_id,
            project_path=main.project_path,
            context_text=full_text,
            trajectory_group=trajectory_group,
            prev_trajectory_ref_id=(
                main.prev_trajectory_ref.session_id if main.prev_trajectory_ref else None
            ),
            next_trajectory_ref_id=(
                main.next_trajectory_ref.session_id if main.next_trajectory_ref else None
            ),
            timestamp=main.timestamp,
            session_index=session_index,
            step_index2id=tracker.index_to_real_id,
        )

    def _find_first_user_prompt(self, main: Trajectory) -> str:
        """Find and format the first user prompt in the trajectory.

        Args:
            main: The main trajectory to search.

        Returns:
            Truncated first user message, or empty string if none found.
        """
        for step in main.steps:
            if step.source == StepSource.USER:
                text = content_to_text(step.message).strip()
                if text:
                    return format_user_prompt(text, self.params)
        return ""

    def format_step(self, step: Step, tracker: _IndexTracker) -> str:
        """Not used — MetadataExtractor overrides extract() directly."""
        return ""


class SummaryExtractor(ContextExtractor):
    """Extracts metadata, first prompt, and compaction summary or all user prompts.

    Uses the compaction-as-TLDR strategy: when compaction agents are present,
    shows only the latest compaction summary instead of step-by-step content.
    Falls back to all user prompts when no compaction agents exist.
    """

    def __init__(self, params: ContextParams = PRESET_MEDIUM) -> None:
        """Store extraction parameters.

        Args:
            params: Context extraction parameters. Defaults to PRESET_MEDIUM.
        """
        super().__init__(params=params)

    def extract(
        self, trajectory_group: list[Trajectory], session_index: int | None = None
    ) -> SessionContext:
        """Extract context using compaction-as-TLDR strategy.

        Always emits indexed user prompts so every session has a populated
        step_index2id (and the LLM has real indices to reference). With
        compaction agents, also appends the latest compaction summary as
        a TLDR block.

        Args:
            trajectory_group: All trajectories for one session.
            session_index: Optional 0-based index within the analysis batch.

        Returns:
            SessionContext with summary-level context text.
        """
        main = self._find_main_trajectory(trajectory_group)
        compaction_agents = self._find_compaction_agents(trajectory_group)
        tracker = _IndexTracker()

        header = build_metadata_block(main, session_index=session_index)
        first_prompt = self._find_first_user_prompt(main)

        parts = [header]
        if first_prompt:
            parts.append(f"FIRST PROMPT: {first_prompt}")

        user_prompts_block = self._format_all_user_prompts(main, tracker)
        if user_prompts_block:
            parts.append(user_prompts_block)

        if compaction_agents:
            summary = self._get_latest_compaction_summary(compaction_agents)
            if summary:
                parts.append("--- COMPACTION SUMMARY (latest) ---")
                parts.append(summary)

        steps_available_line = _format_steps_available(tracker)
        if steps_available_line:
            parts.insert(1, steps_available_line)

        full_text = "\n\n".join(parts)

        return SessionContext(
            session_id=main.session_id,
            project_path=main.project_path,
            context_text=full_text,
            trajectory_group=trajectory_group,
            prev_trajectory_ref_id=(
                main.prev_trajectory_ref.session_id if main.prev_trajectory_ref else None
            ),
            next_trajectory_ref_id=(
                main.next_trajectory_ref.session_id if main.next_trajectory_ref else None
            ),
            timestamp=main.timestamp,
            session_index=session_index,
            step_index2id=tracker.index_to_real_id,
        )

    def format_step(self, step: Step, tracker: _IndexTracker) -> str:
        """Format user prompts only — used in the no-compaction fallback path.

        Args:
            step: The trajectory step to format.
            tracker: Index tracker for sequential step numbering.

        Returns:
            Formatted user prompt line, or empty string to skip.
        """
        if step.source != StepSource.USER:
            return ""
        text = content_to_text(step.message).strip()
        if not text:
            return ""
        idx = tracker.assign(step.step_id)
        truncated = format_user_prompt(text, self.params)
        return f"[step_id={idx}] USER: {truncated}"

    def _find_first_user_prompt(self, main: Trajectory) -> str:
        """Find and format the first user prompt in the trajectory.

        Args:
            main: The main trajectory to search.

        Returns:
            Truncated first user message, or empty string if none found.
        """
        for step in main.steps:
            if step.source == StepSource.USER:
                text = content_to_text(step.message).strip()
                if text:
                    return format_user_prompt(text, self.params)
        return ""

    def _get_latest_compaction_summary(self, compaction_agents: list[Trajectory]) -> str:
        """Get the AGENT step summary from the last compaction agent.

        Args:
            compaction_agents: Compaction sub-agents sorted by timestamp.

        Returns:
            Summary text from the last compaction agent's first AGENT step.
        """
        for agent in reversed(compaction_agents):
            for step in agent.steps:
                if step.source == StepSource.AGENT:
                    summary = content_to_text(step.message).strip()
                    if summary:
                        return summary
        return ""

    def _format_all_user_prompts(self, main: Trajectory, tracker: _IndexTracker) -> str:
        """Format all user prompts as a block of indexed lines.

        Args:
            main: The main trajectory.
            tracker: Index tracker for sequential step numbering.

        Returns:
            All non-empty user prompts joined by double newlines.
        """
        return self._format_all_steps(main.steps, tracker)


class DetailExtractor(ContextExtractor):
    """Full detail extractor with step-by-step formatting and compaction interleaving.

    Includes user prompts, agent messages, tool calls, error observations,
    and optional non-error observations. Uses the base class extract() method
    as-is for compaction interleaving.
    """

    def __init__(self, params: ContextParams = PRESET_MEDIUM) -> None:
        """Store extraction parameters.

        Args:
            params: Context extraction parameters. Defaults to PRESET_MEDIUM.
        """
        super().__init__(params=params)

    def format_step(self, step: Step, tracker: _IndexTracker) -> str:
        """Format a step with full detail: user prompt, agent message, tools, errors.

        - USER steps: truncated prompt with step_id.
        - AGENT steps: truncated message + TOOL lines + ERROR/RESULT observations.
          Omitted if the agent step has no meaningful content beyond the header.
        - SYSTEM steps: skipped entirely.

        Args:
            step: The trajectory step to format.
            tracker: Index tracker for sequential step numbering.

        Returns:
            Formatted step string, or empty string to omit.
        """
        if step.source == StepSource.USER:
            return self._format_user_step(step, tracker)
        if step.source == StepSource.AGENT:
            return self._format_agent_step(step, tracker)
        return ""

    def _format_user_step(self, step: Step, tracker: _IndexTracker) -> str:
        """Format a USER step with truncated prompt and sequential index.

        Args:
            step: A USER step.
            tracker: Index tracker.

        Returns:
            Formatted USER line, or empty string if message is blank.
        """
        message = content_to_text(step.message).strip()
        if not message:
            return ""
        idx = tracker.assign(step.step_id)
        truncated = format_user_prompt(message, self.params)
        return f"[step_id={idx}] USER: {truncated}"

    def _format_agent_step(self, step: Step, tracker: _IndexTracker) -> str:
        """Format an AGENT step with message, tool calls, and observations.

        Skips the step if it has no displayable content (empty message,
        no tool calls, no observations).

        Args:
            step: An AGENT step.
            tracker: Index tracker.

        Returns:
            Formatted AGENT block, or empty string if no content.
        """
        idx = tracker.assign(step.step_id)
        message = content_to_text(step.message).strip()
        truncated_msg = format_agent_message(message, self.params)
        agent_lines = [f"[step_id={idx}] AGENT: {truncated_msg}"]

        for tc in step.tool_calls:
            tool_summary = summarize_tool_args(tc.function_name, tc.arguments, self.params)
            agent_lines.append(f"  TOOL: fn={tc.function_name} {tool_summary}")

        # Include only if there's something beyond the header line
        if len(agent_lines) > 1:
            return "\n".join(agent_lines)
        return ""
