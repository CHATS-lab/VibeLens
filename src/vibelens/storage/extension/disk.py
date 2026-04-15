"""Disk-based extension storage for agents using SKILL.md format.

Directory layout (shared across all agents):
    <extensions_dir>/
    ├── my-skill/
    │   ├── SKILL.md         (YAML frontmatter + markdown body)
    │   ├── scripts/         (optional)
    │   ├── references/      (optional)
    │   └── agents/          (optional)
    └── another-skill/
        └── SKILL.md

Used directly for Claude Code, Codex CLI, Cursor, Gemini CLI, and all
other agents that follow the standard extensions/<name>/SKILL.md layout.
Subclassed by CentralExtensionStore (adds source metadata injection).
"""

import shutil
from pathlib import Path

import yaml

from vibelens.models.enums import AgentExtensionType
from vibelens.models.extension import (
    VALID_EXTENSION_NAME,
    ExtensionInfo,
    ExtensionSource,
    ExtensionSourceInfo,
)
from vibelens.storage.extension.base import BaseExtensionStore
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

# Required definition file inside each extension directory
SKILL_FILENAME = "SKILL.md"

# Optional subdirectories recognized inside an extension directory
KNOWN_SUBDIRS = ("scripts", "references", "agents", "assets")

# YAML frontmatter opening/closing marker in SKILL.md files
FRONTMATTER_DELIMITER = "---"


class DiskExtensionStore(BaseExtensionStore):
    """Concrete extension store backed by a directory of SKILL.md files.

    Constructor takes extensions_dir, source_type, and extension_type so any
    agent and extension type can be represented by a DiskExtensionStore instance.
    """

    def __init__(
        self,
        extensions_dir: Path,
        source_type: ExtensionSource,
        extension_type: AgentExtensionType = AgentExtensionType.SKILL,
    ) -> None:
        super().__init__()
        self._extensions_dir = extensions_dir.expanduser().resolve()
        self._source_type = source_type
        self._extension_type = extension_type

    @property
    def source_type(self) -> ExtensionSource:
        """Return the agent-specific source type."""
        return self._source_type

    @property
    def extensions_dir(self) -> Path:
        """Return the root directory for this store's extensions."""
        return self._extensions_dir

    @property
    def extension_type(self) -> AgentExtensionType:
        """Return the type of extensions this store manages."""
        return self._extension_type

    def list_extensions(self) -> list[ExtensionInfo]:
        """Scan extensions_dir and return metadata for all valid extension directories."""
        if not self._extensions_dir.is_dir():
            logger.debug("Extensions directory does not exist: %s", self._extensions_dir)
            return []

        extensions: list[ExtensionInfo] = []
        for entry in sorted(self._extensions_dir.iterdir()):
            if not entry.is_dir():
                continue
            name = entry.name
            if not VALID_EXTENSION_NAME.match(name):
                logger.debug("Skipping non-kebab-case dir: %s", name)
                continue
            skill_file = entry / SKILL_FILENAME
            if not skill_file.is_file():
                continue
            info = self._build_extension_info(name, entry, skill_file)
            if info:
                extensions.append(info)

        logger.debug("Scanned %d extensions from %s", len(extensions), self._extensions_dir)
        return extensions

    def get_extension(self, name: str) -> ExtensionInfo | None:
        """Look up a single extension by directory name."""
        if not VALID_EXTENSION_NAME.match(name):
            return None
        ext_dir = self._extensions_dir / name
        skill_file = ext_dir / SKILL_FILENAME
        if not skill_file.is_file():
            return None
        return self._build_extension_info(name, ext_dir, skill_file)

    def read_content(self, name: str) -> str | None:
        """Read the full SKILL.md content for a named extension."""
        skill_file = self._extensions_dir / name / SKILL_FILENAME
        if not skill_file.is_file():
            return None
        return skill_file.read_text(encoding="utf-8")

    def write_extension(self, name: str, content: str) -> Path:
        """Create or overwrite an extension's SKILL.md file.

        Args:
            name: Extension name (must be valid kebab-case).
            content: Full SKILL.md content including frontmatter.

        Returns:
            Absolute path to the written SKILL.md file.

        Raises:
            ValueError: If name is not valid kebab-case.
        """
        if not VALID_EXTENSION_NAME.match(name):
            raise ValueError(f"Extension name must be kebab-case: {name!r}")

        ext_dir = self._extensions_dir / name
        ext_dir.mkdir(parents=True, exist_ok=True)

        skill_file = ext_dir / SKILL_FILENAME
        # LLM-generated content often has excessive trailing newlines
        normalized = content.rstrip() + "\n"
        skill_file.write_text(normalized, encoding="utf-8")
        self.invalidate_cache()

        logger.info("Wrote extension %r to %s", name, skill_file)
        return skill_file

    def delete_extension(self, name: str) -> bool:
        """Remove an extension directory entirely."""
        ext_dir = self._extensions_dir / name
        if not ext_dir.is_dir():
            return False

        shutil.rmtree(ext_dir)
        self.invalidate_cache()

        logger.info("Deleted extension %r from %s", name, ext_dir)
        return True

    def _build_extension_info(
        self, name: str, ext_dir: Path, skill_file: Path
    ) -> ExtensionInfo | None:
        """Parse a SKILL.md and build ExtensionInfo metadata."""
        try:
            text = skill_file.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Cannot read %s: %s", skill_file, exc)
            return None

        frontmatter = parse_frontmatter(text)

        description = str(frontmatter.pop("description", ""))
        allowed_tools = parse_allowed_tools(frontmatter.pop("allowed-tools", None))
        frontmatter.pop("name", None)  # already using directory name

        return ExtensionInfo(
            name=name,
            extension_type=self._extension_type,
            description=description,
            sources=[ExtensionSourceInfo(source_type=self.source_type, source_path=str(ext_dir))],
            central_path=None,
            content_hash=ExtensionInfo.hash_content(text),
            metadata={
                **frontmatter,
                "allowed_tools": allowed_tools,
                "subdirs": detect_subdirs(ext_dir),
                "store_path": str(ext_dir),
                "line_count": text.count("\n") + 1,
            },
        )


