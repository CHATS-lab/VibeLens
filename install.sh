#!/usr/bin/env sh
#
# VibeLens installer for macOS and Linux.
#
# What it does:
#   1. Looks for `uv` on PATH. If found, asks to install VibeLens with
#      `uv tool install vibelens`.
#   2. Otherwise, looks for Python 3.10+. If found, asks to install VibeLens
#      with `pip install vibelens`.
#   3. If neither is available, prints platform-specific install guidance
#      for uv (preferred) and Python, then exits.
#
# After install, the user can start VibeLens any time with:
#   vibelens serve
#
# On the uv path we also run `uv tool update-shell`, which adds uv's tool bin
# directory (e.g. ~/.local/bin) to the user's shell rc so `vibelens` is on PATH
# in future terminals.
#
# Safety:
#   - Never installs dependencies (Python, uv) for you.
#   - Always asks for confirmation before running pip/uv.
#   - Idempotent: re-running with VibeLens already installed re-installs
#     the latest version (with your consent) and starts the app.
#
# Usage:
#   curl -LsSf https://raw.githubusercontent.com/CHATS-lab/VibeLens/main/install.sh | sh

set -eu

MIN_PY_MAJOR=3
MIN_PY_MINOR=10

INSTALL_DOC_URL="https://github.com/CHATS-lab/VibeLens/blob/main/docs/INSTALL.md"
PYTHON_DOC_URL="https://www.python.org/downloads/"
UV_DOC_URL="https://docs.astral.sh/uv/getting-started/installation/"

info() {
  printf '%s\n' "$1"
}

warn() {
  printf '%s\n' "$1" >&2
}

fail() {
  printf 'VibeLens install failed: %s\n' "$1" >&2
  printf 'For manual install steps, see: %s\n' "$INSTALL_DOC_URL" >&2
  exit 1
}

# Read a yes/no answer from the user. When the script is piped through
# `curl ... | sh`, stdin is the script itself, so we read from /dev/tty.
confirm() {
  prompt="$1"
  if [ ! -r /dev/tty ]; then
    warn "No interactive terminal detected (cannot prompt for confirmation)."
    warn "Re-run this command in an interactive shell, or install VibeLens manually."
    return 1
  fi
  printf '%s [y/N]: ' "$prompt" > /dev/tty
  IFS= read -r answer < /dev/tty || return 1
  case "$answer" in
    y|Y|yes|YES|Yes) return 0 ;;
    *) return 1 ;;
  esac
}

# Prints the first `pythonX.Y` or `python3` on PATH whose version is >= 3.10.
# Prints nothing if none qualify.
find_python() {
  for candidate in python3.13 python3.12 python3.11 python3.10 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
      version_line=$("$candidate" -c 'import sys; print(sys.version_info[0], sys.version_info[1])' 2>/dev/null || true)
      if [ -z "$version_line" ]; then
        continue
      fi
      major=$(echo "$version_line" | awk '{print $1}')
      minor=$(echo "$version_line" | awk '{print $2}')
      if [ "$major" -gt "$MIN_PY_MAJOR" ] || { [ "$major" -eq "$MIN_PY_MAJOR" ] && [ "$minor" -ge "$MIN_PY_MINOR" ]; }; then
        echo "$candidate"
        return 0
      fi
    fi
  done
  return 1
}

print_python_install_help() {
  os=$(uname -s 2>/dev/null || echo unknown)
  warn ""
  warn "Or install or upgrade Python to 3.10+, then re-run this script:"
  case "$os" in
    Darwin)
      warn "  Homebrew:        brew install python@3.12"
      warn "  Official build:  $PYTHON_DOC_URL"
      ;;
    Linux)
      warn "  Debian/Ubuntu:   sudo apt update && sudo apt install -y python3 python3-pip"
      warn "  Fedora/RHEL:     sudo dnf install -y python3 python3-pip"
      warn "  Arch:            sudo pacman -S python python-pip"
      warn "  Official build:  $PYTHON_DOC_URL"
      ;;
    *)
      warn "  Official build:  $PYTHON_DOC_URL"
      ;;
  esac
}

print_uv_install_help() {
  warn ""
  warn "Install uv (a single binary, no Python required):"
  warn "  curl -LsSf https://astral.sh/uv/install.sh | sh"
  warn "  Homebrew:  brew install uv"
  warn "  Docs:      $UV_DOC_URL"
}

install_with_pip() {
  py="$1"
  info "Found Python at $(command -v "$py") ($("$py" --version 2>&1))."
  info ""
  info "VibeLens will be installed with:"
  info "  $py -m pip install --upgrade vibelens"
  info ""
  if ! confirm "Proceed?"; then
    fail "Install cancelled by user."
  fi
  if ! "$py" -m pip install --upgrade vibelens; then
    warn ""
    warn "pip install failed. This can happen on systems with an 'externally-managed' Python."
    warn "Workarounds:"
    warn "  1. Retry with --user:  $py -m pip install --user --upgrade vibelens"
    warn "  2. Use a virtualenv:   $py -m venv ~/.vibelens && ~/.vibelens/bin/pip install vibelens"
    warn "  3. Install uv and re-run this script (the uv path avoids system Python entirely)."
    fail "pip could not install VibeLens."
  fi
}

