#!/usr/bin/env python3
"""
STT client — push-to-talk via X11 XGrabKey (F13).

Hold the bound key to record, release to transcribe and type the result.
The STT backend (URL + auth token) comes from the unified nemor-link
config at ~/.config/llm.json, selected by profile name.

With the standard Xmodmap remap `keycode 108 = F13`, the physical Right
Alt key becomes F13 at the X level, so any key bound as F13 (which is the
default here) acts as push-to-talk without disturbing menubars or AltGr.

Requires: pip install nemor-link python-xlib sounddevice numpy
Requires: sudo apt install xdotool    # for typing the transcription
"""

import argparse
import json
import os
import select
import subprocess
import sys
import threading
import time

import nemor_link as nl
import numpy as np
import sounddevice as sd
from Xlib import X, XK, display


AUTOREPEAT_WINDOW = 0.030  # seconds; longer than the X autorepeat period
DEFAULT_KEY = "F13"
TOOL_CONFIG_PATH = os.path.expanduser("~/.config/voice-input/config.json")


def load_tool_config():
    if not os.path.isfile(TOOL_CONFIG_PATH):
        return {}
    try:
        with open(TOOL_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}


def type_text(text):
    subprocess.run(
        ["xdotool", "type", "--clearmodifiers", "--delay", "0", "--", text],
        check=True,
    )


class Recorder:
    def __init__(self, stt_client, sample_rate):
        self.stt = stt_client
        self.sample_rate = sample_rate
        self.stream = None
        self.chunks = []
        self.active = False
        self.lock = threading.Lock()

    def start(self):
        with self.lock:
            if self.active:
                return
            self.chunks = []
            self.stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                callback=self._callback,
            )
            self.stream.start()
            self.active = True
            print("  🎙 Recording...", end="", flush=True)

    def _callback(self, indata, frames, time_, status):
        self.chunks.append(indata.copy())

    def stop_and_send(self):
        with self.lock:
            if not self.active:
                return
            self.stream.stop()
            self.stream.close()
            self.stream = None
            self.active = False
            chunks = self.chunks
            self.chunks = []
        print(" done.")

        if not chunks:
            print("  (empty)")
            return
        audio = np.concatenate(chunks).squeeze()
        duration = len(audio) / self.sample_rate
        if duration < 0.3:
            print("  (too short)")
            return
        print(f"  Sending {duration:.1f}s to STT...", end="", flush=True)
        try:
            result = self.stt.transcribe(audio.tobytes())
            text = (result or {}).get("text", "").strip()
            print(" done.")
            if text:
                print(f"  >>> {text}")
                type_text(text)
            else:
                print("  (no speech detected)")
        except nl.STTError as e:
            print(f" error: {e}")
        except Exception as e:
            print(f" error: {e}")


def parse_args():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument("--profile", default=None,
                   help="STT profile name from ~/.config/llm.json (default: configured default)")
    p.add_argument("--key", default=DEFAULT_KEY,
                   help=f"X11 keysym to bind (default {DEFAULT_KEY})")
    p.add_argument("--sample-rate", type=int, default=16000)
    p.add_argument("--monitor", action="store_true",
                   help="Enable background health-check of STT backends")
    return p.parse_args()


def main():
    args = parse_args()
    tool_cfg = load_tool_config()

    # Profile resolution: --profile flag > tool config > nemor-link default
    profile = args.profile or tool_cfg.get("profile")
    sample_rate = args.sample_rate or int(tool_cfg.get("sample_rate", 16000))

    try:
        stt = nl.stt(name=profile, monitor=args.monitor)
    except nl.ConfigError as e:
        print(f"Config error: {e}", file=sys.stderr)
        sys.exit(2)

    # Eager probe so we know the backend is reachable before grabbing keys.
    print(f"STT profile: {stt.name}")
    ok_any = False
    for url, ok, _latency in stt.pool.probe_all():
        print(f"  {'OK  ' if ok else 'FAIL'}  {url}")
        ok_any = ok_any or ok
    if not ok_any:
        print("No STT backend is reachable.", file=sys.stderr)
        stt.close()
        sys.exit(1)

    d = display.Display()
    root = d.screen().root
    keysym = XK.string_to_keysym(args.key)
    if keysym == 0:
        print(f"Unknown keysym: {args.key!r}", file=sys.stderr)
        sys.exit(1)
    keycode = d.keysym_to_keycode(keysym)
    if keycode == 0:
        print(f"No keycode maps to {args.key!r}", file=sys.stderr)
        sys.exit(1)

    root.grab_key(keycode, X.AnyModifier, True, X.GrabModeAsync, X.GrabModeAsync)
    root.change_attributes(event_mask=X.KeyPressMask | X.KeyReleaseMask)
    d.sync()

    recorder = Recorder(stt, sample_rate)
    print(f"Push-to-talk bound on {args.key} (keycode {keycode}). Ctrl+C to exit.\n")

    pending_release_at = None
    fd = d.fileno()

    try:
        while True:
            while d.pending_events():
                event = d.next_event()
                if event.type not in (X.KeyPress, X.KeyRelease):
                    continue
                if event.detail != keycode:
                    continue
                if event.type == X.KeyPress:
                    if pending_release_at is not None:
                        pending_release_at = None  # repeat → still held
                    else:
                        recorder.start()
                else:  # KeyRelease
                    pending_release_at = time.monotonic()

            if pending_release_at is not None:
                if time.monotonic() - pending_release_at >= AUTOREPEAT_WINDOW:
                    pending_release_at = None
                    threading.Thread(target=recorder.stop_and_send, daemon=True).start()

            select.select([fd], [], [], AUTOREPEAT_WINDOW)
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        root.ungrab_key(keycode, X.AnyModifier)
        d.sync()
        d.close()
        stt.close()
        print("Done.")


if __name__ == "__main__":
    main()
