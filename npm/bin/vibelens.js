#!/usr/bin/env node

"use strict";

const { execFileSync, spawnSync } = require("child_process");

const MIN_PYTHON_MAJOR = 3;
const MIN_PYTHON_MINOR = 10;

/**
 * Try a list of Python executable candidates and return the first one
 * that exists and meets the minimum version requirement.
 * Checks VIBELENS_PYTHON env var first.
 */
function findPython() {
  const envPython = process.env.VIBELENS_PYTHON;
  if (envPython) {
    if (checkPythonVersion(envPython)) return envPython;
    console.error(
      `VIBELENS_PYTHON is set to "${envPython}" but it does not meet the minimum version (${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}+).`
    );
    process.exit(1);
  }

  const candidates =
    process.platform === "win32"
      ? ["python3", "python", "py"]
      : ["python3", "python"];

  for (const cmd of candidates) {
    if (checkPythonVersion(cmd) && isVibelensInstalled(cmd)) return cmd;
  }
  for (const cmd of candidates) {
    if (checkPythonVersion(cmd)) return cmd;
  }
  return null;
}

/**
 * Check if a Python executable exists and meets minimum version.
 * On Windows, "py" requires "-3" flag to select Python 3.
 */
function checkPythonVersion(cmd) {
  try {
    const args = cmd === "py" ? ["-3", "--version"] : ["--version"];
    const out = execFileSync(cmd, args, {
      encoding: "utf8",
      stdio: ["pipe", "pipe", "pipe"],
    });
    const match = out.trim().match(/Python (\d+)\.(\d+)/);
    if (!match) return false;
    const major = parseInt(match[1], 10);
    const minor = parseInt(match[2], 10);
    return (
      major > MIN_PYTHON_MAJOR ||
      (major === MIN_PYTHON_MAJOR && minor >= MIN_PYTHON_MINOR)
    );
  } catch {
    return false;
  }
}

/**
 * Check if the vibelens Python package is installed by running
 * `python -m vibelens version`.
 */
function isVibelensInstalled(pythonCmd) {
  try {
    const args =
      pythonCmd === "py"
        ? ["-3", "-m", "vibelens", "version"]
        : ["-m", "vibelens", "version"];
    execFileSync(pythonCmd, args, {
      encoding: "utf8",
      stdio: ["pipe", "pipe", "pipe"],
    });
    return true;
  } catch {
    return false;
  }
}

function printNoPythonError() {
  console.error("Error: vibelens requires Python >= 3.10.\n");
  console.error(
    "Fastest fix (skips Python/pip entirely): install uv and let it handle Python for you.\n"
  );
  if (process.platform === "win32") {
    console.error(
      '  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"'
    );
    console.error("  uvx vibelens serve\n");
  } else {
    console.error("  curl -LsSf https://astral.sh/uv/install.sh | sh");
    console.error("  uvx vibelens serve\n");
  }
  console.error("Or install Python yourself:");
  if (process.platform === "darwin") {
    console.error("  brew install python@3.12");
  } else if (process.platform === "win32") {
    console.error("  winget install Python.Python.3.12");
  } else {
    console.error("  sudo apt install python3  # Debian/Ubuntu");
    console.error("  sudo dnf install python3  # Fedora");
  }
  console.error("  (or download from https://www.python.org/downloads/)\n");
  console.error(
    "Full install guide: https://github.com/CHATS-lab/VibeLens/blob/main/docs/INSTALL.md"
  );
  console.error(
    "If Python is installed at a non-standard path, set VIBELENS_PYTHON=/path/to/python3"
  );
}

function printNotInstalledError() {
  console.error(
    "Python found but vibelens is not installed. Install it with one of:\n"
  );
  console.error("  pip install vibelens");
  console.error(
    "  pipx install vibelens      # if pip reports 'externally-managed-environment'"
  );
  console.error(
    "  uvx vibelens serve         # if you don't want to manage Python at all"
  );
  console.error("\nThen run this command again.");
  console.error(
    "Full install guide: https://github.com/CHATS-lab/VibeLens/blob/main/docs/INSTALL.md"
  );
}

// --- Main ---

const python = findPython();
if (!python) {
  printNoPythonError();
  process.exit(1);
}

if (!isVibelensInstalled(python)) {
  printNotInstalledError();
  process.exit(1);
}

const pyArgs =
  python === "py"
    ? ["-3", "-m", "vibelens", ...process.argv.slice(2)]
    : ["-m", "vibelens", ...process.argv.slice(2)];

const result = spawnSync(python, pyArgs, { stdio: "inherit" });
process.exit(result.status ?? 1);
