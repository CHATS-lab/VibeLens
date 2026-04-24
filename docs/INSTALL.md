# Installing VibeLens

The one-liner in the [README](../README.md#quick-start) handles most cases. This doc covers everything else: the supported methods, what can go wrong, and how to fix it.

## Requirements

You need **one** of:

- [uv](https://docs.astral.sh/uv/) (preferred, single binary, no Python required)
- Python 3.10 or newer

## Install methods

### 1. One-liner (recommended)

Picks uv if available, otherwise falls back to pip.

```bash
# macOS / Linux
curl -LsSf https://raw.githubusercontent.com/CHATS-lab/VibeLens/main/install.sh | sh
```
```powershell
# Windows
irm https://raw.githubusercontent.com/CHATS-lab/VibeLens/main/install.ps1 | iex
```

### 2. Manual install with uv

```bash
uv tool install vibelens
uv tool update-shell         # adds uv's bin dir to your shell PATH
# Open a new terminal so the PATH change takes effect
vibelens serve
```

### 3. Manual install with pip

```bash
pip install vibelens
vibelens serve
```

If pip can't write to the system Python (`externally-managed-environment`):

```bash
pip install --user vibelens
# Then ensure pip's user bin dir is on PATH:
#   Linux:   ~/.local/bin
#   macOS:   ~/Library/Python/3.X/bin
#   Windows: %APPDATA%\Python\PythonXY\Scripts
```

### 4. Run without installing (uv)

Downloads on first use, caches afterwards:

```bash
uvx vibelens serve
```

### 5. npm wrapper

Requires Python 3.10+ and uses pip under the hood. Convenience only.

```bash
npx @chats-lab/vibelens serve
# or globally:
npm install -g @chats-lab/vibelens
```

### 6. From source (developer setup)

```bash
git clone https://github.com/CHATS-lab/VibeLens.git
cd VibeLens
uv sync --extra dev
uv run vibelens serve
```

## Troubleshooting

### `vibelens: command not found` after a uv install

Happens when uv's tool bin directory isn't on your shell's `PATH`. The installer tries to fix this automatically, but the shell rc edit only takes effect in **new terminals**.

Fix, in order of preference:

1. **Open a new terminal** and retry.
2. **Run the PATH fix manually**, then reopen your terminal:
   ```bash
   uv tool update-shell
   ```
3. **Edit your shell rc directly** (replace the path with what `uv tool dir --bin` prints):
   ```bash
   echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc   # or ~/.bashrc
   source ~/.zshrc
   ```
4. **Skip the shim**. `uvx vibelens serve` always works regardless of PATH.

Windows equivalents for step 3:

```powershell
# this session only
$env:Path = "$(uv tool dir --bin);$env:Path"
# persist (takes effect in new shells)
setx PATH "$(uv tool dir --bin);%PATH%"
```

### `vibelens: command not found` after a pip install

pip installed it to a user-local bin directory that isn't on your `PATH`.

Find the location:

```bash
python3 -m site --user-base
```

Add its `bin` (or `Scripts` on Windows) subdirectory to your `PATH`.

### `externally-managed-environment` error from pip

Some Linux distros and Homebrew Python block system-wide pip installs. Options:

1. Use `--user`: `pip install --user vibelens`
2. Use a venv: `python3 -m venv ~/.vibelens && ~/.vibelens/bin/pip install vibelens`
3. Switch to uv: `curl -LsSf https://astral.sh/uv/install.sh | sh`, then `uv tool install vibelens`

### Port 12001 already in use

```bash
vibelens serve --port 8080
```

### The browser doesn't open automatically

```bash
vibelens serve --no-open
# Then open http://localhost:12001 manually
```

## Uninstalling

Match the command to how you installed:

```bash
# uv
uv tool uninstall vibelens

# pip
pip uninstall vibelens

# npm (global)
npm uninstall -g @chats-lab/vibelens
```

VibeLens stores logs and cached data under `~/.vibelens/`. Remove them if you want a clean slate:

```bash
rm -rf ~/.vibelens
```
