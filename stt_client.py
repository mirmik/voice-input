#!/usr/bin/env python3
"""Run the cross-platform voice-input client without the tray."""

import sys

from voice_input.__main__ import main


if __name__ == "__main__":
    sys.exit(main(["client", *sys.argv[1:]]))
