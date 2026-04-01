"""Tests for username hashing and path anonymization."""

import pytest

from vibelens.ingest.anonymize.rule_anonymizer.path_hasher import (
    PathHasher,
    derive_name_variants,
    hash_username,
    split_camel_case,
)


def test_hash_username_deterministic() -> None:
    h1 = hash_username("testuser")
    h2 = hash_username("testuser")
    print(f"  hash('testuser') = {h1}")
    assert h1 == h2
    assert h1.startswith("user_")
    assert len(h1) == len("user_") + 8


def test_hash_username_different_inputs() -> None:
    h1 = hash_username("alice")
    h2 = hash_username("bob")
    print(f"  hash('alice')={h1}, hash('bob')={h2}")
    assert h1 != h2


class TestPathHasher:
    def test_macos_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("USER", "testuser")
        hasher = PathHasher()
        result, count = hasher.anonymize_text("/Users/testuser/code/main.py")
        print(f"  macOS path: {result} (count={count})")
        assert "testuser" not in result
        assert count >= 1

    def test_linux_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("USER", "testuser")
        hasher = PathHasher()
        result, count = hasher.anonymize_text("/home/testuser/project/src/app.py")
        print(f"  Linux path: {result} (count={count})")
        assert "testuser" not in result
        assert count >= 1

    def test_encoded_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("USER", "testuser")
        hasher = PathHasher()
        result, count = hasher.anonymize_text("-Users-testuser-project-main")
        print(f"  encoded path: {result} (count={count})")
        assert "testuser" not in result
        assert count >= 1

    def test_unchanged_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("USER", "testuser")
        hasher = PathHasher()
        text = "/etc/config/app.conf"
        result, count = hasher.anonymize_text(text)
        print(f"  unchanged path: {result} (count={count})")
        assert result == text
        assert count == 0

    def test_auto_discovery(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Path hasher discovers new usernames from path structure."""
        monkeypatch.setenv("USER", "testuser")
        hasher = PathHasher()
        result, count = hasher.anonymize_text("/Users/newuser/foo/bar.txt")
        print(f"  auto-discovered: {result} (count={count})")
        assert "newuser" not in result
        assert count >= 1

    def test_extra_usernames(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("USER", "testuser")
        hasher = PathHasher(extra_usernames=["alice"])
        result, count = hasher.anonymize_text("/Users/alice/project/file.py")
        print(f"  extra username: {result} (count={count})")
        assert "alice" not in result
        assert count >= 1

    def test_bare_username(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Bare username in text (not in a path) is replaced if len >= 4."""
        monkeypatch.setenv("USER", "testuser")
        hasher = PathHasher()
        result, count = hasher.anonymize_text("The user testuser logged in.")
        print(f"  bare username: {result} (count={count})")
        assert "testuser" not in result
        assert count >= 1

    def test_short_username_not_bare(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """3-char username only replaced in paths, not as bare word."""
        monkeypatch.setenv("USER", "bob")
        hasher = PathHasher()
        # Bare "bob" should NOT be replaced (len < MIN_BARE_USERNAME_LENGTH)
        result, count = hasher.anonymize_text("Hi bob, how are you?")
        print(f"  short bare: {result} (count={count})")
        assert "bob" in result

        # But in a path it should still be replaced
        result2, count2 = hasher.anonymize_text("/Users/bob/code/")
        print(f"  short in path: {result2} (count={count2})")
        assert "bob" not in result2

    def test_windows_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Windows paths like C:\\Users\\alice\\ are anonymized."""
        monkeypatch.setenv("USER", "alice")
        hasher = PathHasher()
        result, count = hasher.anonymize_text(r"C:\Users\alice\Documents\project\main.py")
        print(f"  Windows path: {result} (count={count})")
        assert "alice" not in result
        assert count >= 1

    def test_wsl_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """WSL paths like /mnt/c/Users/alice/ are anonymized."""
        monkeypatch.setenv("USER", "alice")
        hasher = PathHasher()
        result, count = hasher.anonymize_text("/mnt/c/Users/alice/project/main.py")
        print(f"  WSL path: {result} (count={count})")
        assert "alice" not in result
        assert count >= 1

    def test_windows_path_consistent_with_unix(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Same username in Windows and Unix paths maps to the same hash."""
        monkeypatch.setenv("USER", "alice")
        hasher = PathHasher()
        expected_hash = hash_username("alice")
        win_result, _ = hasher.anonymize_text(r"C:\Users\alice\code\app.py")
        unix_result, _ = hasher.anonymize_text("/Users/alice/code/app.py")
        print(f"  cross-platform hash: win={win_result}, unix={unix_result}")
        assert expected_hash in win_result
        assert expected_hash in unix_result

    def test_consistent_across_calls(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("USER", "testuser")
        hasher = PathHasher()
        r1, _ = hasher.anonymize_text("/Users/testuser/a.py")
        r2, _ = hasher.anonymize_text("/Users/testuser/b.py")
        # Same hash for the same username
        hash_val = hash_username("testuser")
        print(f"  consistent hash: {hash_val}")
        assert hash_val in r1
        assert hash_val in r2


class TestSplitCamelCase:
    def test_pascal_case(self) -> None:
        assert split_camel_case("JohnDoe") == ["John", "Doe"]

    def test_no_split(self) -> None:
        assert split_camel_case("testuser") == ["testuser"]

    def test_three_parts(self) -> None:
        assert split_camel_case("JohnMichaelDoe") == ["John", "Michael", "Doe"]

    def test_single_char_parts(self) -> None:
        # Single uppercase letter at start
        parts = split_camel_case("ATest")
        print(f"  ATest: {parts}")
        assert len(parts) >= 2


class TestDeriveNameVariants:
    def test_camel_case_username(self) -> None:
        variants = derive_name_variants("JohnDoe")
        print(f"  variants: {variants}")
        assert "John Doe" in variants
        assert "John_Doe" in variants
        assert "John-Doe" in variants
        assert "john doe" in variants
        assert "john_doe" in variants
        assert "JOHN DOE" in variants

    def test_no_camel_case(self) -> None:
        """Non-camelCase username produces no variants."""
        variants = derive_name_variants("testuser")
        assert variants == []

    def test_individual_parts_included(self) -> None:
        """Long-enough individual parts are included as variants."""
        variants = derive_name_variants("JohnDoe")
        # "John" (4 chars >= MIN_BARE_USERNAME_LENGTH) should be included
        assert "John" in variants
        assert "john" in variants

    def test_short_parts_excluded(self) -> None:
        """Parts shorter than MIN_BARE_USERNAME_LENGTH are excluded."""
        variants = derive_name_variants("JohnDoe")
        # "Doe" (3 chars) should NOT be included as standalone
        assert "Doe" not in variants

    def test_case_variations_of_full_name(self) -> None:
        variants = derive_name_variants("JohnDoe")
        assert "johndoe" in variants
        assert "JOHNDOE" in variants


class TestPathHasherVariants:
    def test_space_separated_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """'John Doe' in author field is replaced."""
        monkeypatch.setenv("USER", "JohnDoe")
        hasher = PathHasher()
        text = '"author": {"name": "John Doe"}'
        result, count = hasher.anonymize_text(text)
        print(f"  space-separated: {result} (count={count})")
        assert "John Doe" not in result
        assert count >= 1

    def test_underscore_in_filename(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """'John_Doe' in filename is replaced."""
        monkeypatch.setenv("USER", "JohnDoe")
        hasher = PathHasher()
        text = "HW1_John_Doe.md"
        result, count = hasher.anonymize_text(text)
        print(f"  underscore filename: {result} (count={count})")
        assert "John_Doe" not in result
        assert count >= 1

    def test_lowercase_variant(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Lowercase variant 'john doe' is replaced."""
        monkeypatch.setenv("USER", "JohnDoe")
        hasher = PathHasher()
        text = "contact john doe for details"
        result, count = hasher.anonymize_text(text)
        print(f"  lowercase: {result} (count={count})")
        assert "john doe" not in result

    def test_bare_first_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Bare first name 'John' is replaced (>= 4 chars)."""
        monkeypatch.setenv("USER", "JohnDoe")
        hasher = PathHasher()
        text = "Author: John wrote this"
        result, count = hasher.anonymize_text(text)
        print(f"  bare first name: {result} (count={count})")
        assert "John" not in result

    def test_variant_same_hash_as_username(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """All variants map to the same hash as the original username."""
        monkeypatch.setenv("USER", "JohnDoe")
        hasher = PathHasher()
        expected_hash = hash_username("JohnDoe")
        # Path replacement
        r1, _ = hasher.anonymize_text("/Users/JohnDoe/code/")
        assert expected_hash in r1
        # Variant replacement
        r2, _ = hasher.anonymize_text("by John Doe")
        print(f"  variant hash: {r2}")
        assert expected_hash in r2

    def test_case_insensitive_variant(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Variant matching is case-insensitive."""
        monkeypatch.setenv("USER", "JohnDoe")
        hasher = PathHasher()
        text = "JOHN_DOE wrote the report"
        result, count = hasher.anonymize_text(text)
        print(f"  case-insensitive: {result} (count={count})")
        assert "JOHN_DOE" not in result

    def test_non_camelcase_no_variants(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Non-camelCase username like 'testuser' doesn't get variants."""
        monkeypatch.setenv("USER", "testuser")
        hasher = PathHasher()
        # "test user" should NOT be replaced (not a derived variant)
        text = "the test user logged in"
        result, count = hasher.anonymize_text(text)
        print(f"  non-camel: {result} (count={count})")
        # "testuser" as bare word IS replaced, but "test user" is not
        assert "test user" in result
