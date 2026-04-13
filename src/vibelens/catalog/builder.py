"""Catalog builder orchestrator -- reads hub sources, scores, deduplicates, writes JSON."""

import argparse
import asyncio
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import httpx

from vibelens.catalog.dedup import deduplicate
from vibelens.catalog.enricher import enrich_from_github
from vibelens.catalog.scoring import score_items
from vibelens.catalog.sources.buildwithclaude import parse_buildwithclaude
from vibelens.catalog.sources.featured import parse_featured
from vibelens.catalog.sources.templates import parse_templates
from vibelens.models.recommendation.catalog import CatalogItem
from vibelens.services.recommendation.catalog import load_catalog_from_path
from vibelens.utils.log import get_logger

logger = get_logger(__name__)

DEFAULT_OUTPUT = Path("src/vibelens/data/catalog.json")
SCHEMA_VERSION = 1
URL_CHECK_TIMEOUT = 5
URL_CHECK_CONCURRENCY = 50


async def _check_url(client: httpx.AsyncClient, url: str) -> bool:
    """HEAD-check a single URL. Returns True if accessible."""
    try:
        resp = await client.head(url, follow_redirects=True, timeout=URL_CHECK_TIMEOUT)
        return resp.status_code < 400
    except (httpx.HTTPError, httpx.TimeoutException):
        return False


async def _validate_urls_async(items: list[CatalogItem]) -> list[CatalogItem]:
    """Filter out items with broken source_url values."""
    to_check = [(i, item) for i, item in enumerate(items) if item.source_url]
    if not to_check:
        return items

    sem = asyncio.Semaphore(URL_CHECK_CONCURRENCY)
    results: dict[int, bool] = {}

    async with httpx.AsyncClient() as client:

        async def check(idx: int, url: str) -> None:
            async with sem:
                results[idx] = await _check_url(client, url)

        tasks = [check(idx, item.source_url) for idx, item in to_check]
        await asyncio.gather(*tasks)

    kept: list[CatalogItem] = []
    dropped = 0
    for i, item in enumerate(items):
        if item.source_url and not results.get(i, True):
            dropped += 1
            continue
        kept.append(item)

    logger.info("URL validation: %d items dropped (%d kept)", dropped, len(kept))
    return kept


def validate_source_urls(items: list[CatalogItem]) -> list[CatalogItem]:
    """Synchronous wrapper for URL validation."""
    return asyncio.run(_validate_urls_async(items))


def build_catalog(
    hub_dir: Path,
    output_path: Path = DEFAULT_OUTPUT,
    existing_catalog_path: Path | None = None,
    bwc_repo: str | None = None,
    cct_repo: str | None = None,
) -> list[CatalogItem]:
    """Build catalog.json from hub data sources.

    Pipeline: collect -> deduplicate -> score -> validate URLs -> enrich -> merge -> write.

    Args:
        hub_dir: Root hub directory containing source subdirectories.
        output_path: Where to write the output catalog.json.
        existing_catalog_path: Optional path to existing catalog whose items
            are preserved (hand-curated items keep their original scores).
        bwc_repo: GitHub owner/repo for buildwithclaude (e.g. "davepoon/buildwithclaude").
        cct_repo: GitHub owner/repo for claude-code-templates
            (e.g. "davila7/claude-code-templates").

    Returns:
        Final list of CatalogItem instances written to output.
    """
    raw_items: list[CatalogItem] = []
    path_map: dict[str, str] = {}

    bwc_dir = hub_dir / "buildwithclaude"
    if bwc_dir.is_dir():
        bwc_items, bwc_paths = parse_buildwithclaude(bwc_dir)
        print(f"  buildwithclaude: {len(bwc_items)} items")
        raw_items.extend(bwc_items)
        path_map.update(bwc_paths)

    cct_dir = hub_dir / "claude-code-templates"
    if cct_dir.is_dir():
        cct_items, cct_paths = parse_templates(cct_dir)
        print(f"  claude-code-templates: {len(cct_items)} items")
        raw_items.extend(cct_items)
        path_map.update(cct_paths)

    featured_dir = hub_dir / "skills-hub"
    if featured_dir.is_dir():
        featured_items, featured_paths = parse_featured(featured_dir)
        print(f"  skills-hub featured: {len(featured_items)} items")
        raw_items.extend(featured_items)
        path_map.update(featured_paths)

    print(f"Total raw: {len(raw_items)} items")

    deduped = deduplicate(raw_items)
    print(f"After dedup: {len(deduped)} items ({len(raw_items) - len(deduped)} removed)")

    scored = score_items(deduped)

    scored = validate_source_urls(scored)

    if bwc_repo or cct_repo:
        scored = enrich_from_github(scored, path_map, bwc_repo=bwc_repo, cct_repo=cct_repo)

    if existing_catalog_path:
        existing = load_catalog_from_path(existing_catalog_path)
        if existing:
            scored = _merge_existing(scored, existing.items)
            print(f"After merge with existing: {len(scored)} items")

    _write_catalog(scored, output_path)
    return scored


