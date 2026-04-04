#!/usr/bin/env python3
"""
Streaming STT client: push-to-talk via evdev, streams audio to
WebSocket STT server, shows partial results in real-time,
types final text via xdotool on key release.

Requires: pip install evdev sounddevice numpy websockets
Requires: sudo apt install xdotool
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import threading

import evdev
from evdev import ecodes
import numpy as np
import sounddevice as sd

from config import KEYBOARD_DEVICE, KEY_CODE, SAMPLE_RATE, STT_TOKEN

DEFAULT_WS_URL = "ws://localhost:5080"

# Load overrides
_config_candidates = [
    os.path.expanduser("~/.config/voice-input/config.json"),
]
_ws_url = DEFAULT_WS_URL
for _cfg_path in _config_candidates:
    if os.path.exists(_cfg_path):
        with open(_cfg_path) as _f:
            _overrides = json.load(_f)
        _ws_url = _overrides.get("STT_WS_URL", _ws_url)
        break


def parse_args():
    parser = argparse.ArgumentParser(description="Streaming STT Client")
    parser.add_argument("--url", type=str, default=_ws_url,
                        help=f"WebSocket server URL (default: {_ws_url})")
    parser.add_argument("--host", type=str, default=None)
    parser.add_argument("--port", type=int, default=None)
    return parser.parse_args()


def type_text(text):
    subprocess.run(
        ["xdotool", "type", "--clearmodifiers", "--delay", "0", "--", text],
        check=True,
    )


class StreamingSTTClient:
    def __init__(self, ws_url):
        self.ws_url = ws_url
        self.ws = None
        self.recording = False
        self.stream = None
        self.loop = None
        self.final_text = ""
        self.partial_text = ""
        self.connected = False

    async def connect(self):
        import websockets
        self.ws = await websockets.connect(self.ws_url, max_size=10*1024*1024)

        # Auth
        if STT_TOKEN:
            await self.ws.send(json.dumps({"token": STT_TOKEN}))

        # Wait for ready
        msg = json.loads(await self.ws.recv())
        if msg.get("type") == "error":
            print(f"  Server error: {msg.get('text')}")
            return False
        if msg.get("type") == "ready":
            self.connected = True
            return True
        return False

    async def disconnect(self):
        if self.ws:
            await self.ws.close()
            self.ws = None
            self.connected = False

    async def send_audio(self, pcm_f32):
        if self.ws and self.connected:
            await self.ws.send(pcm_f32.tobytes())

    async def send_done(self):
        if self.ws and self.connected:
            await self.ws.send("done")

    async def send_cancel(self):
        if self.ws and self.connected:
            await self.ws.send("cancel")

    async def recv_loop(self):
        """Receive partial/final results from server."""
        try:
            async for msg_raw in self.ws:
                msg = json.loads(msg_raw)
                if msg["type"] == "partial":
                    self.partial_text = msg["text"]
                    # Clear line and show partial
                    text_preview = self.partial_text[:80]
                    print(f"\r  \033[90m{text_preview}\033[0m\033[K", end="", flush=True)
                elif msg["type"] == "final":
                    self.final_text = msg["text"]
                    return
                elif msg["type"] == "cancelled":
                    return
        except Exception:
            pass


async def session(client, kbd):
    """Run one PTT session: wait for key, stream audio, get result."""
    recording = False
    chunks = []
    stream = None
    recv_task = None

    def audio_callback(indata, frames, time, status):
        if recording:
            chunks.append(indata.copy())

    print("Push-to-talk active. Ctrl+C to exit.\n")

    loop = asyncio.get_event_loop()

    # Run evdev in thread
    key_events = asyncio.Queue()

    def evdev_reader():
        for event in kbd.read_loop():
            if event.type == ecodes.EV_KEY and event.code == KEY_CODE:
                ke = evdev.categorize(event)
                loop.call_soon_threadsafe(
                    key_events.put_nowait, ke.keystate
                )

    reader_thread = threading.Thread(target=evdev_reader, daemon=True)
    reader_thread.start()

    while True:
        keystate = await key_events.get()

        if keystate == evdev.KeyEvent.key_down and not recording:
            # Connect and start recording
            client.final_text = ""
            client.partial_text = ""

            try:
                await client.connect()
            except Exception as e:
                print(f"  Connection failed: {e}")
                continue

            recording = True
            chunks.clear()
            stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                callback=audio_callback,
            )
            stream.start()

            # Start receiving results
            recv_task = asyncio.create_task(client.recv_loop())

            # Start sending audio chunks
            print("  Recording...", end="", flush=True)

            # Periodic sender
            async def send_chunks():
                while recording:
                    await asyncio.sleep(0.3)
                    if chunks:
                        audio = np.concatenate(chunks)
                        chunks.clear()
                        await client.send_audio(audio)

            send_task = asyncio.create_task(send_chunks())

        elif keystate == evdev.KeyEvent.key_up and recording:
            recording = False

            # Cancel sender first
            send_task.cancel()

            # Stop audio
            if stream:
                stream.stop()
                stream.close()

            # Send remaining audio
            if chunks:
                audio = np.concatenate(chunks)
                chunks.clear()
                await client.send_audio(audio)

            # Signal done
            await client.send_done()

            print("\r  Waiting for final result...\033[K", end="", flush=True)

            # Wait for final result
            if recv_task:
                try:
                    await asyncio.wait_for(recv_task, timeout=30)
                except asyncio.TimeoutError:
                    print("\n  Timeout waiting for final result")

            await client.disconnect()

            print()  # newline
            if client.final_text:
                print(f"  >>> {client.final_text}")
                type_text(client.final_text)
            else:
                print("  (no speech)")


def main():
    args = parse_args()

    ws_url = args.url
    if args.host or args.port:
        from urllib.parse import urlparse
        parsed = urlparse(ws_url)
        host = args.host or parsed.hostname
        port = args.port or parsed.port or 5080
        ws_url = f"ws://{host}:{port}"

    print(f"Streaming STT client")
    print(f"  Server: {ws_url}")
    print(f"  Keyboard: {KEYBOARD_DEVICE}, key code: {KEY_CODE}")
    print()

    kbd = evdev.InputDevice(KEYBOARD_DEVICE)
    print(f"  Device: {kbd.name}")

    client = StreamingSTTClient(ws_url)

    try:
        asyncio.run(session(client, kbd))
    except KeyboardInterrupt:
        print("\nExiting...")


if __name__ == "__main__":
    main()