install_with_uv() {
  info "Found uv at $(command -v uv)."
  info ""
  info "VibeLens will be installed with:"
  info "  uv tool install vibelens"
  info ""
  if ! confirm "Proceed?"; then
    fail "Install cancelled by user."
  fi
  if ! uv tool install vibelens; then
    fail "uv could not install VibeLens."
  fi

  # Figure out where the `vibelens` shim actually lives, so the diagnostics we
  # print below are accurate on this machine (not a guess).
  UV_BIN_DIR=$(uv tool dir --bin 2>/dev/null || true)
  if [ -z "$UV_BIN_DIR" ]; then
    UV_BIN_DIR="$HOME/.local/bin"
  fi

  # Try to edit the user's shell rc so the plain `vibelens` command works in
  # future terminals. `update-shell` is a no-op if the entry is already present.
  # Capture stderr so we can surface anything uv complains about.
  shell_update_err=$(uv tool update-shell 2>&1 >/dev/null) || shell_update_rc=$?
  shell_update_rc=${shell_update_rc:-0}

  if [ "$shell_update_rc" -ne 0 ]; then
    warn ""
    warn "uv could not update your shell PATH automatically:"
    if [ -n "$shell_update_err" ]; then
      warn "  $shell_update_err"
    fi
    warn ""
    warn "To use 'vibelens serve', add uv's tool bin to PATH. Pick one:"
    warn "  # this shell only"
    warn "  export PATH=\"$UV_BIN_DIR:\$PATH\""
    warn "  # persist for zsh (reopen your terminal after)"
    warn "  echo 'export PATH=\"$UV_BIN_DIR:\$PATH\"' >> ~/.zshrc"
    warn "  # persist for bash (reopen your terminal after)"
    warn "  echo 'export PATH=\"$UV_BIN_DIR:\$PATH\"' >> ~/.bashrc"
    warn ""
    warn "Or skip the shim and always launch with: uvx vibelens serve"
  else
    info ""
    info "Added $UV_BIN_DIR to your shell PATH (takes effect in NEW terminals)."
  fi
}

# Step 1: prefer uv.
INSTALLED_VIA=""
info "[1/3] Looking for uv..."
if command -v uv >/dev/null 2>&1; then
  info "      uv found."
  info ""
  info "[2/3] Installing VibeLens via uv..."
  install_with_uv
  INSTALLED_VIA="uv"
else
  info "      uv not found."
  # Step 2: fall back to Python.
  info ""
  info "[2/3] Looking for Python >= ${MIN_PY_MAJOR}.${MIN_PY_MINOR}..."
  if PY=$(find_python); then
    info "      Python found."
    info ""
    install_with_pip "$PY"
    INSTALLED_VIA="pip"
  else
    warn "      No suitable Python on PATH either."
    warn ""
    warn "VibeLens needs one of:"
    warn "  - uv (preferred)"
    warn "  - Python >= ${MIN_PY_MAJOR}.${MIN_PY_MINOR}"
    print_uv_install_help
    print_python_install_help
    exit 1
  fi
fi

# Step 3: launch.
# On the uv path, the `vibelens` shim exists on disk, but the user's rc edit
# (from `uv tool update-shell`) only takes effect in NEW shells. Prepend the
# bin dir to PATH for this process so `exec vibelens serve` resolves here too.
if [ "$INSTALLED_VIA" = "uv" ] && [ -n "${UV_BIN_DIR:-}" ]; then
  case ":$PATH:" in
    *":$UV_BIN_DIR:"*) : ;;
    *) PATH="$UV_BIN_DIR:$PATH" ;;
  esac
  export PATH
fi

info ""
info "[3/3] VibeLens installed."

if ! command -v vibelens >/dev/null 2>&1; then
  warn "But the 'vibelens' command is not on PATH in this shell."
  if [ "$INSTALLED_VIA" = "uv" ]; then
    warn "Expected location: ${UV_BIN_DIR:-\$HOME/.local/bin}/vibelens"
    warn "Open a new terminal and try:  vibelens serve"
    warn "Or as a one-off fallback:     uvx vibelens serve"
  else
    warn "pip installed it to a user-local bin directory that isn't on PATH"
    warn "(e.g. ~/.local/bin on Linux, or the Python framework bin on macOS)."
    warn ""
    warn "Open a new terminal and try:  vibelens serve"
    warn "If that still fails, find the install location with:"
    warn "  python3 -m site --user-base"
    warn "and add its 'bin' subdirectory to PATH."
  fi
  exit 1
fi

info "      To start it any time later, run:  vibelens serve"
info "      Starting it now..."
info ""
exec vibelens serve
