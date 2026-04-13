"""Parse skills-hub featured-skills.json."""

import json
import math
from pathlib import Path

from vibelens.models.recommendation.catalog import CatalogItem, ItemType

SOURCE_PREFIX = "featured"
DEFAULT_PLATFORMS = ["claude_code"]


def parse_featured(hub_dir: Path) -> list[CatalogItem]:
    """Parse featured-skills.json into CatalogItem list.

    Args:
        hub_dir: Path to the skills-hub directory containing featured-skills.json.

    Returns:
        List of CatalogItem instances.
    """
    json_path = hub_dir / "featured-skills.json"
    if not json_path.is_file():
        return []

    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    skills = data.get("skills") or []
    max_stars = max((s.get("stars") or 0 for s in skills), default=1)
    max_stars = max(max_stars, 1)

    items: list[CatalogItem] = []
    for entry in skills:
        summary = entry.get("summary") or ""
        if not summary:
            continue

        slug = entry.get("slug") or entry.get("name") or ""
        if not slug:
            continue

        stars = entry.get("stars") or 0
        popularity = math.log(1 + stars) / math.log(1 + max_stars)

        items.append(
            CatalogItem(
                item_id=f"{SOURCE_PREFIX}:skill:{slug}",
                item_type=ItemType.SKILL,
                name=slug,
                description=summary,
                tags=entry.get("tags") or [],
                category=entry.get("category") or "uncategorized",
                platforms=DEFAULT_PLATFORMS,
                quality_score=0.0,
                popularity=round(popularity, 3),
                updated_at=entry.get("updated_at") or "",
                source_url=entry.get("source_url") or "",
                repo_full_name="",
                install_method="skill_file",
            )
        )
    return items
