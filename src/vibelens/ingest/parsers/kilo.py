"""Kilo session parser.

Kilo (https://github.com/Kilo-Org/kilocode) is a fork of OpenCode and uses
an identical Drizzle SQLite schema. The only on-disk differences observed:

- Database file is ``kilo.db`` at ``~/.local/share/kilo/`` rather than
  ``opencode.db`` at ``~/.local/share/opencode/``.
- ``project.icon_url_override`` column does not exist in kilo (the
  OpencodeParser tolerates this).
- ``message.data.editorContext`` is populated per message in kilo (OpenCode
  never populates it). OpencodeParser captures it opportunistically into
  ``Step.extra.editor_context``, so KiloParser inherits this for free with
  no ``_build_steps`` override.

Capability vs Claude reference parser: identical to OpenCode (see
``opencode.py`` docstring) since Kilo inherits every parsing method.
The same gaps apply — multi-level sub-agent recursion, non-image file
attachments — and are tracked there.
"""

from pathlib import Path

from vibelens.ingest.parsers.opencode import OpencodeParser
from vibelens.models.enums import AgentType


class KiloParser(OpencodeParser):
    """Parser for Kilo's SQLite session database (OpenCode fork)."""

    AGENT_TYPE = AgentType.KILO
    LOCAL_DATA_DIR: Path | None = Path.home() / ".local" / "share" / "kilo"
    DB_FILENAME = "kilo.db"
