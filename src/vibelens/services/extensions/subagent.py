"""Subagent extension handler."""

from vibelens.services.extensions.base import FileBasedHandler


class SubagentHandler(FileBasedHandler):
    """Handler for subagent extensions.

    Subagents are skills with context: fork in frontmatter.
    Install as flat .md files inside the commands directory.
    """

    pass
