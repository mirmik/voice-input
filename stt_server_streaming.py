#!/usr/bin/env python3
"""
Streaming STT server: accepts audio chunks via WebSocket,
returns partial and final transcription results in real-time.

Architecture: WebSocket handler feeds audio to a queue.
A dedicated worker thread runs Whisper inference.
Results are sent back via asyncio callback.

Protocol:
  Client sends:
    - binary frames: raw float32 PCM audio chunks (16kHz mono)
    - text "done": signals end of recording
    - text "cancel": abort without final result

  Server sends:
    - {"type": "partial", "text": "..."} — intermediate result
    - {"type": "final", "text": "..."}   — confirmed final result
    - {"type": "ready"}                  — server ready for audio

Requires: pip install websockets faster-whisper numpy
"""

import asyncio
import argparse
import json
import os
import queue
import threading
import time

import numpy as np
from faster_whisper import WhisperModel

from config import MODEL_SIZE, LANGUAGE, SAMPLE_RATE, STT_TOKEN

DEFAULT_PORT = 5080
PARTIAL_INTERVAL = 1.0
WINDOW_SEC = 15


def parse_args():
    parser = argparse.ArgumentParser(description="Streaming STT Server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--window", type=float, default=WINDOW_SEC)
    return parser.parse_args()


def transcribe_audio(model, audio, beam_size=1):
    """Run whisper on audio array, return text."""
    if len(audio) / SAMPLE_RATE < 0.3:
        return ""
    segments, _ = model.transcribe(
        audio, language=LANGUAGE, beam_size=beam_size,
        vad_filter=True,
    )
    return " ".join(s.text.strip() for s in segments).strip()


class Session:
    """
    One recording session. Accumulates audio, runs partial
    transcription on a sliding window, and final on the full audio.
    """
    def __init__(self, model, send_fn, window_sec=WINDOW_SEC):
        self.model = model
        self.send_fn = send_fn  # async callback to send JSON to client
        self.window_samples = int(window_sec * SAMPLE_RATE)
        self.lock = threading.Lock()
        self.audio_chunks = []
        self.total_samples = 0
        self.confirmed_text = ""
        self.confirmed_samples = 0
        self.done = threading.Event()
        self.cancelled = False
        self.loop = None  # set by caller
        self.last_partial_text = ""

    def add_audio(self, pcm):
        with self.lock:
            self.audio_chunks.append(pcm)
            self.total_samples += len(pcm)

    def _get_all_audio(self):
        with self.lock:
            if not self.audio_chunks:
                return np.array([], dtype=np.float32)
            return np.concatenate(self.audio_chunks)

    def run_partials(self):
        """Run in a worker thread. Periodically transcribe and send partial."""
        while not self.done.is_set():
            self.done.wait(timeout=PARTIAL_INTERVAL)
            if self.done.is_set() or self.cancelled:
                break

            all_audio = self._get_all_audio()
            if len(all_audio) == 0:
                continue

            # Transcribe in chunks: confirmed parts + sliding window
            total_len = len(all_audio)

            # If we have more audio than the window, confirm earlier parts
            if total_len > self.confirmed_samples + self.window_samples * 1.5:
                # Confirm everything except the last window
                confirm_end = total_len - self.window_samples
                new_audio = all_audio[self.confirmed_samples:confirm_end]
                if len(new_audio) / SAMPLE_RATE >= 0.5:
                    new_text = transcribe_audio(self.model, new_audio, beam_size=3)
                    if new_text:
                        self.confirmed_text = (self.confirmed_text + " " + new_text).strip()
                    self.confirmed_samples = confirm_end

            # Transcribe the tail (window)
            window_audio = all_audio[self.confirmed_samples:]
            if len(window_audio) / SAMPLE_RATE < 0.5:
                text = self.confirmed_text
            else:
                window_text = transcribe_audio(self.model, window_audio, beam_size=1)
                text = (self.confirmed_text + " " + window_text).strip() if self.confirmed_text else window_text

            self.last_partial_text = text

            if text and self.loop:
                asyncio.run_coroutine_threadsafe(
                    self.send_fn({"type": "partial", "text": text}),
                    self.loop
                )

    def run_final(self):
        """Fast final: use confirmed text + re-transcribe only the tail with higher quality."""
        all_audio = self._get_all_audio()
        duration = len(all_audio) / SAMPLE_RATE
        print(f"  Final ({duration:.1f}s, confirmed: {len(self.confirmed_text)} chars)...")

        if duration < 0.3:
            return ""

        # For short recordings, just transcribe everything
        if duration < WINDOW_SEC:
            result = transcribe_audio(self.model, all_audio, beam_size=5)
            print(f"  Result: {result[:80]}{'...' if len(result) > 80 else ''}")
            return result

        # For longer: keep confirmed text, re-transcribe tail with beam_size=5
        tail_audio = all_audio[self.confirmed_samples:]
        if len(tail_audio) / SAMPLE_RATE < 0.3:
            result = self.confirmed_text
        else:
            tail_text = transcribe_audio(self.model, tail_audio, beam_size=5)
            result = (self.confirmed_text + " " + tail_text).strip() if self.confirmed_text else tail_text

        print(f"  Result: {result[:80]}{'...' if len(result) > 80 else ''}")
        return result


