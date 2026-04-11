"""Parser for pre-parsed trajectory JSON files.

DiskStore saves trajectories as JSON arrays of Trajectory dicts.
This parser deserializes them back into Trajectory objects, allowing
DiskStore to use the same parser-based loading path as LocalStore.
"""

import json

from vibelens.ingest.parsers.base import BaseParser
from vibelens.models.enums import AgentType
from vibelens.models.trajectories import Trajectory
from vibelens.utils.log import get_logger

logger = get_logger(__name__)


class ParsedTrajectoryParser(BaseParser):
    """Deserialize pre-parsed trajectory JSON files.

    Not included in LOCAL_PARSER_CLASSES — only used by DiskStore,
    not local agent discovery.
    """

    AGENT_TYPE = AgentType.PARSED
    LOCAL_DATA_DIR = None

    def parse(self, content: str, source_path: str | None = None) -> list[Trajectory]:
        """Parse JSON content into Trajectory objects.

        Accepts either a JSON array of trajectory dicts or a single
        trajectory dict.

        Args:
            content: JSON string of trajectory data.
            source_path: Original file path (unused).

        Returns:
            List of deserialized Trajectory objects.
        """
        try:
            raw = json.loads(content)
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse JSON from %s: %s", source_path, exc)
            return []

        items = raw if isinstance(raw, list) else [raw]
        trajectories: list[Trajectory] = []

        for item in items:
            try:
                trajectories.append(Trajectory(**item))
            except (TypeError, ValueError) as exc:
                logger.warning("Failed to deserialize trajectory from %s: %s", source_path, exc)

        return trajectories
