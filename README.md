<p align="center">
  <img src="figures/logo.png" alt="VibeLens" width="120">
</p>

<h1 align="center">VibeLens</h1>

<p align="center">
  <strong>See what your AI coding agents are actually doing.</strong><br>
  Replay. Analyze. Evolve.
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
  <a href="#supported-agents">Supported Agents</a> &middot;
  <a href="https://pypi.org/project/vibelens/">PyPI</a> &middot;
  <a href="CHANGELOG.md">Changelog</a>
</p>

---

<p align="center">
  <img src="figures/comic-blurb.jpg" alt="VibeLens Comic — Understand your agent. Teach it. Master it.">
</p>

<p align="center"><em>Let your agent know you better!</em></p>

---

Your AI coding agents run hundreds of tool calls, burn thousands of tokens, and you have no idea what happened. VibeLens changes that.

```bash
# macOS / Linux. Paste into Terminal.
curl -LsSf https://raw.githubusercontent.com/CHATS-lab/VibeLens/main/install.sh | sh
```

No Python, no pip, nothing to set up first. The script installs [uv](https://docs.astral.sh/uv/) (a single binary), fetches VibeLens, and opens it in your browser.

> **Just want a look?** Try the [live demo](https://vibelens.chats-lab.org/). Nothing to install.

One install. Reads local logs. Works with **Claude Code**, **Codex CLI**, **Gemini CLI**, and **OpenClaw** out of the box.

## Features

| Feature | Description |
|---------|-------------|
| **Session visualization** | Step-by-step timeline with tool calls, thinking, and sub-agents |
| **Dashboard analytics** | Usage heatmaps, cost breakdowns, and per-project stats |
| **Productivity tips** _(needs LLM key or Agent)_ | Detects recurring frustration patterns and suggests concrete fixes |
| **Personalization** _(needs LLM key or Agent)_ | Retrieve, customize, and evolve reusable skills from your real sessions |
| **Session sharing** | Share sessions via one-click links |
| **Multi-agent support** | Claude Code, Codex CLI, Gemini CLI, OpenClaw with auto-detection |

## Supported Agents

| Agent | Format | Data Location |
|-------|--------|---------------|
| **Claude Code** | JSONL | `~/.claude/projects/` |
| **Codex CLI** | JSONL | `~/.codex/sessions/` |
| **Gemini CLI** | JSON | `~/.gemini/tmp/` |
| **OpenClaw** | JSONL | `~/.openclaw/agents/` |
| **Hermes Agent** | JSONL | `~/.hermes/sessions/` |

VibeLens auto-detects the agent format. Just point it at your session directory and it works.

## Screenshots

### Session Visualization & Dashboard Analytics

<table>
  <tr>
    <td width="50%">
      <kbd><img src="figures/01-conversation.png" alt="Session Visualization" width="100%" /></kbd>
      <p align="center"><b>Session Visualization</b><br>Step-by-step timeline with messages, tool calls, thinking blocks, and sub-agent spawns.</p>
    </td>
    <td width="50%">
      <kbd><img src="figures/02-dashboard.png" alt="Dashboard Analytics" width="100%" /></kbd>
      <p align="center"><b>Dashboard Analytics</b><br>Usage heatmaps, cost breakdowns by model, and per-project drill-downs.</p>
    </td>
  </tr>
</table>

### Productivity Tips & Personalization

<table>
  <tr>
    <td width="50%">
      <kbd><img src="figures/03-productivity-tips.png" alt="Productivity Tips" width="100%" /></kbd>
      <p align="center"><b>Productivity Tips</b><br>Detect friction patterns and get concrete suggestions to improve your workflow.</p>
    </td>
    <td width="50%">
      <kbd><img src="figures/04-skill-retrieval.png" alt="Skill Recommendation" width="100%" /></kbd>
      <p align="center"><b>Skill Recommendation</b><br>Match workflow patterns to pre-built skills from the catalog.</p>
    </td>
  </tr>
  <tr>
    <td width="50%">
      <kbd><img src="figures/05-skill-creation.png" alt="Skill Customization" width="100%" /></kbd>
      <p align="center"><b>Skill Customization</b><br>Generate new SKILL.md files tailored to your session patterns.</p>
    </td>
    <td width="50%">
      <kbd><img src="figures/06-skill-evolution.png" alt="Skill Evolution" width="100%" /></kbd>
      <p align="center"><b>Skill Evolution</b><br>Evolve installed skills with targeted edits based on your real sessions.</p>
    </td>
  </tr>
</table>

## Quick Start

### One-liner (recommended)

Zero prerequisites: no Python, no pip. The commands below install [uv](https://docs.astral.sh/uv/) first, then run VibeLens.

```bash
# macOS / Linux. Paste into Terminal.
curl -LsSf https://raw.githubusercontent.com/CHATS-lab/VibeLens/main/install.sh | sh
```

```powershell
# Windows. Paste into PowerShell.
irm https://raw.githubusercontent.com/CHATS-lab/VibeLens/main/install.ps1 | iex
```

VibeLens starts on **http://localhost:12001** and your browser opens automatically. Change it with `--port` (for example, `vibelens serve --port 8080`).

### Pick your path

| Your situation | Command |
|----------------|---------|
| **Nothing installed** (recommended) | one-liner above |
| Already have Python 3.10+ | `pip install vibelens && vibelens serve` |
| Prefer the npm workflow (Python also required) | `npx @chats-lab/vibelens serve` |
| Want to hack on VibeLens | [developer setup](#developer-setup) |

### What happens on first run

1. Your browser opens to **http://localhost:12001**.
2. If you have Claude Code, Codex CLI, Gemini CLI, or OpenClaw sessions, VibeLens auto-detects them from `~/.claude/`, `~/.codex/`, `~/.gemini/`, or `~/.openclaw/`.
3. Otherwise, bundled example sessions (recipe-book) show up so you can look around.
4. **Productivity Tips** and **Personalization** need a language-model API key. Optional; configure later in Settings.

### pip (if you already have Python 3.10+)

```bash
pip install vibelens
vibelens serve
```

Check your version first with `python3 --version`. Need Python? See [docs/INSTALL.md](docs/INSTALL.md#installing-python).

### uv (run without a permanent install)

```bash
uvx vibelens serve
```

This fetches VibeLens into uv's cache and runs it without a global install. The one-liner above calls this under the hood.

### npm (if you already have Python and prefer the npm workflow)

VibeLens is a Python app with an npm wrapper for convenience. The wrapper still requires **Python 3.10+** and an installed `vibelens` package. Use this when you already have both and want `npx`/`npm` ergonomics.

```bash
npx @chats-lab/vibelens serve
```

Or install globally: `npm install -g @chats-lab/vibelens`.

### Developer setup

```bash
git clone https://github.com/CHATS-lab/VibeLens.git
cd VibeLens
uv sync --extra dev
uv run vibelens serve
```

### Configuration

YAML configuration with environment variable overrides (`VIBELENS_*`). See [`config/vibelens.example.yaml`](config/vibelens.example.yaml) for all options.

```bash
# Use a config file
vibelens serve --config config/self-use.yaml

# Override host/port
vibelens serve --host 0.0.0.0 --port 8080
```

### Troubleshooting

Top issues. For the full list, see [docs/INSTALL.md](docs/INSTALL.md#troubleshooting).

## Data Donation

VibeLens supports donating your agent session data to advance research on coding agent behavior. Donated sessions are collected by [CHATS-Lab](https://github.com/CHATS-lab) (Conversation, Human-AI Technology, and Safety Lab) at Northeastern University.

To donate, upload your data, select the sessions you want to share, and click the **Donate Data** button.

## Contributing

Contributions are welcome! Please ensure code passes `ruff check` and `pytest` before submitting.

## License

[MIT](LICENSE)
