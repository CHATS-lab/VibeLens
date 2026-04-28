"""Parser for pre-parsed trajectory JSON files.

DiskStore saves trajectories as JSON arrays of Trajectory dicts. This parser
round-trips them so DiskStore loads via the same parser path as LocalStore.
"""

import json
from pathlib import Path

from vibelens.ingest.parsers.base import BaseParser
from vibelens.models.trajectories import Trajectory
from vibelens.utils.log import get_logger

logger = get_logger(__name__)


class ParsedTrajectoryParser(BaseParser):
    """Deserialize pre-parsed trajectory JSON files.

    Not in ``LOCAL_PARSER_CLASSES`` — only DiskStore uses it, not local agent discovery.
    """

    AGENT_TYPE = None
    LOCAL_DATA_DIR = None

    def parse(self, file_path: Path) -> list[Trajectory]:
        """Parse a DiskStore JSON file (single trajectory dict or array of them)."""
        try:
            raw = json.loads(file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to parse JSON from %s: %s", file_path, exc)
            return []
        items = raw if isinstance(raw, list) else [raw]
        trajectories: list[Trajectory] = []
        for item in items:
            try:
                trajectories.append(Trajectory(**item))
            except (TypeError, ValueError) as exc:
                logger.warning("Failed to deserialize trajectory from %s: %s", file_path, exc)
        return trajectories
