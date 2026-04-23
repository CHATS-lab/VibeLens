# VibeLens installer for Windows (PowerShell 5.1+ / PowerShell 7+).
#
# What it does:
#   1. Looks for `uv` on PATH. If found, asks to install VibeLens with
#      `uv tool install vibelens`.
#   2. Otherwise, looks for Python 3.10+. If found, asks to install VibeLens
#      with `pip install vibelens`.
#   3. If neither is available, prints install guidance for uv (preferred)
#      and Python, then exits.
#
# After install, the user can start VibeLens any time with:
#   vibelens serve
#
# On the uv path we also run `uv tool update-shell`, which adds uv's tool bin
# directory (e.g. %USERPROFILE%\.local\bin) to the user's PATH so `vibelens`
# is available in future PowerShell / cmd sessions.
#
# Safety:
#   - Never installs dependencies (Python, uv) for you.
#   - Always asks for confirmation before running pip/uv.
#   - Idempotent: re-running with VibeLens already installed re-installs
#     the latest version (with your consent) and starts the app.
#
# Usage:
#   irm https://raw.githubusercontent.com/CHATS-lab/VibeLens/main/install.ps1 | iex

$ErrorActionPreference = 'Stop'

$MinPyMajor = 3
$MinPyMinor = 10

$InstallDocUrl = 'https://github.com/CHATS-lab/VibeLens/blob/main/docs/INSTALL.md'
$PythonDocUrl  = 'https://www.python.org/downloads/windows/'
$UvDocUrl      = 'https://docs.astral.sh/uv/getting-started/installation/'

function Write-Info([string]$Message) {
  Write-Host $Message
}

function Write-Warn([string]$Message) {
  Write-Host $Message -ForegroundColor Yellow
}

function Invoke-Fail([string]$Message) {
  Write-Host "VibeLens install failed: $Message" -ForegroundColor Red
  Write-Host "For manual install steps, see: $InstallDocUrl" -ForegroundColor Red
  exit 1
}

function Confirm-Prompt([string]$Prompt) {
  $answer = Read-Host "$Prompt [y/N]"
  return ($answer -match '^(y|Y|yes|YES|Yes)$')
}

# Returns the first python executable on PATH whose version is >= 3.10,
# or $null if none qualify.
function Find-Python {
  $candidates = @('python3.13', 'python3.12', 'python3.11', 'python3.10', 'python3', 'python')
  foreach ($c in $candidates) {
    $cmd = Get-Command $c -ErrorAction SilentlyContinue
    if (-not $cmd) { continue }
    try {
      $versionLine = & $cmd.Source -c 'import sys; print(sys.version_info[0], sys.version_info[1])' 2>$null
    } catch {
      continue
    }
    if (-not $versionLine) { continue }
    $parts = $versionLine -split '\s+'
    if ($parts.Length -lt 2) { continue }
    $major = [int]$parts[0]
    $minor = [int]$parts[1]
    if ($major -gt $MinPyMajor -or ($major -eq $MinPyMajor -and $minor -ge $MinPyMinor)) {
      return $cmd.Source
    }
  }
  return $null
}

function Write-PythonInstallHelp {
  Write-Warn ''
  Write-Warn "Or install or upgrade Python to $MinPyMajor.$MinPyMinor+, then re-run this script:"
  Write-Warn '  winget:         winget install --id Python.Python.3.12 -e'
  Write-Warn '  Chocolatey:     choco install python'
  Write-Warn '  Official build: ' + $PythonDocUrl
  Write-Warn 'Tip: during install, check "Add Python to PATH".'
}

function Write-UvInstallHelp {
  Write-Warn ''
  Write-Warn 'Install uv (a single binary, no Python required):'
  Write-Warn '  PowerShell: irm https://astral.sh/uv/install.ps1 | iex'
  Write-Warn '  winget:     winget install --id=astral-sh.uv -e'
  Write-Warn '  scoop:      scoop install uv'
  Write-Warn "  Docs:       $UvDocUrl"
}

function Install-WithPip([string]$PythonExe) {
  $version = & $PythonExe --version 2>&1
  Write-Info "Found Python at $PythonExe ($version)."
  Write-Info ''
  Write-Info 'VibeLens will be installed with:'
  Write-Info "  $PythonExe -m pip install --upgrade vibelens"
  Write-Info ''
  if (-not (Confirm-Prompt 'Proceed?')) {
    Invoke-Fail 'Install cancelled by user.'
  }
  & $PythonExe -m pip install --upgrade vibelens
  if ($LASTEXITCODE -ne 0) {
    Write-Warn ''
    Write-Warn 'pip install failed. Workarounds:'
    Write-Warn "  1. Retry with --user:  $PythonExe -m pip install --user --upgrade vibelens"
    Write-Warn "  2. Use a virtualenv:   $PythonExe -m venv `$HOME\.vibelens; & `$HOME\.vibelens\Scripts\pip install vibelens"
    Write-Warn '  3. Install uv and re-run this script.'
    Invoke-Fail 'pip could not install VibeLens.'
  }
}

