#!/usr/bin/env python3
"""Compatibility wrapper for the X11 voice-input client."""

import sys

from voice_input.__main__ import main


if __name__ == "__main__":
    sys.exit(main(["client", "--platform", "x11", *sys.argv[1:]]))
