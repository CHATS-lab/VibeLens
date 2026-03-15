"""Tests for vibelens.ingest.tool_normalizers — tool categorisation and summary."""

from vibelens.ingest.tool_normalizers import (
    MAX_OUTPUT_DIGEST_LENGTH,
    TOOL_CATEGORY_MAP,
    categorize_tool,
    summarize_tool_input,
    summarize_tool_output,
)


class TestCategorizeTool:
    """Tests for categorize_tool mapping tool names to categories."""

    def test_file_read_tools(self):
        assert categorize_tool("Read") == "file_read"
        assert categorize_tool("read_file") == "file_read"
        assert categorize_tool("cat") == "file_read"

    def test_file_write_tools(self):
        assert categorize_tool("Edit") == "file_write"
        assert categorize_tool("Write") == "file_write"
        assert categorize_tool("write_file") == "file_write"
        assert categorize_tool("NotebookEdit") == "file_write"
        assert categorize_tool("MultiEdit") == "file_write"
        assert categorize_tool("apply_patch") == "file_write"
        assert categorize_tool("apply-patch") == "file_write"

    def test_shell_tools(self):
        assert categorize_tool("Bash") == "shell"
        assert categorize_tool("bash") == "shell"
        assert categorize_tool("shell") == "shell"
        assert categorize_tool("execute_command") == "shell"

    def test_search_tools(self):
        assert categorize_tool("Glob") == "search"
        assert categorize_tool("glob") == "search"
        assert categorize_tool("Grep") == "search"
        assert categorize_tool("grep") == "search"
        assert categorize_tool("find") == "search"

    def test_web_tools(self):
        assert categorize_tool("WebSearch") == "web"
        assert categorize_tool("WebFetch") == "web"
        assert categorize_tool("web_search") == "web"

    def test_agent_tools(self):
        assert categorize_tool("Agent") == "agent"
        assert categorize_tool("Skill") == "agent"
        assert categorize_tool("TodoWrite") == "agent"
        assert categorize_tool("TaskCreate") == "agent"
        assert categorize_tool("TaskUpdate") == "agent"

    def test_unknown_tool_defaults_to_other(self):
        assert categorize_tool("CustomTool") == "other"
        assert categorize_tool("UnknownWidget") == "other"

    def test_empty_tool_name(self):
        assert categorize_tool("") == "other"

    def test_all_map_entries_covered(self):
        """Every entry in TOOL_CATEGORY_MAP has a valid category."""
        valid_categories = {"file_read", "file_write", "shell", "search", "web", "agent", "other"}
        for tool_name, category in TOOL_CATEGORY_MAP.items():
            assert category in valid_categories, f"{tool_name} has invalid category: {category}"


