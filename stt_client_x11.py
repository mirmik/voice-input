#!/usr/bin/env python3
"""
STT client — push-to-talk via X11 XGrabKey (F13).

Binds globally on F13 through XGrabKey. With the standard Xmodmap remap
`keycode 108 = F13` the physical Right Alt key becomes F13 at the X level,
so hold Right Alt to record, release to send.

No evdev, no /dev/input access, no `input` group membership — plain user
privileges. X11-only; Wayland needs a different mechanism.

Requires: pip install python-xlib sounddevice numpy requests
Requires: sudo apt install xdotool
"""

import argparse
import json
import os
import subprocess
import sys
import threading
import time

import numpy as np
import requests
import select
import sounddevice as sd
from Xlib import X, XK, display

from config import SAMPLE_RATE, STT_SERVER, LLM_PROXY_AUTH_FILE


# X11 auto-repeats a held key as repeated (release, press) pairs ~30ms apart.
# We filter them out by timing: a release is "real" only if no matching press
# arrives within AUTOREPEAT_WINDOW seconds.
AUTOREPEAT_WINDOW = 0.030


# --- CLI overrides ---
_parser = argparse.ArgumentParser(add_help=False)
_parser.add_argument("--host", type=str, default=None)
_parser.add_argument("--port", type=int, default=None)
_parser.add_argument("--auth-file", type=str, default=None)
_parser.add_argument("--key", type=str, default="F13",
                     help="X11 keysym to bind (default F13)")
_args, _ = _parser.parse_known_args()


def load_proxy_auth():
    path = os.path.expanduser(_args.auth_file or LLM_PROXY_AUTH_FILE)
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
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
    h = {}
    if _token:
        h["Authorization"] = f"Bearer {_token}"
    if _host_id:
        h["X-LLM-Proxy-Host-ID"] = _host_id
    return h


def type_text(text):
    subprocess.run(
        ["xdotool", "type", "--clearmodifiers", "--delay", "0", "--", text],
        check=True,
    )


def transcribe(audio):
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
    print(f"Waiting for server at {STT_SERVER}...", end="", flush=True)
    for _ in range(max_wait):
        for url in (f"{STT_SERVER}/stt/health", f"{STT_SERVER}/health"):
            try:
                r = requests.get(url, headers=auth_headers(), timeout=2)
                if r.status_code == 200:
                    info = r.json()
                    print(f" OK (model: {info.get('model_size') or info.get('model', '?')})")
                    return True
            except Exception:
                pass
        print(".", end="", flush=True)
        time.sleep(1)
    print(" TIMEOUT")
    return False


# --- Recording ---

class Recorder:
    def __init__(self):
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
                samplerate=SAMPLE_RATE,
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
        duration = len(audio) / SAMPLE_RATE
        if duration < 0.3:
            print("  (too short)")
            return
        print(f"  Sending {duration:.1f}s to server...", end="", flush=True)
        try:
            text = transcribe(audio)
            print(" done.")
            if text:
                print(f"  >>> {text}")
                type_text(text)
            else:
                print("  (no speech detected)")
        except Exception as e:
            print(f" error: {e}")


# --- X11 keyboard grab ---

def main():
    if not wait_for_server():
        print(f"Cannot reach STT server at {STT_SERVER}")
        sys.exit(1)

    d = display.Display()
    root = d.screen().root

    keysym = XK.string_to_keysym(_args.key)
    if keysym == 0:
        print(f"Unknown keysym: {_args.key!r}")
        sys.exit(1)
    keycode = d.keysym_to_keycode(keysym)
    if keycode == 0:
        print(f"No keycode maps to {_args.key!r} on this server")
        sys.exit(1)

    # Grab the key with every possible modifier combination we care about.
    # AnyModifier is simpler and matches what we want: fire regardless of
    # whether NumLock/CapsLock/etc is held.
    root.grab_key(keycode, X.AnyModifier, True, X.GrabModeAsync, X.GrabModeAsync)
    root.change_attributes(event_mask=X.KeyPressMask | X.KeyReleaseMask)
    d.sync()

    recorder = Recorder()
    print(f"Push-to-talk bound on {_args.key} (keycode {keycode}). Ctrl+C to exit.\n")

    pending_release_at = None  # time.monotonic() when release was seen, or None
    fd = d.fileno()

    try:
        while True:
            # Drain all queued X events first.
            while d.pending_events():
                event = d.next_event()
                if event.detail != keycode:
                    continue
                now = time.monotonic()
                if event.type == X.KeyPress:
                    if pending_release_at is not None:
                        # Real repeat — still held, cancel the pending release.
                        pending_release_at = None
                    else:
                        # First press of a hold.
                        recorder.start()
                elif event.type == X.KeyRelease:
                    pending_release_at = now

            # Did a release survive AUTOREPEAT_WINDOW without a matching press?
            if pending_release_at is not None:
                if time.monotonic() - pending_release_at >= AUTOREPEAT_WINDOW:
                    pending_release_at = None
                    threading.Thread(target=recorder.stop_and_send, daemon=True).start()

            # Block until an X event arrives or the autorepeat window ticks.
            select.select([fd], [], [], AUTOREPEAT_WINDOW)
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        root.ungrab_key(keycode, X.AnyModifier)
        d.sync()
        d.close()
        print("Done.")


if __name__ == "__main__":
    main()
