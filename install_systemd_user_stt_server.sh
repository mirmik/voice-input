#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
VOICE_CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/voice-input"
UNIT_NAME="stt-server.service"
UNIT_PATH="$UNIT_DIR/$UNIT_NAME"
LAUNCHER_PATH="$SCRIPT_DIR/run_stt_server.sh"
ENV_FILE="$VOICE_CONFIG_DIR/stt_server.env"
USER_CONFIG_JSON="$VOICE_CONFIG_DIR/config.json"

mkdir -p "$UNIT_DIR"
mkdir -p "$VOICE_CONFIG_DIR"

DEFAULT_PYTHON_BIN="$(python3 - <<'PY'
import json
import os

cfg_path = os.path.expanduser("~/.config/voice-input/config.json")
python_bin = "python3"
if os.path.exists(cfg_path):
    try:
        with open(cfg_path, encoding="utf-8") as f:
            data = json.load(f)
        python_bin = data.get("PYTHON", python_bin)
    except Exception:
        pass
print(python_bin)
PY
)"

cat > "$UNIT_PATH" <<EOF
[Unit]
Description=Voice Input STT Server
After=default.target

[Service]
Type=simple
WorkingDirectory=$SCRIPT_DIR
ExecStart=$LAUNCHER_PATH
Restart=on-failure
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
EOF

if [ ! -f "$ENV_FILE" ]; then
    cat > "$ENV_FILE" <<EOF
# Optional overrides for the STT server.
# Example:
# PYTHON_BIN=/home/USER/.pyenv/versions/3.10.19/bin/python3
PYTHON_BIN=$DEFAULT_PYTHON_BIN
EOF
fi

systemctl --user daemon-reload
systemctl --user enable "$UNIT_NAME"

cat <<EOF
Installed user unit:
  $UNIT_PATH

Optional environment file:
  $ENV_FILE

Useful commands:
  systemctl --user start $UNIT_NAME
  systemctl --user stop $UNIT_NAME
  systemctl --user restart $UNIT_NAME
  systemctl --user status $UNIT_NAME
  journalctl --user -u $UNIT_NAME -f
EOF
