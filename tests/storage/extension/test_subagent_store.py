"""Tests for SubagentStore — flat-file I/O wrapper for subagent .md files."""

import pytest

from vibelens.storage.extension.subagent_store import SubagentStore, parse_subagent_md

SAMPLE_SUBAGENT_MD = """\
---
description: A sample subagent
tags:
  - testing
---
# Sample Subagent

Body content.
"""

MINIMAL_SUBAGENT_MD = """\
---
description: Minimal
---
Body only.
"""

NO_FRONTMATTER_MD = """\
# No Frontmatter

Just content.
"""


class TestParseSubagentMd:
    def test_parses_full_subagent(self):
        subagent = parse_subagent_md("sample-subagent", SAMPLE_SUBAGENT_MD)
        assert subagent.name == "sample-subagent"
        assert subagent.description == "A sample subagent"
        assert subagent.tags == ["testing"]
        assert subagent.content_hash != ""

    def test_parses_minimal(self):
        subagent = parse_subagent_md("minimal", MINIMAL_SUBAGENT_MD)
        assert subagent.description == "Minimal"
        assert subagent.tags == []

    def test_no_frontmatter(self):
        subagent = parse_subagent_md("bare", NO_FRONTMATTER_MD)
        assert subagent.description == ""


class TestSubagentStore:
    @pytest.fixture
    def store(self, tmp_path):
        return SubagentStore(root=tmp_path, create=True)

    @pytest.fixture
    def populated_store(self, store):
        store.write("alpha", SAMPLE_SUBAGENT_MD)
        store.write("beta", MINIMAL_SUBAGENT_MD)
        return store

    def test_write_and_read(self, store):
        store.write("my-subagent", SAMPLE_SUBAGENT_MD)
        subagent = store.read("my-subagent")
        assert subagent is not None
        assert subagent.name == "my-subagent"
        assert subagent.description == "A sample subagent"

    def test_write_creates_file(self, store):
        path = store.write("new-subagent", MINIMAL_SUBAGENT_MD)
        assert path.exists()
        assert path.name == "new-subagent.md"

    def test_write_plain_frontmatter_is_preserved(self, store):
        """Writing content without fork:true leaves frontmatter unchanged."""
        path = store.write("plain-sub", SAMPLE_SUBAGENT_MD)
        text = path.read_text(encoding="utf-8")
        assert "fork:" not in text
        assert store.exists("plain-sub")

    def test_write_no_frontmatter_still_included(self, store):
        """Writing bare markdown (no frontmatter) is still listed as a subagent."""
        store.write("bare-sub", NO_FRONTMATTER_MD)
        assert store.exists("bare-sub")
        assert "bare-sub" in store.list_names()

    def test_read_nonexistent_returns_none(self, store):
        assert store.read("nonexistent") is None

    def test_read_raw(self, store):
        store.write("my-subagent", SAMPLE_SUBAGENT_MD)
        raw = store.read_raw("my-subagent")
        assert raw is not None
        assert "A sample subagent" in raw

    def test_read_raw_nonexistent(self, store):
        assert store.read_raw("nope") is None

    def test_list_names(self, populated_store):
        names = populated_store.list_names()
        assert sorted(names) == ["alpha", "beta"]

    def test_list_names_empty(self, store):
        assert store.list_names() == []

    def test_list_names_includes_plain_md_files(self, store):
        """All .md files are included — no fork:true filter."""
        store.write("real-subagent", SAMPLE_SUBAGENT_MD)
        claude_style_path = store.root / "claude-style.md"
        claude_style_path.write_text(
            "---\nname: claude-style\ndescription: Claude-style subagent\n---\nBody.",
            encoding="utf-8",
        )
        names = store.list_names()
        assert "real-subagent" in names
        assert "claude-style" in names

    def test_exists(self, populated_store):
        assert populated_store.exists("alpha")
        assert not populated_store.exists("nonexistent")

    def test_delete(self, populated_store):
        assert populated_store.delete("alpha")
        assert not populated_store.exists("alpha")

    def test_delete_nonexistent(self, store):
        assert not store.delete("nope")

    def test_copy_from(self, tmp_path):
        src_store = SubagentStore(root=tmp_path / "src", create=True)
        dst_store = SubagentStore(root=tmp_path / "dst", create=True)

        src_store.write("my-subagent", SAMPLE_SUBAGENT_MD)
        assert dst_store.copy_from(src_store, "my-subagent")
        assert dst_store.exists("my-subagent")

        subagent = dst_store.read("my-subagent")
        assert subagent is not None
        assert subagent.description == "A sample subagent"

    def test_copy_from_nonexistent(self, tmp_path):
        src_store = SubagentStore(root=tmp_path / "src", create=True)
        dst_store = SubagentStore(root=tmp_path / "dst", create=True)
        assert not dst_store.copy_from(src_store, "nope")

    def test_write_rejects_invalid_name(self, store):
        with pytest.raises(ValueError, match="kebab-case"):
            store.write("Not Valid", SAMPLE_SUBAGENT_MD)

    def test_root_property(self, tmp_path):
        store = SubagentStore(root=tmp_path / "subagents", create=True)
        assert store.root == (tmp_path / "subagents")

    def test_create_false_does_not_create_dir(self, tmp_path):
        root = tmp_path / "does-not-exist"
        store = SubagentStore(root=root)
        assert not root.exists()
        assert store.list_names() == []
