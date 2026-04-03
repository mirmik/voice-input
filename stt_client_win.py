#!/usr/bin/env python3
"""
STT client for Windows: push-to-talk, sends audio to STT server, types result.
Uses pynput for key capture, pyperclip + keyboard for text insertion.

Requires: pip install sounddevice numpy requests pynput pyperclip keyboard
"""

import argparse
import os
import sys
import numpy as np
import requests
import sounddevice as sd
from pynput import keyboard as kb

# --- Config ---
STT_SERVER = "http://192.168.0.90:5079"
STT_TOKEN = None

# Load overrides from config file
_config_candidates = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json"),
    os.path.expanduser("~/.config/voice-input/config.json"),
]
for _cfg_path in _config_candidates:
    if os.path.exists(_cfg_path):
        import json as _json
        with open(_cfg_path) as _f:
            _overrides = _json.load(_f)
        STT_SERVER = _overrides.get("STT_SERVER", STT_SERVER)
        STT_TOKEN = _overrides.get("STT_TOKEN", STT_TOKEN)
        break

# CLI overrides
_parser = argparse.ArgumentParser(add_help=False)
_parser.add_argument("--host", type=str, default=None)
_parser.add_argument("--port", type=int, default=None)
_parser.add_argument("--token", type=str, default=None)
_args, _ = _parser.parse_known_args()

if _args.host or _args.port:
    from urllib.parse import urlparse
    _parsed = urlparse(STT_SERVER)
    _host = _args.host or _parsed.hostname
    _port = _args.port or _parsed.port or 5079
    STT_SERVER = f"{_parsed.scheme}://{_host}:{_port}"
if _args.token:
    STT_TOKEN = _args.token

SAMPLE_RATE = 16000
PUSH_TO_TALK_KEY = kb.Key.alt_r  # Right Alt


recording = False
chunks = []
stream = None


def transcribe(audio):
    headers = {"Content-Type": "application/octet-stream"}
    if STT_TOKEN:
        headers["Authorization"] = f"Bearer {STT_TOKEN}"
    resp = requests.post(
        f"{STT_SERVER}/stt",
        data=audio.tobytes(),
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("text", "")


def type_text(text):
    """Type text using clipboard paste (most reliable on Windows)."""
    import pyperclip
    import keyboard as kbmod
    pyperclip.copy(text)
    kbmod.press_and_release("ctrl+v")


def audio_callback(indata, frames, time, status):
    chunks.append(indata.copy())


def on_press(key):
    global recording, chunks, stream
    if key == PUSH_TO_TALK_KEY and not recording:
        recording = True
        chunks.clear()
        stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            callback=audio_callback,
        )
        stream.start()
        print("  🎙 Recording...", end="", flush=True)


def on_release(key):
    global recording, stream
    if key == PUSH_TO_TALK_KEY and recording:
        recording = False
        stream.stop()
        stream.close()
        print(" done.")

        if not chunks:
            print("  (empty)")
            return

        audio = np.concatenate(chunks).squeeze()
        duration = len(audio) / SAMPLE_RATE
        if duration < 0.3:
            print("  (too short)")
            return

        print(f"  Sending {duration:.1f}s to server...", end="", flush=True)
        try:
            text = transcribe(audio)
            print(f" done.")
            if text:
                print(f"  >>> {text}")
                type_text(text)
            else:
                print("  (no speech detected)")
        except Exception as e:
            print(f" error: {e}")


def main():
    try:
        r = requests.get(f"{STT_SERVER}/health", timeout=5)
        info = r.json()
        print(f"Server OK: {STT_SERVER} (model: {info.get('model', '?')})")
    except Exception as e:
        print(f"Cannot reach STT server at {STT_SERVER}: {e}")
        sys.exit(1)

    print(f"Push-to-talk: Right Alt. Ctrl+C to exit.\n")

    with kb.Listener(on_press=on_press, on_release=on_release) as listener:
        listener.join()


if __name__ == "__main__":
    main()
