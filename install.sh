#!/usr/bin/env sh
set -eu

REPO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$REPO_DIR"

MIN_VERSION="3.9"

find_python() {
  if [ -n "${PYTHON_BIN:-}" ] && command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    printf '%s\n' "$PYTHON_BIN"
    return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    printf '%s\n' "python3"
    return 0
  fi
  if command -v python >/dev/null 2>&1; then
    printf '%s\n' "python"
    return 0
  fi
  return 1
}

print_python_help() {
  cat <<'EOF'
Python 3.9+ was not found.

Install Python first, then re-run ./install.sh.

Common options:
- macOS with Homebrew: brew install python
- Ubuntu/Debian: sudo apt update && sudo apt install python3 python3-venv python3-pip
- Fedora: sudo dnf install python3 python3-pip
- Arch: sudo pacman -S python python-pip
- Otherwise install Python 3.10+ from https://www.python.org/downloads/
EOF
}

PYTHON=$(find_python || true)
if [ -z "$PYTHON" ]; then
  print_python_help
  exit 1
fi

if ! "$PYTHON" - "$MIN_VERSION" <<'PY'
import sys
minimum = tuple(map(int, sys.argv[1].split(".")))
current = sys.version_info[:2]
raise SystemExit(0 if current >= minimum else 1)
PY
then
  echo "Found $($PYTHON --version 2>&1), but Python $MIN_VERSION+ is required."
  print_python_help
  exit 1
fi

if ! "$PYTHON" -m pip --version >/dev/null 2>&1; then
  echo "pip was not available. Trying ensurepip..."
  if ! "$PYTHON" -m ensurepip --upgrade >/dev/null 2>&1; then
    cat <<'EOF'
pip is not available for this Python installation.

Install pip/venv support, then re-run ./install.sh.
On Ubuntu/Debian this is usually:
  sudo apt update && sudo apt install python3-venv python3-pip
EOF
    exit 1
  fi
fi

if [ ! -d ".venv" ]; then
  echo "Creating .venv..."
  if ! "$PYTHON" -m venv .venv; then
    cat <<'EOF'
Could not create a Python virtual environment.

Install venv support, then re-run ./install.sh.
On Ubuntu/Debian this is usually:
  sudo apt update && sudo apt install python3-venv
EOF
    exit 1
  fi
fi

VENV_PYTHON=".venv/bin/python"
if [ ! -x "$VENV_PYTHON" ]; then
  echo "Virtual environment Python was not found at $VENV_PYTHON"
  exit 1
fi

echo "Installing video-to-notes into .venv..."
"$VENV_PYTHON" -m pip install --upgrade pip setuptools wheel
"$VENV_PYTHON" -m pip install -e .

cat <<EOF

Installed.

Use this environment in the current shell:
  . .venv/bin/activate

Then configure language, Whisper fallback model, and output target:
  video-to-notes configure

Or run it directly:
  .venv/bin/video-to-notes configure
EOF

if [ "${VIDEO_TO_NOTES_SKIP_CONFIGURE:-${YTLT_SKIP_CONFIGURE:-0}}" != "1" ]; then
  if [ -t 0 ] && [ -t 1 ]; then
    printf '\nRun video-to-notes configure now? [Y/n] '
    IFS= read -r answer
    case "$answer" in
      n|N|no|NO|No) exit 0 ;;
      *) .venv/bin/video-to-notes configure ;;
    esac
  fi
fi
