#!/usr/bin/env python3
"""
STT client: push-to-talk via evdev, sends audio to STT server, types result.
Works on Linux with evdev. For Windows client, see stt_client_win.py.

Requires: pip install evdev sounddevice numpy requests
Requires: sudo apt install xdotool
"""

import argparse
import json
import os
import subprocess
import sys

import evdev
from evdev import ecodes
import numpy as np
import sounddevice as sd
import requests

from config import KEYBOARD_DEVICE, KEY_CODE, SAMPLE_RATE, STT_SERVER, LLM_PROXY_AUTH_FILE

# CLI overrides
_parser = argparse.ArgumentParser(add_help=False)
_parser.add_argument("--host", type=str, default=None)
_parser.add_argument("--port", type=int, default=None)
_parser.add_argument("--auth-file", type=str, default=None)
_args, _ = _parser.parse_known_args()


def load_proxy_auth():
    auth_path = os.path.expanduser(_args.auth_file or LLM_PROXY_AUTH_FILE)
    if not os.path.exists(auth_path):
        return {}
    with open(auth_path, encoding="utf-8") as f:
        return json.load(f)


_auth = load_proxy_auth()
_server = _auth.get("server")
_host_id = _auth.get("host_id")
_token = _auth.get("token")

if _server:
    STT_SERVER = _server.rstrip("/")

if _args.host or _args.port:
    from urllib.parse import urlparse
    _parsed = urlparse(STT_SERVER)
    _host = _args.host or _parsed.hostname
    _port = _args.port or _parsed.port or 5079
    STT_SERVER = f"{_parsed.scheme}://{_host}:{_port}"


def auth_headers():
    headers = {}
    if _token:
        headers["Authorization"] = f"Bearer {_token}"
    if _host_id:
        headers["X-LLM-Proxy-Host-ID"] = _host_id
    return headers


def type_text(text):
    subprocess.run(
        ["xdotool", "type", "--clearmodifiers", "--delay", "0", "--", text],
        check=True,
    )


def transcribe(audio):
    """Send audio to STT server and return text."""
    headers = {"Content-Type": "application/octet-stream", **auth_headers()}
    resp = requests.post(
        f"{STT_SERVER}/stt",
        data=audio.tobytes(),
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("text", "")


def wait_for_server(max_wait=60):
    """Wait for STT server to become available."""
    import time
    print(f"Waiting for server at {STT_SERVER}...", end="", flush=True)
    for i in range(max_wait):
        for health_url in (f"{STT_SERVER}/stt/health", f"{STT_SERVER}/health"):
            try:
                r = requests.get(health_url, headers=auth_headers(), timeout=2)
                if r.status_code != 200:
                    continue
                info = r.json()
                print(f" OK (model: {info.get('model', '?')})")
                return True
            except Exception:
                pass
        print(".", end="", flush=True)
        time.sleep(1)
    print(" TIMEOUT")
    return False


def main():
    if not wait_for_server():
        print(f"Cannot reach STT server at {STT_SERVER}")
        sys.exit(1)

    kbd = evdev.InputDevice(KEYBOARD_DEVICE)
    print(f"Keyboard: {kbd.name} ({kbd.path})")
    print(f"Push-to-talk active. Ctrl+C to exit.\n")

    recording = False
    chunks = []
    stream = None

    def audio_callback(indata, frames, time, status):
        chunks.append(indata.copy())

    try:
        for event in kbd.read_loop():
            if event.type != ecodes.EV_KEY or event.code != KEY_CODE:
                continue

            key_event = evdev.categorize(event)

            if key_event.keystate == evdev.KeyEvent.key_down and not recording:
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

            elif key_event.keystate == evdev.KeyEvent.key_up and recording:
                recording = False
                stream.stop()
                stream.close()
                print(" done.")

                if not chunks:
                    print("  (empty)")
                    continue

                audio = np.concatenate(chunks).squeeze()
                duration = len(audio) / SAMPLE_RATE
                if duration < 0.3:
                    print("  (too short)")
                    continue

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

    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        print("Done.")


if __name__ == "__main__":
    main()
