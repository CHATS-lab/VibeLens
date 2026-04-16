"""Tests for SkillStore — dumb I/O wrapper for skill directories."""

import pytest

from vibelens.storage.extension.skill_store import (
    SkillStore,
    parse_skill_md,
)
from vibelens.utils.content import extract_body, parse_frontmatter

SAMPLE_SKILL_MD = """\
---
description: A sample skill for testing
tags:
  - testing
  - demo
allowed-tools: Bash, Read
---
# Sample Skill

This is the body.
"""

MINIMAL_SKILL_MD = """\
---
description: Minimal
---
Body only.
"""

NO_FRONTMATTER_MD = """\
# No Frontmatter

Just content.
"""


class TestParseFrontmatter:
    def test_parses_yaml(self):
        fm = parse_frontmatter(SAMPLE_SKILL_MD)
        assert fm["description"] == "A sample skill for testing"
        assert fm["tags"] == ["testing", "demo"]
        assert fm["allowed-tools"] == "Bash, Read"

    def test_empty_on_no_frontmatter(self):
        fm = parse_frontmatter(NO_FRONTMATTER_MD)
        assert fm == {}

    def test_empty_on_empty_string(self):
        fm = parse_frontmatter("")
        assert fm == {}


class TestExtractBody:
    def test_extracts_after_frontmatter(self):
        body = extract_body(SAMPLE_SKILL_MD)
        assert body.startswith("# Sample Skill")
        assert "---" not in body

    def test_returns_full_text_without_frontmatter(self):
        body = extract_body(NO_FRONTMATTER_MD)
        assert body == NO_FRONTMATTER_MD


class TestParseSkillMd:
    def test_parses_full_skill(self):
        skill = parse_skill_md("sample-skill", SAMPLE_SKILL_MD)
        assert skill.name == "sample-skill"
        assert skill.description == "A sample skill for testing"
        assert skill.tags == ["testing", "demo"]
        assert skill.allowed_tools == ["Bash", "Read"]
        assert skill.content_hash != ""

    def test_parses_minimal(self):
        skill = parse_skill_md("minimal", MINIMAL_SKILL_MD)
        assert skill.description == "Minimal"
        assert skill.tags == []
        assert skill.allowed_tools == []

    def test_no_frontmatter(self):
        skill = parse_skill_md("bare", NO_FRONTMATTER_MD)
        assert skill.description == ""


class TestSkillStore:
    @pytest.fixture
    def store(self, tmp_path):
        return SkillStore(root=tmp_path, create=True)

    @pytest.fixture
    def populated_store(self, store):
        store.write("alpha", SAMPLE_SKILL_MD)
        store.write("beta", MINIMAL_SKILL_MD)
        return store

    def test_write_and_read(self, store):
        store.write("my-skill", SAMPLE_SKILL_MD)
        skill = store.read("my-skill")
        assert skill is not None
        assert skill.name == "my-skill"
        assert skill.description == "A sample skill for testing"

    def test_write_creates_directory(self, store):
        path = store.write("new-skill", MINIMAL_SKILL_MD)
        assert path.exists()
        assert path.name == "SKILL.md"

    def test_read_nonexistent_returns_none(self, store):
        assert store.read("nonexistent") is None

    def test_read_raw(self, store):
        store.write("my-skill", SAMPLE_SKILL_MD)
        raw = store.read_raw("my-skill")
        assert raw is not None
        assert "A sample skill for testing" in raw

    def test_read_raw_nonexistent(self, store):
        assert store.read_raw("nope") is None

    def test_list_names(self, populated_store):
        names = populated_store.list_names()
        assert sorted(names) == ["alpha", "beta"]

    def test_list_names_empty(self, store):
        assert store.list_names() == []

    def test_exists(self, populated_store):
        assert populated_store.exists("alpha")
        assert not populated_store.exists("nonexistent")

    def test_delete(self, populated_store):
        assert populated_store.delete("alpha")
        assert not populated_store.exists("alpha")

    def test_delete_nonexistent(self, store):
        assert not store.delete("nope")

    def test_copy_from(self, tmp_path):
        src_store = SkillStore(root=tmp_path / "src", create=True)
        dst_store = SkillStore(root=tmp_path / "dst", create=True)

        src_store.write("my-skill", SAMPLE_SKILL_MD)
        assert dst_store.copy_from(src_store, "my-skill")
        assert dst_store.exists("my-skill")

        skill = dst_store.read("my-skill")
        assert skill is not None
        assert skill.description == "A sample skill for testing"

    def test_copy_from_nonexistent(self, tmp_path):
        src_store = SkillStore(root=tmp_path / "src", create=True)
        dst_store = SkillStore(root=tmp_path / "dst", create=True)
        assert not dst_store.copy_from(src_store, "nope")

    def test_write_rejects_invalid_name(self, store):
        with pytest.raises(ValueError, match="kebab-case"):
            store.write("Not Valid", "content")

    def test_root_property(self, tmp_path):
        store = SkillStore(root=tmp_path / "skills", create=True)
        assert store.root == (tmp_path / "skills")

    def test_create_false_does_not_create_dir(self, tmp_path):
        root = tmp_path / "does-not-exist"
        store = SkillStore(root=root)
        assert not root.exists()
        assert store.list_names() == []
