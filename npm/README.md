# vibelens

Agent trajectory analysis and visualization platform. Parses, normalizes, and visualizes conversation histories from Claude Code, Codex, Gemini CLI, and more.

## Install

```bash
npx vibelens serve
```

Or install globally:

```bash
npm install -g vibelens
vibelens serve
```

## Requirements

- **Python 3.10+** must be installed on your system
- The `vibelens` Python package: `pip install vibelens`

This npm package is a thin wrapper that detects your Python installation and delegates to the `vibelens` CLI. If Python or the `vibelens` package is missing, it will print install instructions.

## Other install methods

| Method | Command |
|--------|---------|
| pip | `pip install vibelens` |
| Homebrew | `brew install chats-lab/tap/vibelens` |
| Developer | `uv pip install -e ".[dev]"` |

## Links

- [Homepage](https://vibelens.chats-lab.org/)
- [GitHub](https://github.com/CHATS-lab/VibeLens)
- [PyPI](https://pypi.org/project/vibelens/)
