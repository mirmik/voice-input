#!/bin/bash
# Desktop client installation for Debian/Ubuntu.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="${VENV_DIR:-$SCRIPT_DIR/.venv-client}"

sudo apt install -y python3-venv python3-gi python3-tk \
    gir1.2-ayatanaappindicator3-0.1 libportaudio2 \
    xdotool wl-clipboard ydotool ydotoold
python3 -m venv --system-site-packages "$VENV_DIR"
PYTHON_BIN="$VENV_DIR/bin/python"
"$PYTHON_BIN" -m pip install -r "$SCRIPT_DIR/requirements.txt"

if ! id -nG "$USER" | tr ' ' '\n' | grep -qx input; then
    sudo usermod -aG input "$USER"
    echo "Added to input group; log out and back in before using Wayland input."
fi

mkdir -p "$HOME/.config/systemd/user"
cp "$SCRIPT_DIR/systemd/ydotoold.service" "$HOME/.config/systemd/user/ydotoold.service"
systemctl --user daemon-reload
systemctl --user enable --now ydotoold.service

# Preserve existing backend settings and use the installed client interpreter.
cd "$SCRIPT_DIR"
"$PYTHON_BIN" - <<'PY'
import os
import sys
from pathlib import Path
from voice_input.settings import load_tool_config, save_tool_config

cfg = load_tool_config()
cfg['PYTHON'] = sys.executable
save_tool_config(cfg)

def desktop_quote(value):
    value = value.replace('%', '%%')
    for char in ('\\', '"', '`', '$'):
        value = value.replace(char, '\\' + char)
    return '"' + value + '"'

config_home = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
entry = config_home / 'autostart/stt-tray.desktop'
entry.parent.mkdir(parents=True, exist_ok=True)
command = ' '.join(desktop_quote(v) for v in (sys.executable, str(Path.cwd() / 'stt_tray.py')))
entry.write_text(
    '[Desktop Entry]\nType=Application\nName=STT Tray\n'
    f'Exec={command}\nIcon=audio-input-microphone\n'
    'X-GNOME-Autostart-enabled=true\n', encoding='utf-8')
PY

echo "Installation complete. Run: $PYTHON_BIN $SCRIPT_DIR/stt_tray.py"
echo "Enable 'Start Client with Tray' in the tray menu to start listening after login."
echo "On Wayland, ensure both your user and ydotoold can access /dev/uinput."
