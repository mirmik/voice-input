"""Shared voice-input configuration helpers."""

import json
import os


TOOL_CONFIG_PATH = os.path.expanduser("~/.config/voice-input/config.json")


def load_tool_config():
    if not os.path.isfile(TOOL_CONFIG_PATH):
        return {}
    try:
        with open(TOOL_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}


def configured_python():
    cfg = load_tool_config()
    return cfg.get("PYTHON") or ("python" if os.name == "nt" else "python3")
