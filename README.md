<p align="center">
  <img src="figures/icon.png" alt="VibeLens" width="120">
</p>

<h1 align="center">VibeLens</h1>

<p align="center">
  <strong>See what your AI coding agents are actually doing.</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/vibelens/"><img src="https://img.shields.io/pypi/v/vibelens?color=%2334D058" alt="PyPI"></a>
  <a href="https://pypi.org/project/vibelens/"><img src="https://img.shields.io/pypi/pyversions/vibelens" alt="Python"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License"></a>
  <a href="https://vibelens.chats-lab.org/"><img src="https://img.shields.io/badge/demo-live-brightgreen" alt="Live Demo"></a>
</p>

<p align="center">
  <a href="https://vibelens.chats-lab.org/">Live Demo</a> &middot;
  <a href="#quick-start">Quick Start</a> &middot;
  <a href="https://pypi.org/project/vibelens/">PyPI</a> &middot;
  <a href="CHANGELOG.md">Changelog</a>
</p>

---

<p align="center">
  <img src="figures/comic-blurb.png" alt="VibeLens Comic" width="680">
</p>

<p align="center"><em>Analyze and understand your agent. Evolve it.</em></p>

Your AI coding agents run hundreds of tool calls, burn thousands of tokens, and you have no idea what happened. VibeLens changes that.

- **Session visualization.** Step-by-step timeline with every tool call, thinking block, and sub-agent spawn.
- **Dashboard analytics.** Cost breakdowns by model, peak-hour histograms, and per-project drill-downs.
- **Productivity tips.** Flags retries, circular debugging, and abandoned approaches -- with suggested fixes.
- **Skill personalization.** Recommend, create, and evolve reusable agent skills from your session history.
- **Session sharing.** Share your interactions with your teammates with a link.

Works with **Claude Code**, **Codex CLI**, **Gemini CLI**, and **OpenClaw** out of the box.

```bash
pip install vibelens && vibelens serve
```

### Session Viewer & Dashboard

<table>
  <tr>
    <td width="50%">
      <kbd><img src="figures/01-conversation.png" alt="Session Viewer" width="100%" /></kbd>
      <p align="center"><b>Session Viewer</b><br>Step-by-step timeline with messages, tool calls, and sub-agent spawns.</p>
    </td>
    <td width="50%">
      <kbd><img src="figures/02-dashboard.png" alt="Analytics Dashboard" width="100%" /></kbd>
      <p align="center"><b>Analytics Dashboard</b><br>Aggregate stats, cost estimation, and usage trends over time.</p>
    </td>
  </tr>
</table>

### Productivity Tips & Skill Personalization

<table>
  <tr>
    <td width="50%">
      <kbd><img src="figures/03-productivity-tips.png" alt="Productivity Tips" width="100%" /></kbd>
      <p align="center"><b>Productivity Tips</b><br>Detect friction patterns and get concrete improvement suggestions.</p>
    </td>
    <td width="50%">
      <kbd><img src="figures/04-skill-retrieval.png" alt="Skill Retrieval" width="100%" /></kbd>
      <p align="center"><b>Skill Retrieval</b><br>Match workflow patterns to pre-built skills from the catalog.</p>
    </td>
  </tr>
  <tr>
    <td width="50%">
      <kbd><img src="figures/05-skill-creation.png" alt="Skill Creation" width="100%" /></kbd>
      <p align="center"><b>Skill Creation</b><br>Generate new SKILL.md files from your session history.</p>
    </td>
    <td width="50%">
      <kbd><img src="figures/06-skill-evolution.png" alt="Skill Evolution" width="100%" /></kbd>
      <p align="center"><b>Skill Evolution</b><br>Evolve installed skills with targeted edits based on real usage.</p>
    </td>
  </tr>
</table>

## Features

| Feature | Description |
|---------|-------------|
| **Multi-agent parsing** | Claude Code, Codex CLI, Gemini CLI, OpenClaw with auto-detection |
| **Session Visualization** | Tool calls, sub-agent spawns, elapsed time, image content |
| **Dashboard Analytics** | Cost breakdowns by model, peak-hour histograms, and per-project drill-downs. |
| **Productivity tips** | Friction detection, cross-session patterns, actionable mitigations |
| **Skill personalization** | Retrieve, create, and evolve reusable agent skills |
| **Session sharing** | Shareable URLs with read-only view |

## Quick Start

### Install and run

```bash
pip install vibelens
vibelens serve
```

Or run without installing:

```bash
uvx vibelens serve
```

VibeLens opens your browser and reads your local `~/.claude/` sessions by default.

### Development install

```bash
git clone https://github.com/yejh123/VibeLens.git
cd VibeLens
uv sync --extra dev
uv run vibelens serve
```

### Configuration

YAML-based configuration with environment variable overrides (`VIBELENS_*`). See [`config/vibelens.example.yaml`](config/vibelens.example.yaml) for all options.

```bash
# Use a config file
vibelens serve --config config/self-use.yaml

# Override host/port
vibelens serve --host 0.0.0.0 --port 8080
```

## Supported Agents

| Agent | Format | Data Location |
|-------|--------|---------------|
| **Claude Code** | JSONL | `~/.claude/projects/` |
| **Codex CLI** | JSONL | `~/.codex/sessions/` |
| **Gemini CLI** | JSON | `~/.gemini/tmp/` |
| **OpenClaw** | JSONL | `~/.openclaw/agents/` |

## Data Donation

VibeLens supports donating your agent session data to advance research on coding agent behavior. Donated sessions are collected by [CHATS-Lab](https://github.com/CHATS-lab) (Conversation, Human-AI Technology, and Safety Lab) at Northeastern University.

To donate, upload your data, select the sessions you want to share, and click the **Donate** button.

## Development

```bash
# Lint and test
uv run ruff check src/ tests/
uv run pytest tests/ -v -s

# Frontend dev server (hot reload)
cd frontend && npm install && npm run dev
```

## Contributing

Contributions are welcome! Please ensure code passes `ruff check` and `pytest` before submitting.

## License

[MIT](LICENSE)
