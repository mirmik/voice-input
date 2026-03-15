#!/usr/bin/env python3
"""
STT client: push-to-talk via evdev, sends audio to STT server, types result.
Works on Linux with evdev. For Windows client, see stt_client_win.py.

Requires: pip install evdev sounddevice numpy requests
Requires: sudo apt install xdotool
"""

import subprocess
import sys

import evdev
from evdev import ecodes
import numpy as np
import requests
import sounddevice as sd

from config import KEYBOARD_DEVICE, KEY_CODE, SAMPLE_RATE, STT_SERVER, STT_TOKEN


def type_text(text):
    subprocess.run(
        ["xdotool", "type", "--clearmodifiers", "--delay", "0", "--", text],
        check=True,
    )


def transcribe(audio):
    """Send audio to STT server and return text."""
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


def main():
    # Check server
    try:
        r = requests.get(f"{STT_SERVER}/health", timeout=5)
        info = r.json()
        print(f"Server OK: {STT_SERVER} (model: {info.get('model', '?')})")
    except Exception as e:
        print(f"Cannot reach STT server at {STT_SERVER}: {e}")
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
