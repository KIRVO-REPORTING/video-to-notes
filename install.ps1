$ErrorActionPreference = "Stop"

$RepoDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoDir

$MinimumVersion = [Version]"3.9"

function Get-PythonCommand {
    if ($env:PYTHON_BIN) {
        $cmd = Get-Command $env:PYTHON_BIN -ErrorAction SilentlyContinue
        if ($cmd) {
            return @{ File = $cmd.Source; Args = @() }
        }
    }

    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        return @{ File = $py.Source; Args = @("-3") }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return @{ File = $python.Source; Args = @() }
    }

    $python3 = Get-Command python3 -ErrorAction SilentlyContinue
    if ($python3) {
        return @{ File = $python3.Source; Args = @() }
    }

    return $null
}

function Invoke-BasePython {
    param([string[]]$Arguments)
    & $script:PythonCommand.File @($script:PythonCommand.Args) @Arguments
}

function Show-PythonHelp {
    Write-Host @"
Python 3.9+ was not found.

Install Python first, then re-run:
  powershell -ExecutionPolicy Bypass -File .\install.ps1

Common options:
- Install Python 3.10+ from https://www.python.org/downloads/windows/
- Or use winget: winget install Python.Python.3.12
- During installation, enable "Add python.exe to PATH" if offered.
"@
}

$script:PythonCommand = Get-PythonCommand
if (-not $script:PythonCommand) {
    Show-PythonHelp
    exit 1
}

$VersionText = Invoke-BasePython @("-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))")
$Version = [Version]$VersionText.Trim()
if ($Version -lt $MinimumVersion) {
    Write-Host "Found Python $Version, but Python $MinimumVersion+ is required."
    Show-PythonHelp
    exit 1
}

try {
    Invoke-BasePython @("-m", "pip", "--version") | Out-Null
} catch {
    Write-Host "pip was not available. Trying ensurepip..."
    try {
        Invoke-BasePython @("-m", "ensurepip", "--upgrade") | Out-Null
    } catch {
        Write-Host "pip is not available for this Python installation. Reinstall Python with pip enabled, then re-run install.ps1."
        exit 1
    }
}

if (-not (Test-Path ".venv")) {
    Write-Host "Creating .venv..."
    try {
        Invoke-BasePython @("-m", "venv", ".venv")
    } catch {
        Write-Host "Could not create a virtual environment. Reinstall Python with venv support, then re-run install.ps1."
        exit 1
    }
}

$VenvPython = Join-Path $RepoDir ".venv\Scripts\python.exe"
$VenvCommand = Join-Path $RepoDir ".venv\Scripts\video-to-notes.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Host "Virtual environment Python was not found at $VenvPython"
    exit 1
}

Write-Host "Installing video-to-notes into .venv..."
& $VenvPython -m pip install --upgrade pip setuptools wheel
& $VenvPython -m pip install -e .

Write-Host @"

Installed.

Use this environment in the current PowerShell:
  .\.venv\Scripts\Activate.ps1

Then configure language, Whisper fallback model, and output target:
  video-to-notes configure

Or run it directly:
  .\.venv\Scripts\video-to-notes.exe configure
"@

if ($env:VIDEO_TO_NOTES_SKIP_CONFIGURE -ne "1" -and $env:YTLT_SKIP_CONFIGURE -ne "1" -and [Environment]::UserInteractive) {
    $answer = Read-Host "Run video-to-notes configure now? [Y/n]"
    if ($answer -notin @("n", "N", "no", "NO", "No")) {
        & $VenvCommand configure
    }
}
