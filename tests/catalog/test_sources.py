"""Tests for catalog source parsers."""
import json
from pathlib import Path

from vibelens.catalog.sources.buildwithclaude import parse_buildwithclaude
from vibelens.catalog.sources.templates import parse_templates
from vibelens.models.recommendation.catalog import ItemType


def _write_md(path: Path, name: str, desc: str, category: str = "testing") -> None:
    """Write a markdown file with frontmatter."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"""---
name: {name}
description: {desc}
category: {category}
---
# {name}
Body content for {name}.
""")


def _write_json(path: Path, data: dict) -> None:
    """Write a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def test_bwc_parses_agents(tmp_path: Path):
    """Parse agent markdown files from buildwithclaude plugins."""
    plugin_dir = tmp_path / "plugins" / "agents-design"
    _write_md(
        plugin_dir / "agents" / "accessibility-expert.md",
        "accessibility-expert",
        "Ensures WCAG compliance",
        "design-experience",
    )
    items = parse_buildwithclaude(tmp_path)
    agents = [i for i in items if i.item_type == ItemType.SUBAGENT]
    assert len(agents) == 1
    assert agents[0].name == "accessibility-expert"
    assert agents[0].item_id == "bwc:agent:accessibility-expert"
    assert agents[0].install_content is not None
    assert "WCAG" in agents[0].description
    print(f"BWC agent: {agents[0].item_id} — {agents[0].description}")


def test_bwc_parses_commands(tmp_path: Path):
    """Parse command markdown files."""
    plugin_dir = tmp_path / "plugins" / "commands-api"
    _write_md(
        plugin_dir / "commands" / "design-rest-api.md",
        "design-rest-api",
        "Generate REST API designs",
        "api-development",
    )
    items = parse_buildwithclaude(tmp_path)
    commands = [i for i in items if i.item_type == ItemType.COMMAND]
    assert len(commands) == 1
    assert commands[0].item_id == "bwc:command:design-rest-api"
    print(f"BWC command: {commands[0].item_id}")


def test_bwc_parses_skills(tmp_path: Path):
    """Parse skill SKILL.md files."""
    plugin_dir = tmp_path / "plugins" / "all-skills"
    skill_dir = plugin_dir / "skills" / "my-skill"
    _write_md(skill_dir / "SKILL.md", "my-skill", "Does cool things", "automation")
    items = parse_buildwithclaude(tmp_path)
    skills = [i for i in items if i.item_type == ItemType.SKILL]
    assert len(skills) == 1
    assert skills[0].item_id == "bwc:skill:my-skill"
    print(f"BWC skill: {skills[0].item_id}")


def test_bwc_parses_hooks(tmp_path: Path):
    """Parse hook JSON files."""
    plugin_dir = tmp_path / "plugins" / "project-boundary"
    _write_json(
        plugin_dir / "hooks" / "hooks.json",
        {
            "description": "Blocks dangerous commands",
            "hooks": {
                "PreToolUse": [
                    {"matcher": "Bash", "hooks": [{"type": "command", "command": "bash guard.sh"}]}
                ]
            },
        },
    )
    items = parse_buildwithclaude(tmp_path)
    hooks = [i for i in items if i.item_type == ItemType.HOOK]
    assert len(hooks) == 1
    assert hooks[0].item_id == "bwc:hook:project-boundary"
    assert hooks[0].install_content is not None
    print(f"BWC hook: {hooks[0].item_id}")


def test_bwc_parses_mcp_servers(tmp_path: Path):
    """Parse mcp-servers.json."""
    _write_json(
        tmp_path / "mcp-servers.json",
        {
            "mcpServers": {
                "github-server": {
                    "command": "docker",
                    "args": ["run", "-i", "--rm", "mcp/github"],
                    "_metadata": {
                        "displayName": "GitHub Server",
                        "category": "development",
                        "description": "Access GitHub repos from agent sessions",
                    },
                }
            }
        },
    )
    items = parse_buildwithclaude(tmp_path)
    mcps = [i for i in items if i.item_type == ItemType.REPO]
    assert len(mcps) == 1
    assert mcps[0].item_id == "bwc:mcp:github-server"
    assert mcps[0].name == "GitHub Server"
    assert mcps[0].install_command == "docker run -i --rm mcp/github"
    print(f"BWC MCP: {mcps[0].item_id} — {mcps[0].install_command}")


