"""Parse claude-code-templates components directory."""

import json
from pathlib import Path

from vibelens.catalog.frontmatter import extract_tags, parse_frontmatter
from vibelens.models.recommendation.catalog import CatalogItem, ItemType

SOURCE_PREFIX = "cct"
DEFAULT_PLATFORMS = ["claude_code"]
COMPONENTS_REL = Path("cli-tool") / "components"
EXCLUDED_DIRS = {"settings"}

DIR_TYPE_MAP: dict[str, tuple[ItemType, str]] = {
    "agents": (ItemType.SUBAGENT, "agent"),
    "commands": (ItemType.COMMAND, "command"),
    "skills": (ItemType.SKILL, "skill"),
}


def parse_templates(hub_dir: Path) -> list[CatalogItem]:
    """Parse all items from a claude-code-templates hub directory.

    Args:
        hub_dir: Path to the claude-code-templates directory.

    Returns:
        List of CatalogItem instances.
    """
    comp_dir = hub_dir / COMPONENTS_REL
    if not comp_dir.is_dir():
        return []

    items: list[CatalogItem] = []
    for subdir in sorted(comp_dir.iterdir()):
        if not subdir.is_dir() or subdir.name in EXCLUDED_DIRS:
            continue
        if subdir.name in DIR_TYPE_MAP:
            item_type, type_label = DIR_TYPE_MAP[subdir.name]
            items.extend(_parse_md_components(subdir, item_type, type_label))
        elif subdir.name == "hooks":
            items.extend(_parse_hook_components(subdir))
        elif subdir.name == "mcps":
            items.extend(_parse_mcp_components(subdir))
    return items


def _parse_md_components(
    base_dir: Path, item_type: ItemType, type_label: str
) -> list[CatalogItem]:
    """Parse Markdown components (agents, commands, skills).

    Args:
        base_dir: Base directory for the component type (e.g., agents/, skills/).
        item_type: ItemType to assign to each parsed item.
        type_label: Short label used in item_id (e.g. "agent", "skill").

    Returns:
        List of CatalogItem instances.
    """
    items: list[CatalogItem] = []

    if item_type == ItemType.SKILL:
        for skill_md in sorted(base_dir.glob("*/SKILL.md")):
            item = _md_to_item(skill_md, item_type, type_label, category=skill_md.parent.name)
            if item:
                items.append(item)
        return items

    for md_file in sorted(base_dir.glob("**/*.md")):
        category = md_file.parent.name if md_file.parent != base_dir else "uncategorized"
        item = _md_to_item(md_file, item_type, type_label, category=category)
        if item:
            items.append(item)
    return items


def _md_to_item(
    md_path: Path,
    item_type: ItemType,
    type_label: str,
    category: str = "uncategorized",
) -> CatalogItem | None:
    """Convert a Markdown file with frontmatter to CatalogItem.

    Args:
        md_path: Path to the Markdown file.
        item_type: ItemType to assign.
        type_label: Short label used in item_id (e.g. "agent", "command").
        category: Fallback category if not in frontmatter.

    Returns:
        CatalogItem if description is present, else None.
    """
    try:
        content = md_path.read_text(encoding="utf-8")
    except OSError:
        return None

    meta, _body = parse_frontmatter(content)
    name = meta.get("name") or md_path.stem
    description = meta.get("description") or ""
    if not description:
        return None

    fm_category = meta.get("category") or category
    item_id = f"{SOURCE_PREFIX}:{type_label}:{name}"

    return CatalogItem(
        item_id=item_id,
        item_type=item_type,
        name=name,
        description=description,
        tags=extract_tags(meta),
        category=fm_category,
        platforms=DEFAULT_PLATFORMS,
        quality_score=0.0,
        popularity=0.0,
        updated_at="",
        source_url="",
        repo_full_name="",
        install_method="skill_file",
        install_content=content,
    )


def _parse_hook_components(hooks_dir: Path) -> list[CatalogItem]:
    """Parse hooks/{category}/{name}.json files.

    Args:
        hooks_dir: Path to the hooks/ component directory.

    Returns:
        List of CatalogItem instances with ItemType.HOOK.
    """
    items: list[CatalogItem] = []
    for json_file in sorted(hooks_dir.glob("**/*.json")):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        description = data.get("description") or ""
        if not description:
            continue
        category = json_file.parent.name if json_file.parent != hooks_dir else "automation"
        name = f"{category}/{json_file.stem}"
        item_id = f"{SOURCE_PREFIX}:hook:{name}"

        items.append(
            CatalogItem(
                item_id=item_id,
                item_type=ItemType.HOOK,
                name=json_file.stem,
                description=description,
                tags=[category],
                category=category,
                platforms=DEFAULT_PLATFORMS,
                quality_score=0.0,
                popularity=0.0,
                updated_at="",
                source_url="",
                repo_full_name="",
                install_method="hook_config",
                install_content=json.dumps(data, indent=2),
            )
        )
    return items


def _parse_mcp_components(mcps_dir: Path) -> list[CatalogItem]:
    """Parse mcps/{name}/{variant}.json files.

    Args:
        mcps_dir: Path to the mcps/ component directory.

    Returns:
        List of CatalogItem instances with ItemType.REPO.
    """
    items: list[CatalogItem] = []
    for json_file in sorted(mcps_dir.glob("**/*.json")):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        servers = data.get("mcpServers") or {}
        for server_id, config in servers.items():
            description = config.get("description") or ""
            if not description:
                continue
            command = config.get("command") or ""
            args = config.get("args") or []
            install_cmd = f"{command} {' '.join(args)}" if command else None
            mcp_group = json_file.parent.name
            item_name = f"{mcp_group}/{json_file.stem}"
            item_id = f"{SOURCE_PREFIX}:mcp:{item_name}"

            items.append(
                CatalogItem(
                    item_id=item_id,
                    item_type=ItemType.REPO,
                    name=server_id,
                    description=description,
                    tags=[mcp_group],
                    category="mcp",
                    platforms=DEFAULT_PLATFORMS,
                    quality_score=0.0,
                    popularity=0.0,
                    updated_at="",
                    source_url="",
                    repo_full_name="",
                    install_method="mcp_config",
                    install_command=install_cmd,
                    install_content=json.dumps({"mcpServers": {server_id: config}}, indent=2),
                )
            )
    return items
