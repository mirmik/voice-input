#!/usr/bin/env python3
"""
STT server: loads Whisper model and exposes HTTP API.
Accepts audio via POST, returns transcribed text.

POST /stt  — multipart audio file or raw float32 PCM
GET /health — check if server is alive
"""

import io
import numpy as np
from flask import Flask, request, jsonify
from faster_whisper import WhisperModel

from config import MODEL_SIZE, LANGUAGE, SAMPLE_RATE, STT_TOKEN

HOST = "0.0.0.0"
PORT = 5055

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

    segments, info = model.transcribe(audio, language=LANGUAGE, beam_size=5)
    text = " ".join(s.text.strip() for s in segments).strip()
    return jsonify({"text": text, "duration": duration})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "model": MODEL_SIZE})


if __name__ == "__main__":
    print(f"STT server on {HOST}:{PORT}")
    app.run(host=HOST, port=PORT, threaded=False)
