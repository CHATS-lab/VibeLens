"""Central managed skill repository (~/.vibelens/skills/).

Acts as the authoritative skill store for VibeLens. Skills imported from
agent-native stores are copied here with source metadata injected into
the SKILL.md frontmatter so the UI can display where each skill
originated and which interfaces it can be synced to.
"""

from pathlib import Path

import yaml

from vibelens.models.skill import ExtensionInfo, ExtensionSource, ExtensionSourceInfo
from vibelens.storage.skill.base import BaseExtensionStore
from vibelens.storage.skill.disk import (
    FRONTMATTER_DELIMITER,
    SKILL_FILENAME,
    DiskExtensionStore,
    detect_subdirs,
    extract_body,
    parse_allowed_tools,
    parse_frontmatter,
)
from vibelens.utils.log import get_logger

logger = get_logger(__name__)


class CentralExtensionStore(DiskExtensionStore):
    """Central repository for VibeLens-managed skills.

    Extends DiskExtensionStore with source metadata injection and
    central-specific frontmatter fields (tags, sources).
    Creates its directory on init (unlike agent stores which are read-only).
    """

    def __init__(self, root_dir: Path) -> None:
        super().__init__(root_dir, ExtensionSource.CENTRAL)
        self._skills_dir.mkdir(parents=True, exist_ok=True)

    def _build_skill_info(
        self, name: str, skill_dir: Path, skill_file: Path
    ) -> ExtensionInfo | None:
        """Parse central SKILL.md with extra metadata (tags, sources)."""
        try:
            text = skill_file.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Cannot read %s: %s", skill_file, exc)
            return None

        frontmatter = parse_frontmatter(text)
        description = str(frontmatter.pop("description", ""))
        allowed_tools = parse_allowed_tools(frontmatter.pop("allowed-tools", None))
        tags = frontmatter.pop("tags", [])
        sources = _parse_sources(frontmatter.pop("sources", None))
        frontmatter.pop("skill_targets", None)
        frontmatter.pop("name", None)

        if not isinstance(tags, list):
            tags = []

        return ExtensionInfo(
            name=name,
            description=description,
            sources=sources,
            central_path=skill_dir,
            content_hash=ExtensionInfo.hash_content(text),
            metadata={
                **frontmatter,
                "allowed_tools": allowed_tools,
                "subdirs": detect_subdirs(skill_dir),
                "tags": [str(tag) for tag in tags if str(tag).strip()],
                "line_count": text.count("\n") + 1,
            },
        )

    def import_skill_from(
        self, source_store: "BaseExtensionStore", name: str, overwrite: bool = False
    ) -> ExtensionInfo | None:
        """Import a skill, injecting source provenance into frontmatter."""
        result = super().import_skill_from(source_store, name, overwrite=overwrite)
        if result is None:
            return None

        self._inject_source_metadata(name, source_store)
        self.invalidate_cache()
        return self.get_skill(name)

    def _inject_source_metadata(self, name: str, source_store: "BaseExtensionStore") -> None:
        """Add source_type and source_path to SKILL.md frontmatter."""
        skill_file = self._skills_dir / name / SKILL_FILENAME
        if not skill_file.is_file():
            return

        text = skill_file.read_text(encoding="utf-8")
        frontmatter = parse_frontmatter(text)

        new_source = {
            "source_type": str(source_store.source_type),
            "source_path": str(source_store.skill_path(name)),
        }

        # Merge with existing sources, avoiding duplicates by source_type
        existing_sources = frontmatter.get("sources", [])
        if not isinstance(existing_sources, list):
            existing_sources = []
        existing_types = {s.get("source_type") for s in existing_sources if isinstance(s, dict)}
        if new_source["source_type"] not in existing_types:
            existing_sources.append(new_source)
        frontmatter["sources"] = existing_sources

        # Rebuild SKILL.md with updated frontmatter
        body = extract_body(text)
        yaml_block = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True).rstrip()
        new_text = f"{FRONTMATTER_DELIMITER}\n{yaml_block}\n{FRONTMATTER_DELIMITER}\n\n{body}"
        skill_file.write_text(new_text.rstrip() + "\n", encoding="utf-8")


def _parse_sources(raw: object) -> list[ExtensionSourceInfo]:
    """Normalize persisted source metadata into ExtensionSourceInfo objects."""
    if not isinstance(raw, list):
        return []
    sources: list[ExtensionSourceInfo] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            sources.append(
                ExtensionSourceInfo(
                    source_type=ExtensionSource(item.get("source_type")),
                    source_path=str(item.get("source_path", "")),
                )
            )
        except Exception:
            continue
    return sources
