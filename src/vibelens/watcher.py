"""File watcher for local Claude Code session changes."""


async def watch_sessions() -> None:
    """Watch ~/.claude for session file changes and emit events.

    Uses watchfiles to monitor JSONL history files.
    Not yet implemented.
    """
    raise NotImplementedError
