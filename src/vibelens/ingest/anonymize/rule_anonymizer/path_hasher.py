"""Stateful username detection and path hashing for trajectory anonymization.

Detects usernames in common path formats (macOS ``/Users/X/``, Linux
``/home/X/``, encoded ``-Users-X-``) and replaces them with a stable
``user_<8-hex>`` hash derived from SHA-256.
"""

import hashlib
import os
import re

from vibelens.config.anonymize import MIN_BARE_USERNAME_LENGTH

USER_HASH_PREFIX = "user_"
HASH_HEX_LENGTH = 8


def hash_username(username: str) -> str:
    """Produce a stable anonymized identifier from a username.

    Args:
        username: The raw username string to hash.

    Returns:
        A string like ``user_a1b2c3d4`` (prefix + 8 hex chars from SHA-256).
    """
    digest = hashlib.sha256(username.encode()).hexdigest()
    return f"{USER_HASH_PREFIX}{digest[:HASH_HEX_LENGTH]}"


class PathHasher:
    """Detects and replaces usernames in file paths with stable hashes.

    A single instance should be shared across all trajectories in a batch
    so the same username always maps to the same hash.

    Args:
        extra_usernames: Additional usernames to detect beyond the current OS user.
    """

    def __init__(self, extra_usernames: list[str] | None = None) -> None:
        self._username_to_hash: dict[str, str] = {}
        # Always include the current OS user
        current_user = os.getenv("USER") or os.getenv("USERNAME") or ""
        seed_names = [current_user] if current_user else []
        if extra_usernames:
            seed_names.extend(extra_usernames)
        for name in seed_names:
            if name and name not in self._username_to_hash:
                self._username_to_hash[name] = hash_username(name)

        # Build regex from known usernames
        self._rebuild_patterns()

    def _rebuild_patterns(self) -> None:
        """Compile path-matching regexes from the current username set."""
        if not self._username_to_hash:
            self._path_pattern: re.Pattern[str] | None = None
            self._encoded_pattern: re.Pattern[str] | None = None
            self._bare_pattern: re.Pattern[str] | None = None
            return

        # Escape and sort longest-first to avoid partial matches
        escaped = sorted((re.escape(u) for u in self._username_to_hash), key=len, reverse=True)
        names_alt = "|".join(escaped)

        # /Users/<name>/ or /home/<name>/ (macOS / Linux)
        self._path_pattern = re.compile(rf"(/(?:Users|home)/)({names_alt})(/)")
        # Encoded path form: -Users-<name>- (used in Claude Code project dirs)
        self._encoded_pattern = re.compile(rf"(-(?:Users|home)-)({names_alt})(-)")
        # Bare username references (only if username >= MIN_BARE_USERNAME_LENGTH)
        bare_names = [
            re.escape(u) for u in self._username_to_hash if len(u) >= MIN_BARE_USERNAME_LENGTH
        ]
        if bare_names:
            bare_alt = "|".join(sorted(bare_names, key=len, reverse=True))
            self._bare_pattern = re.compile(rf"\b({bare_alt})\b")
        else:
            self._bare_pattern = None

    def _register_username(self, username: str) -> str:
        """Register a newly discovered username and return its hash."""
        if username not in self._username_to_hash:
            self._username_to_hash[username] = hash_username(username)
            self._rebuild_patterns()
        return self._username_to_hash[username]

    def anonymize_path(self, path: str) -> tuple[str, int]:
        """Replace usernames in a single file-path string.

        Also discovers new usernames from path structure (e.g. if a path
        contains ``/Users/newuser/`` that wasn't in the seed set).

        Args:
            path: A file path that may contain usernames.

        Returns:
            Tuple of (anonymized path, number of replacements made).
        """
        count = 0

        # Discover usernames from path structure before applying patterns
        for match in re.finditer(r"/(?:Users|home)/([^/]+)/", path):
            self._register_username(match.group(1))
        for match in re.finditer(r"-(?:Users|home)-([^-]+)-", path):
            self._register_username(match.group(1))

        if self._path_pattern:
            new_path, n = self._path_pattern.subn(
                lambda m: f"{m.group(1)}{self._username_to_hash[m.group(2)]}{m.group(3)}",
                path,
            )
            path = new_path
            count += n

        if self._encoded_pattern:
            new_path, n = self._encoded_pattern.subn(
                lambda m: f"{m.group(1)}{self._username_to_hash[m.group(2)]}{m.group(3)}",
                path,
            )
            path = new_path
            count += n

        return path, count

    def anonymize_text(self, text: str) -> tuple[str, int]:
        """Replace usernames in free-form text (paths + bare references).

        Args:
            text: Arbitrary text that may contain file paths or bare usernames.

        Returns:
            Tuple of (anonymized text, number of replacements made).
        """
        # First handle structured paths (which also discovers new usernames)
        text, count = self.anonymize_path(text)

        # Then handle bare username references
        if self._bare_pattern:
            new_text, n = self._bare_pattern.subn(
                lambda m: self._username_to_hash[m.group(1)], text
            )
            text = new_text
            count += n

        return text, count
