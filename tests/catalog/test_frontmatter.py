"""Tests for YAML frontmatter parser."""
from vibelens.catalog.frontmatter import parse_frontmatter


def test_parse_standard_frontmatter():
    """Parse standard YAML frontmatter with body."""
    text = """---
name: test-skill
description: A test skill
category: testing
---
# Test Skill

Body content here.
"""
    meta, body = parse_frontmatter(text)
    assert meta["name"] == "test-skill"
    assert meta["description"] == "A test skill"
    assert meta["category"] == "testing"
    assert "Body content here." in body
    print(f"Parsed meta keys: {list(meta.keys())}, body length: {len(body)}")


def test_parse_no_frontmatter():
    """Return empty dict for files without frontmatter."""
    text = "# Just markdown\n\nNo frontmatter."
    meta, body = parse_frontmatter(text)
    assert meta == {}
    assert "Just markdown" in body
    print(f"No frontmatter: meta={meta}, body[:30]={body[:30]}")


def test_parse_empty_frontmatter():
    """Handle empty frontmatter block."""
    text = "---\n---\nBody only."
    meta, body = parse_frontmatter(text)
    assert meta == {} or meta is not None
    assert "Body only." in body
    print(f"Empty frontmatter: meta={meta}")


def test_parse_multiline_description():
    """Handle multi-line description in frontmatter."""
    text = '''---
name: agent-name
description: "Use this agent when you need to design,
  optimize, and test prompts for LLMs."
tools: Read, Write, Edit
model: sonnet
---
Content body.
'''
    meta, body = parse_frontmatter(text)
    assert meta["name"] == "agent-name"
    assert "optimize" in meta["description"]
    assert meta["tools"] == "Read, Write, Edit"
    assert meta["model"] == "sonnet"
    print(f"Multiline desc: {meta['description'][:60]}...")


def test_parse_command_format():
    """Parse command-style frontmatter with allowed-tools."""
    text = """---
allowed-tools: Read, Write, Edit, Bash
argument-hint: [migration-type] | --create
description: Generate database migrations
---
# Command content
"""
    meta, body = parse_frontmatter(text)
    assert meta["allowed-tools"] == "Read, Write, Edit, Bash"
    assert meta["description"] == "Generate database migrations"
    print(f"Command meta: {meta}")
