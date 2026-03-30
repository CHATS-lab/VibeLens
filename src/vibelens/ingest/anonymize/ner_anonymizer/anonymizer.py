"""NER-based anonymizer stub — not yet implemented."""

from vibelens.config.anonymize import AnonymizeConfig
from vibelens.ingest.anonymize.base import AnonymizeResult, BaseAnonymizer
from vibelens.models.trajectories.trajectory import Trajectory


class NERAnonymizer(BaseAnonymizer):
    """Anonymizer that uses Named Entity Recognition to find and redact PII.

    This approach runs a local NER model (e.g. spaCy, Presidio) to
    detect person names, organizations, locations, and other entities
    beyond what regex patterns can catch.

    Not yet implemented. Instantiation succeeds but calling
    ``anonymize_trajectory`` raises ``NotImplementedError``.
    """

    def __init__(self, config: AnonymizeConfig) -> None:
        super().__init__(config)

    def anonymize_trajectory(
        self, trajectory: Trajectory
    ) -> tuple[Trajectory, AnonymizeResult]:
        """Not implemented — raises NotImplementedError.

        Args:
            trajectory: Unused.

        Raises:
            NotImplementedError: Always. NER-based anonymization is planned
                but not yet available.
        """
        raise NotImplementedError(
            "NER-based anonymization is not yet implemented. "
            "Use RuleAnonymizer for regex-based redaction."
        )
