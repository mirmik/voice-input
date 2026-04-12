#!/usr/bin/env python3
"""
STT server: loads Whisper model and exposes HTTP API.
Accepts audio via POST, returns transcribed text.

POST /stt  — multipart audio file or raw float32 PCM
GET /health — check if server is alive
"""

import atexit
import os
import signal
import time

import numpy as np
from flask import Flask, request, jsonify
from faster_whisper import WhisperModel

from config import MODEL_SIZE, LANGUAGE, SAMPLE_RATE, STT_TOKEN, STT_PORT

HOST = "0.0.0.0"
PID_FILE = os.path.expanduser("~/.config/voice-input/stt_server.pid")

print(f"Loading Whisper {MODEL_SIZE}...")
model = WhisperModel(MODEL_SIZE, device="cuda", compute_type="float16")
print("Model loaded.")
if STT_TOKEN:
    print("Authentication enabled.")

app = Flask(__name__)


def check_auth():
    if not STT_TOKEN:
        return True
    token = request.headers.get("Authorization", "").removeprefix("Bearer ")
    return token == STT_TOKEN


@app.route("/stt", methods=["POST"])
def handle_stt():
    if not check_auth():
        return jsonify({"error": "unauthorized"}), 401
    if "audio" in request.files:
        raw = request.files["audio"].read()
        audio = np.frombuffer(raw, dtype=np.float32)
    elif request.content_type == "application/octet-stream":
        audio = np.frombuffer(request.data, dtype=np.float32)
    else:
        return jsonify({"error": "send audio as file or raw PCM"}), 400

    duration = len(audio) / SAMPLE_RATE
    if duration < 0.3:
        return jsonify({"text": "", "duration": duration})

    prompt = request.args.get("prompt", "") or request.headers.get("X-Initial-Prompt", "")
    segments, info = model.transcribe(audio, language=LANGUAGE, beam_size=5,
                                      initial_prompt=prompt or None)
    text = " ".join(s.text.strip() for s in segments).strip()
    return jsonify({"text": text, "duration": duration})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "model": MODEL_SIZE})


def write_pid():
    os.makedirs(os.path.dirname(PID_FILE), exist_ok=True)
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))


def remove_pid():
    try:
        os.remove(PID_FILE)
    except FileNotFoundError:
        pass


def read_cmdline(pid):
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            raw = f.read()
    except FileNotFoundError:
        return None
    if not raw:
        return []
    return [part.decode("utf-8", errors="replace") for part in raw.split(b"\0") if part]


def is_our_server_process(pid):
    cmdline = read_cmdline(pid)
    if cmdline is None:
        return None
    script_name = os.path.basename(__file__)
    return any(os.path.basename(arg) == script_name for arg in cmdline)


def kill_old_server():
    """Kill previously running server if PID file exists."""
    try:
        with open(PID_FILE) as f:
            old_pid = int(f.read().strip())
    except (FileNotFoundError, ValueError):
        pass
        return

    if old_pid == os.getpid():
        return

    is_ours = is_our_server_process(old_pid)
    if is_ours is None:
        remove_pid()
        return
    if not is_ours:
        print(f"Removing stale PID file for foreign process {old_pid}.")
        remove_pid()
        return

    try:
        os.kill(old_pid, signal.SIGTERM)
        print(f"Killed old server (PID {old_pid}).")
        time.sleep(1)
    except ProcessLookupError:
        remove_pid()
    except PermissionError:
        raise RuntimeError(
            f"Process {old_pid} looks like {os.path.basename(__file__)}, "
            "but cannot be terminated. Stop it manually and retry."
        )


if __name__ == "__main__":
    kill_old_server()
    write_pid()
    atexit.register(remove_pid)
    print(f"STT server on {HOST}:{STT_PORT} (PID {os.getpid()})")
    app.run(host=HOST, port=STT_PORT, threaded=False)