class TestSummarizeToolInput:
    """Tests for summarize_tool_input extracting key info from tool args."""

    def test_read_tool_file_path(self):
        result = summarize_tool_input("Read", {"file_path": "/src/main.py"})
        assert result == "/src/main.py"

    def test_bash_tool_command(self):
        result = summarize_tool_input("Bash", {"command": "ls -la"})
        assert result == "ls -la"

    def test_grep_tool_pattern(self):
        result = summarize_tool_input("Grep", {"pattern": "TODO", "path": "/src"})
        assert result == "TODO"

    def test_glob_tool_pattern(self):
        result = summarize_tool_input("Glob", {"pattern": "**/*.py"})
        assert result == "**/*.py"

    def test_websearch_query(self):
        result = summarize_tool_input("WebSearch", {"query": "python async patterns"})
        assert result == "python async patterns"

    def test_webfetch_url(self):
        result = summarize_tool_input("WebFetch", {"url": "https://example.com"})
        assert result == "https://example.com"

    def test_agent_description(self):
        inputs = {"description": "Search codebase", "prompt": "find bugs"}
        result = summarize_tool_input("Agent", inputs)
        assert result == "Search codebase"

    def test_agent_prompt_fallback(self):
        result = summarize_tool_input("Agent", {"prompt": "find bugs"})
        assert result == "find bugs"

    def test_edit_tool_file_path(self):
        result = summarize_tool_input("Edit", {"file_path": "/src/utils.py", "old_string": "x"})
        assert result == "/src/utils.py"

    def test_write_file_path(self):
        result = summarize_tool_input("write_file", {"path": "/tmp/out.txt", "content": "data"})
        assert result == "/tmp/out.txt"

    def test_none_input(self):
        assert summarize_tool_input("Read", None) == ""

    def test_string_input(self):
        result = summarize_tool_input("Bash", "ls -la")
        assert result == "ls -la"

    def test_non_dict_non_string_input(self):
        assert summarize_tool_input("Read", 12345) == ""

    def test_unknown_tool_falls_back_to_first_string(self):
        result = summarize_tool_input("CustomTool", {"some_key": "some_value"})
        assert result == "some_value"

    def test_unknown_tool_empty_dict(self):
        result = summarize_tool_input("CustomTool", {})
        assert result == ""

    def test_unknown_tool_non_string_values(self):
        result = summarize_tool_input("CustomTool", {"count": 42, "flag": True})
        assert result == ""

    def test_long_value_truncated(self):
        long_path = "/very/long/" + "x" * 200
        result = summarize_tool_input("Read", {"file_path": long_path})
        assert len(result) == 120

    def test_long_string_input_truncated(self):
        long_cmd = "echo " + "x" * 200
        result = summarize_tool_input("Bash", long_cmd)
        assert len(result) == 120

    def test_whitespace_only_value_skipped(self):
        """Values that are only whitespace are skipped."""
        result = summarize_tool_input("CustomTool", {"key": "   ", "other": "valid"})
        assert result == "valid"

    def test_empty_string_value_skipped(self):
        """Empty string values are skipped."""
        result = summarize_tool_input("Read", {"file_path": "", "other": "/backup.py"})
        assert result == "/backup.py"

    def test_shell_tool_lowercase(self):
        """Lowercase shell tool name works."""
        result = summarize_tool_input("shell", {"command": "git status"})
        assert result == "git status"

    def test_notebook_edit(self):
        result = summarize_tool_input("NotebookEdit", {"notebook_path": "/analysis.ipynb"})
        assert result == "/analysis.ipynb"


# ─── summarize_tool_output
class TestSummarizeToolOutput:
    def test_none_output(self):
        assert summarize_tool_output("Read", None, False) == ""

    def test_error_output(self):
        result = summarize_tool_output("Bash", "FileNotFoundError: /missing.py", True)
        assert result.startswith("ERROR:")
        assert "FileNotFoundError" in result
        print(f"  error digest: {result}")

    def test_error_multiline(self):
        output = "Permission denied\nSome extra detail\nMore"
        result = summarize_tool_output("Bash", output, True)
        assert result.startswith("ERROR: Permission denied")
        assert "extra detail" not in result

    def test_file_read_lines(self):
        output = "line1\nline2\nline3\n"
        result = summarize_tool_output("Read", output, False)
        assert result == "3 lines"
        print(f"  file_read digest: {result}")

    def test_search_matches(self):
        output = "file1.py:10: match\nfile2.py:20: match\n"
        result = summarize_tool_output("Grep", output, False)
        assert "matches" in result

    def test_file_write_applied(self):
        result = summarize_tool_output("Edit", "ok", False)
        assert result == "applied"

    def test_web_fetch_chars(self):
        output = "x" * 500
        result = summarize_tool_output("WebFetch", output, False)
        assert "fetched" in result
        assert "500" in result

    def test_shell_success_lines(self):
        output = "output line 1\noutput line 2\n"
        result = summarize_tool_output("Bash", output, False)
        assert "lines" in result

    def test_error_truncated_at_max_length(self):
        long_error = "E" * 300
        result = summarize_tool_output("Bash", long_error, True)
        assert len(result) <= MAX_OUTPUT_DIGEST_LENGTH

    def test_empty_string_output(self):
        result = summarize_tool_output("Bash", "", False)
        assert isinstance(result, str)
