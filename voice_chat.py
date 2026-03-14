#!/usr/bin/env python3
"""
Voice chat with Claude: hold Right Alt to record, release to transcribe,
send to Claude Code via --continue -p, print response.

Requires: pip install faster-whisper evdev sounddevice numpy
"""

import subprocess
import requests
import evdev
from evdev import UInput, ecodes
import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

# --- Config ---
KEY_CODE = ecodes.KEY_RIGHTALT
SAMPLE_RATE = 16000
MODEL_SIZE = "large-v3"
LANGUAGE = "ru"
CLAUDE_SESSION = "6e5f8cb6-b8c8-4f23-9847-40011352aaed"
TTS_URL = "http://localhost:5050/tts"


def ask_claude(text):
    result = subprocess.run(
        ["claude", "--resume", CLAUDE_SESSION, "-p", text],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result.stdout.strip()


def speak(text):
    try:
        requests.post(TTS_URL, json={"text": text, "language": "ru"}, timeout=30)
    except Exception as e:
        print(f"  TTS error: {e}")


def main():
    print(f"Loading Whisper {MODEL_SIZE}...")
    model = WhisperModel(MODEL_SIZE, device="cuda", compute_type="float16")
    print("Model loaded.\n")

    kbd = evdev.InputDevice("/dev/input/event7")
    ui = UInput.from_device(kbd, name="voice-chat-proxy")
    kbd.grab()
    print(f"Keyboard grabbed. Right Alt = push-to-talk.")
    print(f"Ctrl+C to exit.\n")

    recording = False
    chunks = []
    stream = None

    def audio_callback(indata, frames, time, status):
        chunks.append(indata.copy())

    try:
        for event in kbd.read_loop():
            if event.type == ecodes.EV_KEY and event.code == KEY_CODE:
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

                    print(f"  Transcribing {duration:.1f}s...")
                    segments, info = model.transcribe(
                        audio, language=LANGUAGE, beam_size=5
                    )
                    text = " ".join(s.text.strip() for s in segments).strip()

                    if not text:
                        print("  (no speech detected)")
                        continue

                    print(f"  You: {text}")
                    print(f"  Asking Claude...", end="", flush=True)

                    try:
                        response = ask_claude(text)
                        print(f" done.")
                        print(f"  Claude: {response}\n")
                        if response:
                            speak(response)
                    except subprocess.TimeoutExpired:
                        print(f" timeout!")
                    except Exception as e:
                        print(f" error: {e}")
            else:
                ui.write_event(event)
                ui.syn()

    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        kbd.ungrab()
        ui.close()
        print("Keyboard released.")


if __name__ == "__main__":
    main()
