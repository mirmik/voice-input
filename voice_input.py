#!/usr/bin/env python3
"""
Voice input: hold Right Alt to record, release to transcribe and type.
No grab — listens passively, Right Alt still triggers system actions
but also starts recording.

Requires: pip install faster-whisper evdev sounddevice numpy
Requires: sudo apt install xdotool
"""

import subprocess
import evdev
from evdev import ecodes
import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

# --- Config ---
KEY_CODE = ecodes.KEY_RIGHTALT
SAMPLE_RATE = 16000
MODEL_SIZE = "large-v3"
LANGUAGE = "ru"


def type_text(text):
    subprocess.run(
        ["xdotool", "type", "--clearmodifiers", "--delay", "0", "--", text],
        check=True,
    )


def main():
    print(f"Loading Whisper {MODEL_SIZE}...")
    model = WhisperModel(MODEL_SIZE, device="cuda", compute_type="float16")
    print("Model loaded.")

    kbd = evdev.InputDevice("/dev/input/event7")
    print(f"Keyboard: {kbd.name} ({kbd.path})")
    print(f"Listening (no grab). Right Alt = push-to-talk.")
    print(f"Ctrl+C to exit.\n")

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

            # Key down
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

            # Key up (ignore repeat)
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

                if text:
                    print(f"  >>> {text}")
                    type_text(text)
                else:
                    print("  (no speech detected)")

    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        print("Done.")


if __name__ == "__main__":
    main()
