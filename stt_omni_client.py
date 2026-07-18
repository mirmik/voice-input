#!/usr/bin/env python3
"""
STT client for Qwen3-Omni. Like stt_client.py, but sends audio to
Qwen3-Omni's /v1/chat/completions endpoint instead of whisper.

Usage:
    python stt_omni_client.py [--host 192.168.0.61] [--port 8095] [--prompt "..."]
"""

import argparse
import base64
import subprocess
import sys

import evdev
from evdev import ecodes
import numpy as np
import requests
import sounddevice as sd

# --- defaults (override with --keyboard, --keycode, --host, --port, --prompt) ---
KEYBOARD_DEVICE = "/dev/input/event7"
KEY_CODE = 100  # KEY_RIGHTALT
SAMPLE_RATE = 16000
OMNI_HOST = "192.168.0.61"
OMNI_PORT = 8098
OMNI_TOKEN = None
PROMPT = "Ответь."

_parser = argparse.ArgumentParser(add_help=False)
_parser.add_argument("--keyboard", type=str, default=KEYBOARD_DEVICE)
_parser.add_argument("--keycode", type=int, default=KEY_CODE)
_parser.add_argument("--host", type=str, default=OMNI_HOST)
_parser.add_argument("--port", type=int, default=OMNI_PORT)
_parser.add_argument("--token", type=str, default=None)
_parser.add_argument("--prompt", type=str, default=PROMPT)
_args, _ = _parser.parse_known_args()

KEYBOARD_DEVICE = _args.keyboard
KEY_CODE = _args.keycode
OMNI_HOST = _args.host
OMNI_PORT = _args.port
OMNI_TOKEN = _args.token
PROMPT = _args.prompt

ENDPOINT = f"http://{OMNI_HOST}:{OMNI_PORT}/v1/chat/completions"


def type_text(text):
    subprocess.run(
        ["xdotool", "type", "--clearmodifiers", "--delay", "0", "--", text],
        check=True,
    )


def transcribe(audio):
    """Send audio to Qwen3-Omni, return transcription."""
    wav_bytes = audio_to_wav(audio)
    b64 = base64.b64encode(wav_bytes).decode()

    payload = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": b64,
                            "format": "wav",
                        },
                    },
                    {"type": "text", "text": PROMPT},
                ],
            }
        ]
    }

    headers = {"Content-Type": "application/json"}
    if OMNI_TOKEN:
        headers["Authorization"] = f"Bearer {OMNI_TOKEN}"

    resp = requests.post(ENDPOINT, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def audio_to_wav(audio, sample_rate=SAMPLE_RATE):
    """Convert float32 numpy array to WAV bytes."""
    import io
    import struct

    pcm = (audio * 32767).clip(-32768, 32767).astype("<i2")
    buf = io.BytesIO()
    nchannels = 1
    sampwidth = 2
    nframes = len(pcm)
    byte_rate = sample_rate * nchannels * sampwidth
    block_align = nchannels * sampwidth
    bits_per_sample = sampwidth * 8

    buf.write(b"RIFF")
    buf.write(struct.pack("<I", 36 + nframes * block_align))
    buf.write(b"WAVE")
    buf.write(b"fmt ")
    buf.write(struct.pack("<I", 16))
    buf.write(struct.pack("<HH", 1, nchannels))
    buf.write(struct.pack("<II", sample_rate, byte_rate))
    buf.write(struct.pack("<HH", block_align, bits_per_sample))
    buf.write(b"data")
    buf.write(struct.pack("<I", nframes * block_align))
    buf.write(pcm.tobytes())
    return buf.getvalue()


def wait_for_server(max_wait=60):
    import time

    print(f"Waiting for server at {ENDPOINT}...", end="", flush=True)
    for i in range(max_wait):
        try:
            r = requests.get(
                f"http://{OMNI_HOST}:{OMNI_PORT}/health", timeout=2
            )
            info = r.json()
            print(f" OK (status: {info.get('status', '?')})")
            return True
        except Exception:
            print(".", end="", flush=True)
            time.sleep(1)
    print(" TIMEOUT")
    return False


def main():
    if not wait_for_server():
        print(f"Cannot reach Omni server at {ENDPOINT}")
        sys.exit(1)

    kbd = evdev.InputDevice(KEYBOARD_DEVICE)
    print(f"Keyboard: {kbd.name} ({kbd.path})")
    print(f"Prompt:   {PROMPT}")
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

                print(f"  Sending {duration:.1f}s to Omni...", end="", flush=True)
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
