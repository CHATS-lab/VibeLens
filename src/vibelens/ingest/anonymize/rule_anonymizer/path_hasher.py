"""Stateful username detection and path hashing for trajectory anonymization.

Detects usernames in common path formats (macOS ``/Users/X/``, Linux
``/home/X/``, encoded ``-Users-X-``) and replaces them with a stable
``user_<8-hex>`` hash derived from SHA-256.

Also derives name variants from camelCase usernames (e.g. ``JohnDoe`` →
``John Doe``, ``John_Doe``, ``John-Doe``) and replaces them in free text,
file names, author fields, and document headers.
"""

import hashlib
import os
import re

from vibelens.config.anonymize import MIN_BARE_USERNAME_LENGTH

# Prefix prepended to hashed usernames (e.g. "user_a1b2c3d4")
USER_HASH_PREFIX = "user_"
# Hex digits kept from the SHA-256 hash for the username replacement
HASH_HEX_LENGTH = 8

# Separators used to join camelCase parts into name variants
_VARIANT_SEPARATORS = (" ", "_", "-")

# Regex that splits on camelCase boundaries:
# "JohnDoe" → ["John", "Doe"]
# "HTTPServer" → ["HTTP", "Server"]
_CAMEL_SPLIT_RE = re.compile(
    r"(?<=[a-z])(?=[A-Z])"  # lowercase followed by uppercase
    r"|(?<=[A-Z])(?=[A-Z][a-z])"  # uppercase followed by uppercase+lowercase
)


def hash_username(username: str) -> str:
    """Produce a stable anonymized identifier from a username.

    Args:
        username: The raw username string to hash.

    Returns:
        A string like ``user_a1b2c3d4`` (prefix + 8 hex chars from SHA-256).
    """
    digest = hashlib.sha256(username.encode()).hexdigest()
    return f"{USER_HASH_PREFIX}{digest[:HASH_HEX_LENGTH]}"


def split_camel_case(name: str) -> list[str]:
    """Split a camelCase or PascalCase string into its constituent parts.

    Args:
        name: A string like ``JohnDoe`` or ``HTTPServer``.

    Returns:
        List of parts, e.g. ``["John", "Doe"]``.
        Returns a single-element list if no split points are found.
    """
    return _CAMEL_SPLIT_RE.split(name)


def derive_name_variants(username: str) -> list[str]:
    """Derive common name variants from a camelCase username.

    For ``JohnDoe``, generates space/underscore/hyphen-separated
    variants in original case, lowercase, and uppercase. Also includes
    individual parts that are long enough to be meaningful.

    Args:
        username: The original username (e.g. ``JohnDoe``).

    Returns:
        List of variant strings (excluding the original username itself).
    """
    parts = split_camel_case(username)
    if len(parts) < 2:
        return []

    variants: list[str] = []
    for sep in _VARIANT_SEPARATORS:
        # Original case: "John Doe", "John_Doe", "John-Doe"
        joined = sep.join(parts)
        variants.append(joined)
        # Lowercase: "john doe", "john_doe", "john-doe"
        variants.append(joined.lower())
        # Uppercase: "JOHN DOE", "JOHN_DOE", "JOHN-DOE"
        variants.append(joined.upper())

    # Case variations of the full username: "johndoe", "JOHNDOE"
    variants.append(username.lower())
    variants.append(username.upper())

    # Individual parts as standalone names (only if long enough)
    for part in parts:
        if len(part) >= MIN_BARE_USERNAME_LENGTH:
            variants.append(part)
            variants.append(part.lower())
            variants.append(part.upper())

    # Deduplicate while preserving order, exclude the original
    seen: set[str] = {username}
    unique: list[str] = []
    for v in variants:
        if v not in seen:
            seen.add(v)
            unique.append(v)
    return unique