def merge_parts(parts):
    if not parts:
        return ""
    result = parts[0]
    for part in parts[1:]:
        if not part:
            continue
        words_r = result.split()
        words_p = part.split()
        best = 0
        for n in range(1, min(8, len(words_r), len(words_p)) + 1):
            if words_r[-n:] == words_p[:n]:
                best = n
        if best > 0:
            result = result + " " + " ".join(words_p[best:])
        else:
            result = result + " " + part
    return result.strip()


async def handle_client(websocket, model, window_sec):
    # Auth
    if STT_TOKEN:
        try:
            auth_msg = await asyncio.wait_for(websocket.recv(), timeout=5)
            auth = json.loads(auth_msg)
            if auth.get("token") != STT_TOKEN:
                await websocket.send(json.dumps({"type": "error", "text": "unauthorized"}))
                return
        except (asyncio.TimeoutError, json.JSONDecodeError):
            await websocket.send(json.dumps({"type": "error", "text": "auth required"}))
            return

    loop = asyncio.get_event_loop()

    async def send_msg(msg):
        try:
            await websocket.send(json.dumps(msg))
        except Exception:
            pass

    session = Session(model, send_msg, window_sec=window_sec)
    session.loop = loop

    await websocket.send(json.dumps({"type": "ready"}))
    print(f"  Client connected")

    # Start partial worker thread
    partial_thread = threading.Thread(target=session.run_partials, daemon=True)
    partial_thread.start()

    try:
        async for message in websocket:
            if isinstance(message, bytes):
                pcm = np.frombuffer(message, dtype=np.float32)
                session.add_audio(pcm)

            elif isinstance(message, str):
                msg = message.strip().lower()
                if msg == "done":
                    session.done.set()
                    partial_thread.join(timeout=5)

                    # Run final in thread
                    text = await loop.run_in_executor(
                        None, session.run_final
                    )
                    await websocket.send(json.dumps({
                        "type": "final", "text": text
                    }))
                    return

                elif msg == "cancel":
                    session.cancelled = True
                    session.done.set()
                    await websocket.send(json.dumps({"type": "cancelled"}))
                    return

    except Exception as e:
        print(f"  Client error: {e}")
    finally:
        session.done.set()
        print(f"  Client disconnected")


async def main():
    import websockets

    args = parse_args()
    model_size = args.model or MODEL_SIZE

    print(f"Loading Whisper {model_size}...")
    model = WhisperModel(model_size, device="cuda", compute_type="float16")
    print("Model loaded.")

    if STT_TOKEN:
        print("Authentication enabled.")

    print(f"Streaming STT server on ws://{args.host}:{args.port}")
    print(f"  Partial interval: {PARTIAL_INTERVAL}s")
    print(f"  Window size: {args.window}s")
    print()

    async with websockets.serve(
        lambda ws: handle_client(ws, model, args.window),
        args.host, args.port,
        max_size=10 * 1024 * 1024,
    ):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