def test_bwc_empty_dir(tmp_path: Path):
    """Return empty list for missing or empty directory."""
    items = parse_buildwithclaude(tmp_path)
    assert items == []
    print("BWC empty dir: 0 items")


def test_cct_parses_agents(tmp_path: Path):
    """Parse agent .md files from claude-code-templates."""
    comp_dir = tmp_path / "cli-tool" / "components"
    _write_md(
        comp_dir / "agents" / "ai-specialists" / "prompt-engineer.md",
        "prompt-engineer",
        "Design and optimize LLM prompts",
        "ai-specialists",
    )
    items = parse_templates(tmp_path)
    agents = [i for i in items if i.item_type == ItemType.SUBAGENT]
    assert len(agents) == 1
    assert agents[0].item_id == "cct:agent:prompt-engineer"
    assert agents[0].install_content is not None
    print(f"CCT agent: {agents[0].item_id}")


def test_cct_parses_skills(tmp_path: Path):
    """Parse skill SKILL.md from claude-code-templates."""
    comp_dir = tmp_path / "cli-tool" / "components"
    _write_md(
        comp_dir / "skills" / "design-to-code" / "SKILL.md",
        "design-to-code",
        "Figma to React conversion",
    )
    items = parse_templates(tmp_path)
    skills = [i for i in items if i.item_type == ItemType.SKILL]
    assert len(skills) == 1
    assert skills[0].item_id == "cct:skill:design-to-code"
    print(f"CCT skill: {skills[0].item_id}")


def test_cct_parses_mcps(tmp_path: Path):
    """Parse MCP JSON files from claude-code-templates."""
    comp_dir = tmp_path / "cli-tool" / "components"
    _write_json(
        comp_dir / "mcps" / "deepgraph" / "deepgraph-typescript.json",
        {
            "mcpServers": {
                "DeepGraph TypeScript MCP": {
                    "description": "TypeScript code analysis",
                    "command": "npx",
                    "args": ["-y", "mcp-code-graph@latest"],
                }
            }
        },
    )
    items = parse_templates(tmp_path)
    mcps = [i for i in items if i.item_type == ItemType.REPO]
    assert len(mcps) == 1
    assert mcps[0].item_id == "cct:mcp:deepgraph/deepgraph-typescript"
    print(f"CCT MCP: {mcps[0].item_id}")


def test_cct_excludes_settings(tmp_path: Path):
    """Settings directory is excluded from parsing."""
    comp_dir = tmp_path / "cli-tool" / "components"
    (comp_dir / "settings" / "general").mkdir(parents=True)
    (comp_dir / "settings" / "general" / "theme.json").write_text('{"theme": "dark"}')
    items = parse_templates(tmp_path)
    assert len(items) == 0
    print("CCT settings excluded: 0 items")


def test_cct_parses_hooks(tmp_path: Path):
    """Parse hook JSON files from claude-code-templates."""
    comp_dir = tmp_path / "cli-tool" / "components"
    _write_json(
        comp_dir / "hooks" / "security" / "secret-scanner.json",
        {
            "description": "Detects hardcoded secrets before commits",
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [{"type": "command", "command": "python3 scanner.py"}],
                    }
                ]
            },
        },
    )
    items = parse_templates(tmp_path)
    hooks = [i for i in items if i.item_type == ItemType.HOOK]
    assert len(hooks) == 1
    assert hooks[0].item_id == "cct:hook:security/secret-scanner"
    print(f"CCT hook: {hooks[0].item_id}")
