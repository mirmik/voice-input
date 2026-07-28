"""Platform selection helpers."""

import os
import sys


def platform_name():
    if sys.platform.startswith("win"):
        return "win"
    if sys.platform.startswith("linux"):
        if (
            os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"
            or os.environ.get("WAYLAND_DISPLAY")
        ):
            return "wayland"
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
    if selected == "wayland":
        from voice_input import platform_wayland

        return platform_wayland
    raise RuntimeError(f"Unsupported voice-input platform: {selected}")
