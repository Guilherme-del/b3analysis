#!/usr/bin/env bash
set -e
WORKSPACE="$(cd "$(dirname "$0")" && pwd)"
VENV="$WORKSPACE/.venv"

# venv layout differs between platforms: bin/ on POSIX, Scripts/ on Windows.
if [ -x "$VENV/bin/python" ]; then
    PYTHON="$VENV/bin/python"
elif [ -x "$VENV/Scripts/python.exe" ]; then
    PYTHON="$VENV/Scripts/python.exe"
else
    echo "[B3Analysis] First run: setting up Python environment..." >&2
    python3 -m venv "$VENV"
    if [ -x "$VENV/bin/pip" ]; then
        PIP="$VENV/bin/pip"
        PYTHON="$VENV/bin/python"
    else
        PIP="$VENV/Scripts/pip.exe"
        PYTHON="$VENV/Scripts/python.exe"
    fi
    "$PIP" install -q -r "$WORKSPACE/requirements.txt"
    echo "[B3Analysis] Done." >&2
fi

exec "$PYTHON" "$@"