def _merge_existing(
    new_items: list[CatalogItem], existing_items: list[CatalogItem]
) -> list[CatalogItem]:
    """Merge existing hand-curated items, preserving their scores.

    Args:
        new_items: Freshly built and scored items.
        existing_items: Items from the existing catalog to preserve if not
            already present in new_items.

    Returns:
        Combined list with existing items appended where not duplicated.
    """
    new_ids = {item.item_id for item in new_items}
    merged = list(new_items)
    for existing in existing_items:
        if existing.item_id not in new_ids:
            merged.append(existing)
    return merged


def _write_catalog(items: list[CatalogItem], output_path: Path) -> None:
    """Serialize items to catalog.json format.

    Args:
        items: Scored catalog items to write.
        output_path: Destination file path (parent dirs created if needed).
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    version = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    catalog = {
        "version": version,
        "schema_version": SCHEMA_VERSION,
        "items": [item.model_dump(mode="json") for item in items],
    }
    output_path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False))
    print(f"Wrote {len(items)} items to {output_path}")


def print_stats(items: list[CatalogItem]) -> None:
    """Print distribution statistics for the catalog.

    Args:
        items: Catalog items to summarize.
    """
    type_counts = Counter(i.item_type.value for i in items)
    category_counts = Counter(i.category for i in items)
    platform_counts = Counter(p for i in items for p in i.platforms)
    has_content = sum(1 for i in items if i.install_content)
    scores = [i.quality_score for i in items]

    print(f"\n{'='*60}")
    print(f"Catalog Statistics: {len(items)} items")
    print(f"{'='*60}")
    print("\nType distribution:")
    for item_type, count in type_counts.most_common():
        print(f"  {item_type:12s} {count:4d}")
    print("\nTop 15 categories:")
    for cat, count in category_counts.most_common(15):
        print(f"  {cat:30s} {count:4d}")
    print("\nPlatform distribution:")
    for plat, count in platform_counts.most_common():
        print(f"  {plat:15s} {count:4d}")
    avg_score = sum(scores) / len(scores)
    print(f"\nQuality scores: min={min(scores):.1f}, max={max(scores):.1f}, avg={avg_score:.1f}")
    print(f"Installable (has content): {has_content}/{len(items)} ({100*has_content//len(items)}%)")
    print(f"Total categories: {len(category_counts)}")


def main() -> None:
    """CLI entry point for catalog builder."""
    parser = argparse.ArgumentParser(description="Build VibeLens catalog from hub sources")
    parser.add_argument("--hub-dir", type=Path, required=True, help="Path to hub directory")
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT, help="Output catalog.json path"
    )
    parser.add_argument("--existing", type=Path, default=None, help="Existing catalog to preserve")
    parser.add_argument(
        "--bwc-repo", type=str, default=None, help="GitHub owner/repo for buildwithclaude"
    )
    parser.add_argument(
        "--cct-repo", type=str, default=None, help="GitHub owner/repo for claude-code-templates"
    )
    parser.add_argument("--stats", action="store_true", help="Print statistics after build")
    args = parser.parse_args()

    if not args.hub_dir.is_dir():
        print(f"Error: hub directory not found: {args.hub_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Building catalog from {args.hub_dir}...")
    items = build_catalog(
        hub_dir=args.hub_dir,
        output_path=args.output,
        existing_catalog_path=args.existing,
        bwc_repo=args.bwc_repo,
        cct_repo=args.cct_repo,
    )

    if args.stats:
        print_stats(items)
