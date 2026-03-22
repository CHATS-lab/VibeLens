# VibeLens

[![PyPI version](https://img.shields.io/pypi/v/vibelens.svg)](https://pypi.org/project/vibelens/)
[![Python 3.12+](https://img.shields.io/pypi/pyversions/vibelens.svg)](https://pypi.org/project/vibelens/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

Agent trajectory visualization and analysis platform. Parses, normalizes, and visualizes conversation histories from coding agent CLIs using the [ATIF v1.6](https://github.com/harbor-framework/harbor/blob/main/docs/rfcs/0001-trajectory-format.md) trajectory model.

![Session list with step timeline](https://raw.githubusercontent.com/yejh123/VibeLens/main/figures/demo1.png)

![Session detail with sub-agent view](https://raw.githubusercontent.com/yejh123/VibeLens/main/figures/demo2.png)

**Live Demo:** [vibelens.chats-lab.org](https://vibelens.chats-lab.org/)

## Features

- **Multi-agent parsing** — Claude Code, Codex CLI, Gemini CLI, and Dataclaw formats with auto-detection
- **Step timeline** — Visual timeline with elapsed time, tool call details, and sub-agent spawn indicators

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

VibeLens opens your browser automatically and reads your local `~/.claude/` sessions by default. Use `--no-open` to disable the browser auto-open.

### Development install

```bash
git clone https://github.com/yejh123/VibeLens.git
cd VibeLens
uv sync
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

## Data Donation

VibeLens supports donating your agent conversation data to advance research on coding agent behavior. Donated sessions are collected by [CHATS-Lab](https://github.com/CHATS-lab) (Conversation, Human-AI Technology, and Safety Lab) at Northeastern University.

We welcome contributions of real-world coding agent trajectories across all supported formats. Your data helps the research community better understand how developers interact with AI coding assistants.

To donate, upload your data, select the sessions you want to donate, and click the **Donate** button.

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
