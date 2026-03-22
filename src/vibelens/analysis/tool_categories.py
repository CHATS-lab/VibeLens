"""Tool category mapping for session analytics modules.

Keep in sync with frontend/src/components/conversation/flow-layout.ts
which maintains a parallel TypeScript version of this mapping.
"""

# Maps tool function names to semantic categories used by phase detection
# and tool graph construction. Covers all tool names across Claude Code,
# Codex, and Gemini agent formats.
TOOL_CATEGORY_MAP: dict[str, str] = {
    "Read": "file_read",
    "read_file": "file_read",
    "cat": "file_read",
    "Glob": "search",
    "glob": "search",
    "Grep": "search",
    "grep": "search",
    "find": "search",
    "Edit": "file_write",
    "Write": "file_write",
    "write_file": "file_write",
    "NotebookEdit": "file_write",
    "MultiEdit": "file_write",
    "apply_patch": "file_write",
    "apply-patch": "file_write",
    "Bash": "shell",
    "bash": "shell",
    "shell": "shell",
    "execute_command": "shell",
    "WebSearch": "web",
    "WebFetch": "web",
    "web_search": "web",
    "Agent": "agent",
    "Task": "agent",
    "Skill": "agent",
}
