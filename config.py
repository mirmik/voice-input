"""
STT Voice Input — configuration.

Defaults are defined here. Override any value in:
    ~/.config/voice-input/config.json

Example config.json:
{
    "KEYBOARD_DEVICE": "/dev/input/event7",
    "KEY_CODE": 100,
    "MODEL_SIZE": "large-v3",
    "LANGUAGE": "ru",
    "SAMPLE_RATE": 16000,
    "STT_SERVER": "http://localhost:5055",
    "STT_PORT": 5055,
    "STT_TOKEN": "your-secret-token-here",
    "PYTHON": "python3"
}
"""

import json
import os

# --- Defaults ---
KEYBOARD_DEVICE = "/dev/input/event7"
KEY_CODE = 100  # KEY_RIGHTALT
MODEL_SIZE = "large-v3"
LANGUAGE = "ru"
SAMPLE_RATE = 16000
STT_SERVER = "http://localhost:5055"
STT_PORT = 5055
STT_TOKEN = None
PYTHON = "python3"

# --- Load user overrides ---
_config_path = os.path.expanduser("~/.config/voice-input/config.json")
if os.path.exists(_config_path):
    with open(_config_path) as _f:
        _overrides = json.load(_f)
    for _k, _v in _overrides.items():
        if _k in globals():
            globals()[_k] = _v
