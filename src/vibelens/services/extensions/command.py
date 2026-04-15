"""Command extension handler (legacy flat .md format)."""

from vibelens.services.extensions.base import FileBasedHandler


class CommandHandler(FileBasedHandler):
    """Handler for command extensions (legacy format).

    Commands install as flat .md files in the commands directory.
    """

    pass
