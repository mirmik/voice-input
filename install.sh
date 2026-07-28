#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== STT Voice Input — Installation ==="
echo ""

# --- System dependencies ---
echo "[1/7] Installing system packages..."
sudo apt install -y \
    python3-gi \
    gir1.2-ayatanaappindicator3-0.1 \
    xdotool \
    wl-clipboard \
    ydotool \
    ydotoold

# --- Python dependencies ---
echo "[2/7] Installing Python packages..."
PYTHON_BIN="$(python3 -c 'import sys; print(sys.executable)')"
"$PYTHON_BIN" -m pip install -r "$SCRIPT_DIR/requirements.txt"
"$PYTHON_BIN" -m pip install faster-whisper evdev flask

# --- Add user to input group (for evdev without sudo) ---
echo "[3/7] Adding user to 'input' group..."
if groups | grep -q input; then
    echo "  Already in 'input' group."
else
    sudo usermod -aG input "$USER"
    echo "  Added. You may need to re-login for this to take effect."
fi

# --- Configure the Wayland input daemon ---
echo "[4/7] Configuring ydotoold user service..."
mkdir -p "$HOME/.config/systemd/user"
cp "$SCRIPT_DIR/systemd/ydotoold.service" \
    "$HOME/.config/systemd/user/ydotoold.service"
systemctl --user daemon-reload
systemctl --user enable --now ydotoold.service

# --- Create user config ---
echo "[5/7] Creating user config..."
CONFIG_DIR="$HOME/.config/voice-input"
if [ ! -f "$CONFIG_DIR/config.json" ]; then
    mkdir -p "$CONFIG_DIR"
    cat > "$CONFIG_DIR/config.json" << CONF
{
    "KEYBOARD_DEVICE": "/dev/input/event7",
    "KEY_CODE": 100,
    "PYTHON": "${PYTHON_BIN}"
}
CONF
    echo "  Created $CONFIG_DIR/config.json — edit to match your setup."
else
    echo "  Config already exists, skipping."
fi

# --- Install desktop autostart entry ---
echo "[6/7] Installing desktop autostart entry..."
mkdir -p ~/.config/autostart
cat > ~/.config/autostart/stt-tray.desktop << EOF
[Desktop Entry]
Type=Application
Name=STT Tray
Comment=Speech-to-text tray indicator
Exec=${PYTHON_BIN} ${SCRIPT_DIR}/stt_tray.py
Icon=audio-input-microphone
X-GNOME-Autostart-enabled=true
EOF
echo "  Autostart entry created."

# --- Download Whisper model ---
echo "[7/7] Pre-downloading Whisper large-v3 model..."
python3 -c "from faster_whisper import WhisperModel; WhisperModel('large-v3', device='cpu', compute_type='int8')" 2>/dev/null && echo "  Model cached." || echo "  Model will download on first run."

echo ""
echo "=== Installation complete ==="
echo ""
echo "To start manually:  ${PYTHON_BIN} ${SCRIPT_DIR}/stt_tray.py"
echo "Or re-login for autostart."
echo ""
echo "Usage: click tray icon → Start STT → hold Right Alt to record."
echo "On Wayland, make sure ydotoold is running and re-login after group changes."
