#!/usr/bin/env python3
"""Compatibility wrapper for the Wayland voice-input client."""

import sys

from voice_input.__main__ import main


if __name__ == "__main__":
    sys.exit(main(["client", "--platform", "wayland", *sys.argv[1:]]))