class PathHasher:
    """Detects and replaces usernames in file paths with stable hashes.

    A single instance should be shared across all trajectories in a batch
    so the same username always maps to the same hash.

    Automatically derives name variants from camelCase usernames so that
    ``JohnDoe`` also catches ``John Doe``, ``John_Doe``, etc.

    Args:
        extra_usernames: Additional usernames to detect beyond the current OS user.
    """

    def __init__(self, extra_usernames: list[str] | None = None) -> None:
        self._username_to_hash: dict[str, str] = {}
        # Maps every variant string → same hash as the original username
        self._variant_to_hash: dict[str, str] = {}
        # Always include the current OS user
        current_user = os.getenv("USER") or os.getenv("USERNAME") or ""
        seed_names = [current_user] if current_user else []
        if extra_usernames:
            seed_names.extend(extra_usernames)
        for name in seed_names:
            if name:
                self._register_username(name)

        # Build regex from known usernames
        self._rebuild_patterns()

    def _rebuild_patterns(self) -> None:
        """Compile path-matching regexes from the current username set."""
        if not self._username_to_hash:
            self._path_pattern: re.Pattern[str] | None = None
            self._encoded_pattern: re.Pattern[str] | None = None
            self._win_path_pattern: re.Pattern[str] | None = None
            self._wsl_path_pattern: re.Pattern[str] | None = None
            self._bare_pattern: re.Pattern[str] | None = None
            self._variant_pattern: re.Pattern[str] | None = None
            return

        # Escape and sort longest-first to avoid partial matches
        escaped = sorted((re.escape(u) for u in self._username_to_hash), key=len, reverse=True)
        names_alt = "|".join(escaped)

        # /Users/<name>/ or /home/<name>/ (macOS / Linux)
        self._path_pattern = re.compile(rf"(/(?:Users|home)/)({names_alt})(/)")
        # Encoded path form: -Users-<name>- (used in Claude Code project dirs)
        self._encoded_pattern = re.compile(rf"(-(?:Users|home)-)({names_alt})(-)")
        # C:\Users\<name>\ (Windows)
        self._win_path_pattern = re.compile(rf"([A-Za-z]:\\Users\\)({names_alt})(\\)")
        # /mnt/<drive>/Users/<name>/ (WSL)
        self._wsl_path_pattern = re.compile(rf"(/mnt/[a-z]/Users/)({names_alt})(/)")
        # Bare username references (only if username >= MIN_BARE_USERNAME_LENGTH)
        bare_names = [
            re.escape(u) for u in self._username_to_hash if len(u) >= MIN_BARE_USERNAME_LENGTH
        ]
        if bare_names:
            bare_alt = "|".join(sorted(bare_names, key=len, reverse=True))
            self._bare_pattern = re.compile(rf"\b({bare_alt})\b")
        else:
            self._bare_pattern = None

        # Name variants — case-insensitive literal matching without word
        # boundaries so they match inside filenames like "HW1_John_Doe.md"
        if self._variant_to_hash:
            variant_escaped = sorted(
                (re.escape(v) for v in self._variant_to_hash), key=len, reverse=True
            )
            variant_alt = "|".join(variant_escaped)
            self._variant_pattern = re.compile(rf"({variant_alt})", re.IGNORECASE)
        else:
            self._variant_pattern = None

    def _register_username(self, username: str) -> str:
        """Register a username and its derived variants, return its hash."""
        if username in self._username_to_hash:
            return self._username_to_hash[username]

        hashed = hash_username(username)
        self._username_to_hash[username] = hashed

        # Derive and register name variants (all map to the same hash)
        for variant in derive_name_variants(username):
            if variant not in self._variant_to_hash:
                self._variant_to_hash[variant] = hashed

        self._rebuild_patterns()
        return hashed

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
        for match in re.finditer(r"[A-Za-z]:\\Users\\([^\\]+)\\", path):
            self._register_username(match.group(1))
        for match in re.finditer(r"/mnt/[a-z]/Users/([^/]+)/", path):
            self._register_username(match.group(1))
        for match in re.finditer(r"/(?:Users|home)/([^/]+)/", path):
            self._register_username(match.group(1))
        for match in re.finditer(r"-(?:Users|home)-([^-]+)-", path):
            self._register_username(match.group(1))

        if self._path_pattern:
            new_path, n = self._path_pattern.subn(
                lambda m: f"{m.group(1)}{self._username_to_hash[m.group(2)]}{m.group(3)}", path
            )
            path = new_path
            count += n

        if self._encoded_pattern:
            new_path, n = self._encoded_pattern.subn(
                lambda m: f"{m.group(1)}{self._username_to_hash[m.group(2)]}{m.group(3)}", path
            )
            path = new_path
            count += n

        if self._win_path_pattern:
            new_path, n = self._win_path_pattern.subn(
                lambda m: f"{m.group(1)}{self._username_to_hash[m.group(2)]}{m.group(3)}", path
            )
            path = new_path
            count += n

        if self._wsl_path_pattern:
            new_path, n = self._wsl_path_pattern.subn(
                lambda m: f"{m.group(1)}{self._username_to_hash[m.group(2)]}{m.group(3)}", path
            )
            path = new_path
            count += n

        return path, count

    def _resolve_variant_hash(self, matched_text: str) -> str:
        """Look up the hash for a variant match (case-insensitive).

        Args:
            matched_text: The actual text matched by the variant pattern.

        Returns:
            The hash associated with this variant.
        """
        # Try exact match first, then lowercase lookup
        if matched_text in self._variant_to_hash:
            return self._variant_to_hash[matched_text]
        return self._variant_to_hash.get(
            matched_text.lower(), self._variant_to_hash.get(matched_text.upper(), "[ANON]")
        )

    def anonymize_text(self, text: str) -> tuple[str, int]:
        """Replace usernames in free-form text (paths + bare + name variants).

        Args:
            text: Arbitrary text that may contain file paths or bare usernames.

        Returns:
            Tuple of (anonymized text, number of replacements made).
        """
        # Phase 1: structured paths (also discovers new usernames)
        text, count = self.anonymize_path(text)

        # Phase 2: bare username references (word-boundary match)
        if self._bare_pattern:
            new_text, n = self._bare_pattern.subn(
                lambda m: self._username_to_hash[m.group(1)], text
            )
            text = new_text
            count += n

        # Phase 3: name variants (case-insensitive literal match)
        if self._variant_pattern:
            new_text, n = self._variant_pattern.subn(
                lambda m: self._resolve_variant_hash(m.group(1)), text
            )
            text = new_text
            count += n

        return text, count
