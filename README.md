# VibeLens

Agent trajectory analysis and visualization platform. Parses, normalizes, and visualizes conversation histories from coding agent CLIs using the [ATIF v1.6](https://github.com/agent-trajectory/atif) trajectory model.


![Session list with step timeline](figures/demo1.png)

![Session detail with sub-agent view](figures/demo2.png)

## Features

- **Multi-agent parsing** — Claude Code, Codex CLI, Gemini CLI, and Dataclaw formats with auto-detection
- **Step timeline** — Visual timeline with elapsed time, tool call details, and sub-agent spawn indicators

## Quick Start

```bash
uv sync

# Self-use mode — reads local ~/.claude/ sessions
cp config/self-use.yaml vibelens.yaml
uv run vibelens serve
```

Open `http://127.0.0.1:12001` in your browser.

## Configuration

YAML-based configuration with environment variable overrides (`VIBELENS_*`).

```bash
# Explicit config file
vibelens serve --config config/self-use.yaml

# Override via CLI flags
vibelens serve --host 0.0.0.0 --port 8080
```

## Data Donation

VibeLens supports donating your agent conversation data to advance research on coding agent behavior. Donated sessions are collected by [CHATS-Lab](https://github.com/CHATS-lab) (Conversation, Human-AI Technology, and Safety Lab) at Northeastern University.

We welcome contributions of real-world coding agent trajectories across all supported formats. Your data helps the research community better understand how developers interact with AI coding assistants.

To donate, upload your data, select your sessions, and click the **Donate** button.

## Contributing

Contributions are welcome! Please ensure code passes linting and tests before submitting:

```bash
uv run ruff check src/ tests/
uv run pytest tests/ -v -s
```

## Development

```bash
# Backend
uv run ruff check src/ tests/
uv run pytest tests/ -v -s

# Frontend
cd frontend && npm install && npm run dev
```
