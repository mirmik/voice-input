"""
STT Voice Input — configuration.
Edit this file to match your setup.
"""

# Evdev input device for keyboard.
# Find yours:
#   python3 -c "import evdev; [print(f'{d.path}: {d.name}') for d in [evdev.InputDevice(p) for p in evdev.list_devices()]]"
KEYBOARD_DEVICE = "/dev/input/event7"

# Key code for push-to-talk (evdev key code number).
# 100 = KEY_RIGHTALT (default)
# 97  = KEY_RIGHTCTRL
# 70  = KEY_SCROLLLOCK
# 119 = KEY_PAUSE
# Find yours:
#   python3 -c "import evdev; print({v:k for k,v in evdev.ecodes.ecodes.items() if k.startswith('KEY_')})"
KEY_CODE = 100  # KEY_RIGHTALT

# Whisper model size: tiny, base, small, medium, large-v3
MODEL_SIZE = "large-v3"

# Language for speech recognition (e.g. "ru", "en", or None for auto-detect)
LANGUAGE = "ru"

# Audio sample rate (16000 is optimal for Whisper)
SAMPLE_RATE = 16000

# STT server URL (used by client)
STT_SERVER = "http://localhost:5055"

# Shared secret for authentication (set to None to disable)
# Generate one: python3 -c "import secrets; print(secrets.token_hex(32))"
STT_TOKEN = None

# STT server port (used by server)
STT_PORT = 5055

# Python interpreter (used by stt_tray.py to launch server/client).
# If you use system Python for everything, set to "python3".
# If you use pyenv/venv, set the full path, e.g.:
#   PYTHON = "/home/user/.pyenv/versions/3.10.19/bin/python3"
PYTHON = "python3"
