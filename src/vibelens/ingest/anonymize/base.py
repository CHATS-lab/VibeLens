"""Base anonymizer interface and shared result model."""

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field

from vibelens.config.anonymize import AnonymizeConfig
from vibelens.models.trajectories.trajectory import Trajectory


class AnonymizeResult(BaseModel):
    """Counts of redactions applied during a single trajectory anonymization pass."""

    secrets_redacted: int = Field(
        default=0, description="Number of credential/secret patterns replaced."
    )
    paths_anonymized: int = Field(
        default=0, description="Number of path segments with hashed usernames."
    )
    pii_redacted: int = Field(
        default=0, description="Number of PII patterns (emails, IPs) replaced."
    )


class BaseAnonymizer(ABC):
    """Abstract base for all trajectory anonymizers.

    Subclasses implement ``anonymize_trajectory`` with their specific
    redaction strategy (regex rules, LLM-based, NER-based, etc.).
    """

    def __init__(self, config: AnonymizeConfig) -> None:
        self.config = config

    @abstractmethod
    def anonymize_trajectory(self, trajectory: Trajectory) -> tuple[Trajectory, AnonymizeResult]:
        """Redact sensitive data from a single trajectory.

        Args:
            trajectory: The ATIF trajectory to anonymize.

        Returns:
            A tuple of (anonymized trajectory copy, result counts).
        """

    def anonymize_batch(
        self, trajectories: list[Trajectory]
    ) -> list[tuple[Trajectory, AnonymizeResult]]:
        """Anonymize multiple trajectories with shared state.

        Default implementation calls ``anonymize_trajectory`` for each.
        Subclasses may override for batch-level optimizations (e.g. shared
        username hashing across trajectories).

        Args:
            trajectories: List of trajectories to anonymize.

        Returns:
            List of (anonymized trajectory, result) tuples.
        """
        return [self.anonymize_trajectory(t) for t in trajectories]
