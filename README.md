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

<p align="center">
  <a href="README.md">English</a> &middot;
  <a href="README.zh-CN.md">中文</a>
</p>

---

<p align="center">
  <img src="figures/comic-blurb.jpg" alt="VibeLens Comic: Understand your agent. Teach it. Master it.">
</p>

<p align="center"><em>Let your agent know you better!</em></p>

---

**Sound familiar**?

- Your agent is powerful, but it doesn't know you.
- So many agent skills out there. Which ones actually fit your workflow?
- Your agent keeps repeating the same mistakes.
- Running an agent team but no idea what they're doing.

**Why VibeLens**:

- **Personalization**: Turns your real sessions into reusable skills your agent can load.
- **Productivity tips**: Spots where the agent got stuck or went off track, and tells you how to fix it.
- **Session visualization**: Replays what actually happened, step by step.
- **Multi-agent support**: 11 local agents (Claude, Codex, Gemini, Cursor, Copilot, Kilo, Kiro, OpenCode, OpenClaw, Hermes, CodeBuddy).
- **Dashboard analytics**: Show usage heatmaps, cost breakdowns, and per-project stats.

> **Just want a look?** Try the [live demo](https://vibelens.chats-lab.org/). Nothing to install.

## Quick Start

**Requirement:** either [uv](https://docs.astral.sh/uv/) (preferred) or Python 3.10+.

<details>
<summary><b>Don't have uv or Python yet?</b></summary>

**Install uv** (recommended, single binary, no Python needed):

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
# or: brew install uv
```
```powershell
# Windows
irm https://astral.sh/uv/install.ps1 | iex
# or: winget install --id=astral-sh.uv -e
```

**Install or upgrade Python 3.10+** (alternative):

```bash
# macOS
brew install python@3.12

# Debian / Ubuntu
sudo apt update && sudo apt install -y python3 python3-pip

# Fedora / RHEL
sudo dnf install -y python3 python3-pip

# Arch
sudo pacman -S python python-pip
```
```powershell
# Windows
winget install --id Python.Python.3.12 -e
# or: choco install python
```

Official downloads: [python.org](https://www.python.org/downloads/) · [uv docs](https://docs.astral.sh/uv/getting-started/installation/)
</details>

Run the one-liner:

```bash
# macOS / Linux. Paste into Terminal.
curl -LsSf https://raw.githubusercontent.com/CHATS-lab/VibeLens/main/install.sh | sh
```
```powershell
# Windows. Paste into PowerShell.
irm https://raw.githubusercontent.com/CHATS-lab/VibeLens/main/install.ps1 | iex
```

After installation, start VibeLens any time with:

```bash
vibelens serve
```

VibeLens opens on **http://localhost:12001** and your browser launches automatically.

Change it with `--port` (for example, `vibelens serve --port 8080`). Press `Ctrl+C` to stop.

<details>
<summary><b><code>vibelens: command not found</code> after a uv install?</b></summary>

This happens when uv's tool bin directory isn't on your shell's `PATH`. The installer tries to fix this automatically, but the change only takes effect in **new terminals**. Try one of:

1. **Open a new terminal** and run `vibelens serve` again.
2. **Run the PATH fix manually**, then reopen your terminal:
   ```bash
   uv tool update-shell
   ```
3. **Add it to PATH yourself** (replace the path with what `uv tool dir --bin` prints):
   ```bash
   echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc   # or ~/.bashrc
   source ~/.zshrc
   ```
4. **Skip the shim entirely** and always use:
   ```bash
   uvx vibelens serve
   ```

</details>

<details>
<summary><b>Prefer a manual install?</b></summary>

| Your situation | Command |
|----------------|---------|
| Have `uv` | `uv tool install vibelens && uv tool update-shell` (then open a new terminal and run `vibelens serve`) |
| Have Python 3.10+ | `pip install vibelens && vibelens serve` |
| Want to run without installing | `uvx vibelens serve` |
| Prefer the npm workflow (Python also required) | `npx @chats-lab/vibelens serve` |
| Want to hack on VibeLens | [developer setup](#developer-setup) |

The npm wrapper requires Python 3.10+ and an installed `vibelens` package. It's a convenience layer, not a replacement. Install globally with `npm install -g @chats-lab/vibelens` if you prefer.

Full install guide and troubleshooting: [docs/INSTALL.md](docs/INSTALL.md).

</details>

## Supported Agents

| Agent | Format | Data Location |
|-------|--------|---------------|
| **Claude Code** | JSONL | `~/.claude/projects/` |
| **Codex CLI** | JSONL + SQLite | `~/.codex/sessions/` |
| **Gemini CLI** | JSON | `~/.gemini/tmp/` |
| **Cursor** | SQLite | `~/.cursor/chats/` |
| **GitHub Copilot CLI** | JSONL | `~/.copilot/session-state/` |
| **Kilo Code** | SQLite | `~/.local/share/kilo/` |
| **Kiro** | JSONL + JSON | `~/.kiro/sessions/` |
| **OpenCode** | SQLite | `~/.local/share/opencode/` |
| **OpenClaw** | JSONL | `~/.openclaw/agents/` |
| **Hermes** | JSONL + SQLite | `~/.hermes/sessions/` |
| **CodeBuddy** | JSONL | `~/.codebuddy/projects/` |
| **Claude.ai (web)** | exported JSON | drag-and-drop upload |

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


### Developer setup

```bash
git clone https://github.com/CHATS-lab/VibeLens.git
cd VibeLens
uv sync --extra dev
uv run vibelens serve
```

### Uninstall

Match the command to how you installed:

```bash
# Installed with uv (one-liner picked this path, or you ran `uv tool install`)
uv tool uninstall vibelens

# Installed with pip
pip uninstall vibelens

# Installed globally via npm
npm uninstall -g @chats-lab/vibelens
```

VibeLens stores logs and cached data under `~/.vibelens/` and `logs/` in the working directory. Remove them if you want a clean slate:

```bash
rm -rf ~/.vibelens
```

## Data Donation

VibeLens supports donating your agent session data to advance research on coding agent behavior. Donated sessions are collected by [CHATS-Lab](https://github.com/CHATS-lab) (Conversation, Human-AI Technology, and Safety Lab) at Northeastern University.

To donate, upload your data, select the sessions you want to share, and click the **Donate Data** button.

## Contributing

Contributions are welcome! Please ensure code passes `ruff check` and `pytest` before submitting.

## License

[MIT](LICENSE)
