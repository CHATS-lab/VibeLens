"""Parse diagnostics collection for tracking data quality during ingestion."""

from vibelens.models.session import ParseDiagnostics

MAX_WARNINGS = 20


class DiagnosticsCollector:
    """Accumulates parsing quality metrics during session ingestion.

    Tracks skipped lines, orphaned tool calls/results, and produces
    a completeness score that quantifies how much data survived parsing.
    """

    def __init__(self) -> None:
        self.skipped_lines: int = 0
        self.orphaned_tool_calls: int = 0
        self.orphaned_tool_results: int = 0
        self.total_lines: int = 0
        self.parsed_lines: int = 0
        self._total_tool_calls: int = 0
        self._total_tool_results: int = 0
        self.warnings: list[str] = []

    def record_skip(self, reason: str) -> None:
        """Record a skipped line with an explanation.

        Args:
            reason: Why the line was skipped.
        """
        self.skipped_lines += 1
        if len(self.warnings) < MAX_WARNINGS:
            self.warnings.append(f"skip: {reason}")

    def record_orphaned_call(self, tool_call_id: str) -> None:
        """Record a tool_use block with no matching tool_result.

        Args:
            tool_call_id: The unmatched tool_use ID.
        """
        self.orphaned_tool_calls += 1
        if len(self.warnings) < MAX_WARNINGS:
            self.warnings.append(f"orphaned call: {tool_call_id}")

    def record_orphaned_result(self, tool_use_id: str) -> None:
        """Record a tool_result block with no matching tool_use.

        Args:
            tool_use_id: The unmatched tool_result ID.
        """
        self.orphaned_tool_results += 1
        if len(self.warnings) < MAX_WARNINGS:
            self.warnings.append(f"orphaned result: {tool_use_id}")

    def record_tool_call(self) -> None:
        """Increment total tool call count."""
        self._total_tool_calls += 1

    def record_tool_result(self) -> None:
        """Increment total tool result count."""
        self._total_tool_results += 1

    def compute_score(self) -> float:
        """Compute a completeness score from 0.0 (poor) to 1.0 (perfect).

        Returns:
            Clamped float score.
        """
        total = max(self.total_lines, 1)
        total_calls = max(self._total_tool_calls, 1)
        total_results = max(self._total_tool_results, 1)
        score = (
            1.0
            - (self.skipped_lines / total) * 0.5
            - (self.orphaned_tool_calls / total_calls) * 0.3
            - (self.orphaned_tool_results / total_results) * 0.2
        )
        return max(0.0, min(1.0, score))

    def to_diagnostics(self) -> ParseDiagnostics:
        """Convert collected metrics into a ParseDiagnostics model.

        Returns:
            Populated ParseDiagnostics instance.
        """
        return ParseDiagnostics(
            skipped_lines=self.skipped_lines,
            orphaned_tool_calls=self.orphaned_tool_calls,
            orphaned_tool_results=self.orphaned_tool_results,
            completeness_score=self.compute_score(),
        )
