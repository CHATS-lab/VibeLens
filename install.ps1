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
}

# Step 1: prefer uv.
Write-Info '[1/3] Looking for uv...'
if (Get-Command uv -ErrorAction SilentlyContinue) {
  Write-Info '      uv found.'
  Write-Info ''
  Write-Info '[2/3] Installing VibeLens via uv...'
  Install-WithUv
} else {
  Write-Info '      uv not found.'
  Write-Info ''
  Write-Info "[2/3] Looking for Python >= $MinPyMajor.$MinPyMinor..."
  $python = Find-Python
  if ($python) {
    Write-Info '      Python found.'
    Write-Info ''
    Install-WithPip -PythonExe $python
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
Write-Info '      Starting it now...'
Write-Info ''
& vibelens serve
exit $LASTEXITCODE
