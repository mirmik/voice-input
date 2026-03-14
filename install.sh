#!/bin/bash
set -e

echo "=== STT Voice Input — Installation ==="
echo ""

# --- System dependencies ---
echo "[1/5] Installing system packages..."
sudo apt install -y python3-gi gir1.2-ayatanaappindicator3-0.1 xdotool

# --- Python dependencies ---
echo "[2/5] Installing Python packages..."
pip install faster-whisper evdev sounddevice numpy

# --- Add user to input group (for evdev without sudo) ---
echo "[3/5] Adding user to 'input' group..."
if groups | grep -q input; then
    echo "  Already in 'input' group."
else
    sudo usermod -aG input "$USER"
    echo "  Added. You may need to re-login for this to take effect."
fi

# --- Install XFCE autostart entry ---
echo "[4/5] Installing XFCE autostart entry..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p ~/.config/autostart
cat > ~/.config/autostart/stt-tray.desktop << EOF
[Desktop Entry]
Type=Application
Name=STT Tray
Comment=Speech-to-text tray indicator
Exec=/usr/bin/python3 ${SCRIPT_DIR}/stt_tray.py
Icon=audio-input-microphone
X-GNOME-Autostart-enabled=true
EOF
echo "  Autostart entry created."

# --- Download Whisper model ---
echo "[5/5] Pre-downloading Whisper large-v3 model..."
python3 -c "from faster_whisper import WhisperModel; WhisperModel('large-v3', device='cpu', compute_type='int8')" 2>/dev/null && echo "  Model cached." || echo "  Model will download on first run."

echo ""
echo "=== Installation complete ==="
echo ""
echo "To start manually:  /usr/bin/python3 ${SCRIPT_DIR}/stt_tray.py"
echo "Or re-login for autostart."
echo ""
echo "Usage: click tray icon → Start STT → hold Right Alt to record."
