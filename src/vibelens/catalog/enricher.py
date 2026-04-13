"""GitHub API enrichment for catalog items."""

from vibelens.models.recommendation.catalog import CatalogItem
from vibelens.utils.log import get_logger

logger = get_logger(__name__)


def enrich_from_github(
    items: list[CatalogItem],
    path_map: dict[str, str],
    bwc_repo: str | None = None,
    cct_repo: str | None = None,
) -> list[CatalogItem]:
    """Enrich catalog items with GitHub metadata.

    Resolves source_urls and fetches stars, forks, language, license from
    the GitHub REST API.

    Args:
        items: Scored catalog items.
        path_map: Mapping of item_id to relative file path within source repo.
        bwc_repo: GitHub owner/repo for buildwithclaude source.
        cct_repo: GitHub owner/repo for claude-code-templates source.

    Returns:
        Items with enriched metadata.
    """
    logger.info("GitHub enrichment stub -- skipping (no implementation yet)")
    return items
