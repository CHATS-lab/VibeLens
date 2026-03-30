"""LLM-based anonymizer stub — not yet implemented."""

from vibelens.config.anonymize import AnonymizeConfig
from vibelens.ingest.anonymize.base import AnonymizeResult, BaseAnonymizer
from vibelens.models.trajectories.trajectory import Trajectory


class LLMAnonymizer(BaseAnonymizer):
    """Anonymizer that uses an LLM to identify and redact sensitive data.

    This approach sends trajectory text to an LLM with instructions to
    identify secrets, PII, and sensitive paths — offering better recall
    for obfuscated or non-standard secret formats.

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
            NotImplementedError: Always. LLM-based anonymization is planned
                but not yet available.
        """
        raise NotImplementedError(
            "LLM-based anonymization is not yet implemented. "
            "Use RuleAnonymizer for regex-based redaction."
        )
