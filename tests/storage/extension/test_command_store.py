"""Tests for CommandStore — flat-file I/O wrapper for command .md files."""

import pytest

from vibelens.storage.extension.command_store import CommandStore, parse_command_md

SAMPLE_COMMAND_MD = """\
---
description: A sample command
tags:
  - testing
---
# Sample Command

Body content.
"""

FORK_COMMAND_MD = """\
---
description: A forked subagent
fork: true
tags:
  - testing
---
# Forked

Body content.
"""

MINIMAL_COMMAND_MD = """\
---
description: Minimal
---
Body only.
"""

NO_FRONTMATTER_MD = """\
# No Frontmatter

Just content.
"""


class TestParseCommandMd:
    def test_parses_full_command(self):
        command = parse_command_md("sample-command", SAMPLE_COMMAND_MD)
        assert command.name == "sample-command"
        assert command.description == "A sample command"
        assert command.tags == ["testing"]
        assert command.content_hash != ""

    def test_parses_minimal(self):
        command = parse_command_md("minimal", MINIMAL_COMMAND_MD)
        assert command.description == "Minimal"
        assert command.tags == []

    def test_no_frontmatter(self):
        command = parse_command_md("bare", NO_FRONTMATTER_MD)
        assert command.description == ""


class TestCommandStore:
    @pytest.fixture
    def store(self, tmp_path):
        return CommandStore(root=tmp_path, create=True)

    @pytest.fixture
    def populated_store(self, store):
        store.write("alpha", SAMPLE_COMMAND_MD)
        store.write("beta", MINIMAL_COMMAND_MD)
        return store

    def test_write_and_read(self, store):
        store.write("my-command", SAMPLE_COMMAND_MD)
        command = store.read("my-command")
        assert command is not None
        assert command.name == "my-command"
        assert command.description == "A sample command"

    def test_write_creates_file(self, store):
        path = store.write("new-command", MINIMAL_COMMAND_MD)
        assert path.exists()
        assert path.name == "new-command.md"

    def test_read_nonexistent_returns_none(self, store):
        assert store.read("nonexistent") is None

    def test_read_raw(self, store):
        store.write("my-command", SAMPLE_COMMAND_MD)
        raw = store.read_raw("my-command")
        assert raw is not None
        assert "A sample command" in raw

    def test_read_raw_nonexistent(self, store):
        assert store.read_raw("nope") is None

    def test_list_names(self, populated_store):
        names = populated_store.list_names()
        assert sorted(names) == ["alpha", "beta"]

    def test_list_names_empty(self, store):
        assert store.list_names() == []

    def test_list_names_excludes_forked(self, store):
        """Files with fork: true should be excluded from list_names."""
        store.write("real-command", SAMPLE_COMMAND_MD)
        # Write a forked subagent file directly
        fork_path = store.root / "forked-agent.md"
        fork_path.write_text(FORK_COMMAND_MD, encoding="utf-8")
        names = store.list_names()
        assert "real-command" in names
        assert "forked-agent" not in names

    def test_exists(self, populated_store):
        assert populated_store.exists("alpha")
        assert not populated_store.exists("nonexistent")

    def test_exists_excludes_forked(self, store):
        """exists() returns False for forked subagent files."""
        fork_path = store.root / "forked-agent.md"
        fork_path.write_text(FORK_COMMAND_MD, encoding="utf-8")
        assert not store.exists("forked-agent")

    def test_read_raw_excludes_forked(self, store):
        """read_raw() returns None for forked subagent files."""
        fork_path = store.root / "forked-agent.md"
        fork_path.write_text(FORK_COMMAND_MD, encoding="utf-8")
        assert store.read_raw("forked-agent") is None

    def test_delete(self, populated_store):
        assert populated_store.delete("alpha")
        assert not populated_store.exists("alpha")

    def test_delete_nonexistent(self, store):
        assert not store.delete("nope")

    def test_copy_from(self, tmp_path):
        src_store = CommandStore(root=tmp_path / "src", create=True)
        dst_store = CommandStore(root=tmp_path / "dst", create=True)

        src_store.write("my-command", SAMPLE_COMMAND_MD)
        assert dst_store.copy_from(src_store, "my-command")
        assert dst_store.exists("my-command")

        command = dst_store.read("my-command")
        assert command is not None
        assert command.description == "A sample command"

    def test_copy_from_nonexistent(self, tmp_path):
        src_store = CommandStore(root=tmp_path / "src", create=True)
        dst_store = CommandStore(root=tmp_path / "dst", create=True)
        assert not dst_store.copy_from(src_store, "nope")

    def test_write_rejects_invalid_name(self, store):
        with pytest.raises(ValueError, match="kebab-case"):
            store.write("Not Valid", "content")

    def test_root_property(self, tmp_path):
        store = CommandStore(root=tmp_path / "commands", create=True)
        assert store.root == (tmp_path / "commands")

    def test_create_false_does_not_create_dir(self, tmp_path):
        root = tmp_path / "does-not-exist"
        store = CommandStore(root=root)
        assert not root.exists()
        assert store.list_names() == []
