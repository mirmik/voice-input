#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${ENV_FILE:-$HOME/.config/voice-input/stt_server.env}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
fi

if [ ! -x "$PYTHON_BIN" ]; then
    echo "Python executable not found: $PYTHON_BIN" >&2
    echo "Set PYTHON_BIN in $ENV_FILE before starting the service." >&2
    exit 1
fi

cd "$SCRIPT_DIR"
exec "$PYTHON_BIN" "$SCRIPT_DIR/stt_server.py"
