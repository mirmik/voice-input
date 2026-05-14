"""Platform selection helpers."""

import sys


def platform_name():
    if sys.platform.startswith("win"):
        return "win"
    if sys.platform.startswith("linux"):
        return "x11"
    raise RuntimeError(f"Unsupported platform: {sys.platform}")


def load_platform(name=None):
    selected = name or platform_name()
    if selected == "win":
        from voice_input import platform_win

        return platform_win
    if selected == "x11":
        from voice_input import platform_x11

        return platform_x11
    raise RuntimeError(f"Unsupported voice-input platform: {selected}")