def parse_frontmatter(text: str) -> dict:
    """Extract YAML frontmatter from a SKILL.md file.

    Expects the file to start with '---' followed by YAML, closed by '---'.
    Returns an empty dict if no valid frontmatter is found.
    """
    lines = text.split("\n")
    if not lines or lines[0].strip() != FRONTMATTER_DELIMITER:
        return {}

    end_idx = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == FRONTMATTER_DELIMITER:
            end_idx = i
            break

    if end_idx is None:
        return {}

    yaml_text = "\n".join(lines[1:end_idx])
    try:
        parsed = yaml.safe_load(yaml_text)
        return parsed if isinstance(parsed, dict) else {}
    except yaml.YAMLError as exc:
        logger.warning("Failed to parse YAML frontmatter: %s", exc)
        return {}


def parse_allowed_tools(raw: str | list | None) -> list[str]:
    """Normalize allowed-tools from frontmatter into a list of tool names.

    Handles both comma-separated strings and YAML lists.
    """
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(t).strip() for t in raw if str(t).strip()]
    return [t.strip() for t in str(raw).split(",") if t.strip()]


def detect_subdirs(ext_dir: Path) -> list[str]:
    """Return which KNOWN_SUBDIRS exist in the extension directory."""
    return [name for name in KNOWN_SUBDIRS if (ext_dir / name).is_dir()]


def extract_body(text: str) -> str:
    """Extract the markdown body after the YAML frontmatter.

    Leading blank lines between the closing ``---`` and the body content
    are stripped to prevent accumulation across repeated metadata injections.
    """
    if not text.startswith(FRONTMATTER_DELIMITER):
        return text
    end_idx = text.find(FRONTMATTER_DELIMITER, len(FRONTMATTER_DELIMITER))
    if end_idx < 0:
        return text
    return text[end_idx + len(FRONTMATTER_DELIMITER) :].lstrip("\n")
