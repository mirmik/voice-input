#!/usr/bin/env python3
"""Compatibility wrapper for the cross-platform voice-input tray."""

import sys

from voice_input.__main__ import main


if __name__ == "__main__":
    sys.exit(main(["tray", *sys.argv[1:]]))
