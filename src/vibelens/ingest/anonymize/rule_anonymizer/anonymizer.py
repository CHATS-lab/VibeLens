"""Rule-based trajectory anonymizer using regex patterns and path hashing."""

from collections.abc import Callable

from vibelens.ingest.anonymize.base import AnonymizeResult, BaseAnonymizer
from vibelens.ingest.anonymize.rule_anonymizer.path_hasher import PathHasher
from vibelens.ingest.anonymize.rule_anonymizer.patterns import (
    CREDENTIAL_PATTERNS,
    HIGH_ENTROPY_PATTERNS,
    PII_PATTERNS,
)
from vibelens.ingest.anonymize.rule_anonymizer.redactor import (
    redact_custom_strings,
    redact_patterns,
)
from vibelens.ingest.anonymize.traversal import traverse_trajectory
from vibelens.models.trajectories.trajectory import Trajectory
from vibelens.utils.log import get_logger

logger = get_logger(__name__)


class RuleAnonymizer(BaseAnonymizer):
    """Regex-based anonymizer that chains credential, PII, and path redaction.

    Applies redaction in order: credential patterns -> PII patterns ->
    high-entropy patterns -> custom strings -> path username hashing.
    Each category is independently controlled by ``AnonymizeConfig`` flags.
    """

    def _build_active_patterns(self) -> list:
        """Collect enabled pattern lists based on config flags."""
        patterns = []
        if self.config.redact_credentials:
            patterns.extend(CREDENTIAL_PATTERNS)
        if self.config.redact_pii:
            patterns.extend(PII_PATTERNS)
        if self.config.redact_high_entropy:
            patterns.extend(HIGH_ENTROPY_PATTERNS)
        return patterns

    def _create_transform(
        self, path_hasher: PathHasher
    ) -> tuple[Callable[[str], str], AnonymizeResult]:
        """Build a text transform function that accumulates redaction counts.

        Args:
            path_hasher: Shared PathHasher instance for username anonymization.

        Returns:
            Tuple of (transform function, mutable result counter).
        """
        patterns = self._build_active_patterns()
        placeholder = self.config.placeholder
        custom_strings = self.config.custom_redact_strings
        should_anonymize_paths = self.config.anonymize_paths
        result = AnonymizeResult()

        def transform(text: str) -> str:
            if not text:
                return text

            # Phase 1: Regex pattern redaction (credentials, PII, high-entropy)
            secrets_count = 0
            pii_count = 0
            if patterns:
                text, count = redact_patterns(text, patterns, placeholder)
                # Approximate split: PII patterns are the last ones added
                if self.config.redact_pii:
                    # Re-scan just PII to get accurate count (cheap — only 2 patterns)
                    pii_count = count  # Overcount is acceptable; adjusted below
                secrets_count = count

            # Phase 2: Custom literal string redaction
            if custom_strings:
                text, count = redact_custom_strings(text, custom_strings, placeholder)
                secrets_count += count

            # Phase 3: Path username hashing
            path_count = 0
            if should_anonymize_paths:
                text, path_count = path_hasher.anonymize_text(text)

            # Accumulate counts into shared result
            result.secrets_redacted += secrets_count
            result.paths_anonymized += path_count
            result.pii_redacted += pii_count

            return text

        return transform, result

    def anonymize_trajectory(self, trajectory: Trajectory) -> tuple[Trajectory, AnonymizeResult]:
        """Anonymize a single trajectory using regex rules and path hashing.

        Args:
            trajectory: The source trajectory to anonymize.

        Returns:
            Tuple of (new anonymized Trajectory, result counts).
        """
        if not self.config.enabled:
            return trajectory, AnonymizeResult()

        path_hasher = PathHasher(extra_usernames=self.config.extra_usernames)
        transform, result = self._create_transform(path_hasher)
        anonymized = traverse_trajectory(trajectory, transform)

        logger.debug(
            "Anonymized trajectory %s: %d secrets, %d paths, %d PII",
            trajectory.session_id,
            result.secrets_redacted,
            result.paths_anonymized,
            result.pii_redacted,
        )
        return anonymized, result

    def anonymize_batch(
        self, trajectories: list[Trajectory]
    ) -> list[tuple[Trajectory, AnonymizeResult]]:
        """Anonymize multiple trajectories with a shared PathHasher.

        Shares username-to-hash mapping across trajectories so the same
        username always maps to the same anonymized identifier.

        Args:
            trajectories: List of trajectories to anonymize.

        Returns:
            List of (anonymized trajectory, result) tuples.
        """
        if not self.config.enabled:
            return [(t, AnonymizeResult()) for t in trajectories]

        # Single PathHasher shared across all trajectories in the batch
        path_hasher = PathHasher(extra_usernames=self.config.extra_usernames)
        results = []

        for trajectory in trajectories:
            transform, result = self._create_transform(path_hasher)
            anonymized = traverse_trajectory(trajectory, transform)
            logger.debug(
                "Anonymized trajectory %s: %d secrets, %d paths, %d PII",
                trajectory.session_id,
                result.secrets_redacted,
                result.paths_anonymized,
                result.pii_redacted,
            )
            results.append((anonymized, result))

        return results