function Install-WithUv {
  $uvPath = (Get-Command uv).Source
  Write-Info "Found uv at $uvPath."
  Write-Info ''
  Write-Info 'VibeLens will be installed with:'
  Write-Info '  uv tool install vibelens'
  Write-Info ''
  if (-not (Confirm-Prompt 'Proceed?')) {
    Invoke-Fail 'Install cancelled by user.'
  }
  & uv tool install vibelens
  if ($LASTEXITCODE -ne 0) {
    Invoke-Fail 'uv could not install VibeLens.'
  }

  # Look up the real bin directory so any diagnostics we print match this
  # machine, instead of guessing %USERPROFILE%\.local\bin.
  $uvBinDir = $null
  try {
    $uvBinDir = (& uv tool dir --bin 2>$null | Select-Object -First 1).Trim()
  } catch { }
  if (-not $uvBinDir) {
    $uvBinDir = Join-Path $HOME '.local\bin'
  }

  # Ask uv to edit the user's PATH so the plain `vibelens` command works in
  # future shells. Capture stderr so we can surface the real error if it fails.
  $shellUpdateOut = & uv tool update-shell 2>&1
  if ($LASTEXITCODE -ne 0) {
    Write-Warn ''
    Write-Warn 'uv could not update your PATH automatically:'
    if ($shellUpdateOut) {
      Write-Warn "  $shellUpdateOut"
    }
    Write-Warn ''
    Write-Warn "To use 'vibelens serve', add uv's tool bin to PATH. Pick one:"
    Write-Warn "  `$env:Path = `"$uvBinDir;`$env:Path`"                                    # this session only"
    Write-Warn "  setx PATH `"$uvBinDir;%PATH%`"                                           # persist (new shells)"
    Write-Warn ''
    Write-Warn 'Or skip the shim and always launch with: uvx vibelens serve'
  } else {
    Write-Info ''
    Write-Info "Added $uvBinDir to your PATH (takes effect in NEW PowerShell / cmd sessions)."
  }
}

# Step 1: prefer uv.
$InstalledVia = ''
Write-Info '[1/3] Looking for uv...'
if (Get-Command uv -ErrorAction SilentlyContinue) {
  Write-Info '      uv found.'
  Write-Info ''
  Write-Info '[2/3] Installing VibeLens via uv...'
  Install-WithUv
  $InstalledVia = 'uv'
} else {
  Write-Info '      uv not found.'
  Write-Info ''
  Write-Info "[2/3] Looking for Python >= $MinPyMajor.$MinPyMinor..."
  $python = Find-Python
  if ($python) {
    Write-Info '      Python found.'
    Write-Info ''
    Install-WithPip -PythonExe $python
    $InstalledVia = 'pip'
  } else {
    Write-Warn '      No suitable Python on PATH either.'
    Write-Warn ''
    Write-Warn 'VibeLens needs one of:'
    Write-Warn '  - uv (preferred)'
    Write-Warn "  - Python >= $MinPyMajor.$MinPyMinor"
    Write-UvInstallHelp
    Write-PythonInstallHelp
    exit 1
  }
}

# Step 3: launch.
Write-Info ''
Write-Info '[3/3] VibeLens installed.'
Write-Info '      To start it any time later, run:  vibelens serve'

# The `vibelens` shim may not be on PATH in *this* session yet if uv just
# registered its tool bin via update-shell (Windows only picks up PATH changes
# in NEW shells). Fall back to `uvx` for this one launch when that happens.
if (Get-Command vibelens -ErrorAction SilentlyContinue) {
  Write-Info '      Starting it now...'
  Write-Info ''
  & vibelens serve
  exit $LASTEXITCODE
} elseif ($InstalledVia -eq 'uv' -and (Get-Command uv -ErrorAction SilentlyContinue)) {
  Write-Info "      (PATH will pick up 'vibelens' in new shells. Launching via uvx for this run.)"
  Write-Info '      Starting it now...'
  Write-Info ''
  & uvx vibelens serve
  exit $LASTEXITCODE
} else {
  Write-Warn ''
  Write-Warn "VibeLens installed, but the 'vibelens' command is not on PATH in this session."
  Write-Warn 'This usually means pip installed it to a user-local Scripts directory that'
  Write-Warn "isn't on PATH (e.g. %APPDATA%\Python\PythonXY\Scripts)."
  Write-Warn ''
  Write-Warn 'Open a new PowerShell window and try:  vibelens serve'
  Write-Warn 'If that still fails, find the install location with:'
  Write-Warn '  python -m site --user-base'
  Write-Warn "and add its 'Scripts' subdirectory to PATH."
  exit 1
}
