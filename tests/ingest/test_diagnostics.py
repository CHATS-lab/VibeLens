"""Tests for vibelens.ingest.diagnostics — parse quality tracking."""

from vibelens.ingest.diagnostics import MAX_WARNINGS, DiagnosticsCollector


# ─── DiagnosticsCollector
class TestDiagnosticsCollector:
    def test_initial_state(self):
        collector = DiagnosticsCollector()
        assert collector.skipped_lines == 0
        assert collector.orphaned_tool_calls == 0
        assert collector.orphaned_tool_results == 0
        assert collector.total_lines == 0
        assert collector.parsed_lines == 0
        assert collector.warnings == []

    def test_record_skip(self):
        collector = DiagnosticsCollector()
        collector.record_skip("malformed JSON")
        assert collector.skipped_lines == 1
        assert len(collector.warnings) == 1
        assert "malformed JSON" in collector.warnings[0]
        print(f"  warning: {collector.warnings[0]}")

    def test_record_orphaned_call(self):
        collector = DiagnosticsCollector()
        collector.record_orphaned_call("tc_001")
        assert collector.orphaned_tool_calls == 1
        assert "tc_001" in collector.warnings[0]

    def test_record_orphaned_result(self):
        collector = DiagnosticsCollector()
        collector.record_orphaned_result("tr_001")
        assert collector.orphaned_tool_results == 1
        assert "tr_001" in collector.warnings[0]

    def test_record_tool_call(self):
        collector = DiagnosticsCollector()
        collector.record_tool_call()
        collector.record_tool_call()
        assert collector._total_tool_calls == 2

    def test_record_tool_result(self):
        collector = DiagnosticsCollector()
        collector.record_tool_result()
        assert collector._total_tool_results == 1


# ─── Warnings cap
class TestWarningsCap:
    def test_warnings_capped_at_max(self):
        collector = DiagnosticsCollector()
        for i in range(MAX_WARNINGS + 10):
            collector.record_skip(f"line {i}")
        assert len(collector.warnings) == MAX_WARNINGS
        assert collector.skipped_lines == MAX_WARNINGS + 10
        print(f"  skipped={collector.skipped_lines}, warnings={len(collector.warnings)}")


# ─── Completeness score
class TestComputeScore:
    def test_perfect_score(self):
        """No skips or orphans → score 1.0."""
        collector = DiagnosticsCollector()
        collector.total_lines = 100
        collector.parsed_lines = 100
        collector.record_tool_call()
        collector.record_tool_result()
        score = collector.compute_score()
        assert score == 1.0
        print(f"  perfect score: {score}")

    def test_all_skipped(self):
        """All lines skipped → score reduced by 0.5."""
        collector = DiagnosticsCollector()
        collector.total_lines = 10
        collector.skipped_lines = 10
        score = collector.compute_score()
        assert score <= 0.5
        print(f"  all skipped: {score}")

    def test_orphaned_calls_reduce_score(self):
        collector = DiagnosticsCollector()
        collector.total_lines = 10
        collector._total_tool_calls = 10
        collector.orphaned_tool_calls = 5
        score = collector.compute_score()
        assert score < 1.0
        print(f"  orphaned calls: {score}")

    def test_orphaned_results_reduce_score(self):
        collector = DiagnosticsCollector()
        collector.total_lines = 10
        collector._total_tool_results = 10
        collector.orphaned_tool_results = 5
        score = collector.compute_score()
        assert score < 1.0
        print(f"  orphaned results: {score}")

    def test_score_clamped_to_zero(self):
        """Extreme values don't produce negative scores."""
        collector = DiagnosticsCollector()
        collector.total_lines = 1
        collector.skipped_lines = 100
        collector._total_tool_calls = 1
        collector.orphaned_tool_calls = 100
        collector._total_tool_results = 1
        collector.orphaned_tool_results = 100
        score = collector.compute_score()
        assert score == 0.0

    def test_zero_totals_no_division_error(self):
        """Zero totals use max(total, 1) to avoid ZeroDivisionError."""
        collector = DiagnosticsCollector()
        score = collector.compute_score()
        assert score == 1.0


# ─── to_diagnostics
class TestToDiagnostics:
    def test_produces_parse_diagnostics(self):
        collector = DiagnosticsCollector()
        collector.total_lines = 50
        collector.parsed_lines = 45
        collector.skipped_lines = 5
        collector.orphaned_tool_calls = 2
        collector._total_tool_calls = 10

        diag = collector.to_diagnostics()
        assert diag.skipped_lines == 5
        assert diag.orphaned_tool_calls == 2
        assert diag.orphaned_tool_results == 0
        assert diag.completeness_score is not None
        assert 0.0 <= diag.completeness_score <= 1.0
        print(f"  diagnostics: skipped={diag.skipped_lines}, score={diag.completeness_score:.3f}")
