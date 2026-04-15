#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
VOICE_CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/voice-input"
UNIT_NAME="stt-server-rocm.service"
UNIT_PATH="$UNIT_DIR/$UNIT_NAME"
LAUNCHER_PATH="$SCRIPT_DIR/run_stt_server_rocm.sh"
ENV_FILE="$VOICE_CONFIG_DIR/stt_server_rocm.env"

mkdir -p "$UNIT_DIR"
mkdir -p "$VOICE_CONFIG_DIR"

cat > "$UNIT_PATH" <<EOF
[Unit]
Description=Voice Input STT ROCm Server
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
    cat > "$ENV_FILE" <<'EOF'
# Optional overrides for the ROCm STT server.
# Examples:
# HF_TOKEN=hf_xxx
# STT_MODEL_ID=openai/whisper-large-v3
# VENV_DIR=/home/USER/project/voice-input/.venv
# PYTHON_BIN=/home/USER/project/voice-input/.venv/bin/python
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
