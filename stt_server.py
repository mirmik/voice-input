#!/usr/bin/env python3
"""Compatibility entrypoint; implementation lives in servers/."""

import runpy

if __name__ == "__main__":
    runpy.run_module("servers.stt_server", run_name="__main__")
