"""
STT server configuration (desktop settings live in voice_input/settings.py).

Defaults are defined here. Override any value in:
    ~/.config/voice-input/config.json

Example config.json:
{
    "MODEL_SIZE": "large-v3",
    "LANGUAGE": "ru",
    "SAMPLE_RATE": 16000,
    "STT_PORT": 5055
}
"""

import json
import os

# --- Defaults ---
MODEL_SIZE = "large-v2"
LANGUAGE = "ru"
SAMPLE_RATE = 16000
STT_PORT = 5055
STT_TOKEN = None

# --- Load user overrides ---
_config_path = os.path.expanduser("~/.config/voice-input/config.json")
_overrides = {}
if os.path.exists(_config_path):
    with open(_config_path) as _f:
        _overrides = json.load(_f)
    for _k, _v in _overrides.items():
        if _k in {"MODEL_SIZE", "LANGUAGE", "SAMPLE_RATE", "STT_PORT", "STT_TOKEN"}:
            globals()[_k] = _v
