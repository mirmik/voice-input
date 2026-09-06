#!/usr/bin/env python3
"""GigaAM-v3 e2e RNN-T server compatible with the voice-input STT API."""

import atexit
import os
import time
from pathlib import Path

import numpy as np
import torch
from flask import Flask, jsonify, request
from transformers import AutoConfig, AutoModel

from servers import config as voice_config


HOST = os.environ.get("STT_HOST", "127.0.0.1")
SAMPLE_RATE = voice_config.SAMPLE_RATE
STT_TOKEN = getattr(voice_config, "STT_TOKEN", "")
PORT = int(os.environ.get("STT_PORT_OVERRIDE", voice_config.STT_PORT))
MODEL_ID = os.environ.get("GIGAAM_MODEL_ID", "ai-sage/GigaAM-v3")
MODEL_REVISION = os.environ.get("GIGAAM_REVISION", "e2e_rnnt")
MAX_AUDIO_SECONDS = float(os.environ.get("GIGAAM_MAX_AUDIO_SECONDS", "25"))
PID_FILE = os.path.expanduser(f"~/.config/voice-input/stt_server_gigaam_{PORT}.pid")


class GigaAMRecognizer:
    def __init__(self):
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA GPU is not available")

        self.device = torch.device("cuda:0")
        print(
            f"Loading {MODEL_ID}@{MODEL_REVISION} on "
            f"{torch.cuda.get_device_name(self.device)}...",
            flush=True,
        )
        started = time.perf_counter()
        model_path = Path(MODEL_ID).expanduser()
        if model_path.is_dir():
            config = AutoConfig.from_pretrained(
                model_path,
                trust_remote_code=True,
            )
            model = AutoModel.from_config(config, trust_remote_code=True)
            state_dict = torch.load(
                model_path / "pytorch_model.bin",
                map_location="cpu",
                weights_only=True,
            )
            model.load_state_dict(state_dict)
        else:
            model = AutoModel.from_pretrained(
                MODEL_ID,
                revision=MODEL_REVISION,
                trust_remote_code=True,
            )
        self.model = model.to(self.device).eval()
        print(f"Model loaded in {time.perf_counter() - started:.2f}s.", flush=True)

        if os.environ.get("GIGAAM_WARMUP", "1") != "0":
            print("Warming up GigaAM kernels...", flush=True)
            self.transcribe_pcm(np.zeros(SAMPLE_RATE // 2, dtype=np.float32))
            print("Warmup complete.", flush=True)

    @torch.inference_mode()
    def transcribe_pcm(self, audio: np.ndarray) -> str:
        """Run the upstream model directly on float32 PCM without a temp WAV."""
        inner = self.model.model
        wav = torch.from_numpy(np.asarray(audio, dtype=np.float32).copy())
        wav = wav.to(device=inner._device, dtype=inner._dtype).unsqueeze(0)
        length = torch.full([1], wav.shape[-1], device=inner._device)
        encoded, encoded_len = inner.forward(wav, length)
        return inner.decoding.decode(inner.head, encoded, encoded_len)[0].strip()


recognizer = GigaAMRecognizer()
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
    elif request.content_type == "application/octet-stream":
        raw = request.data
    else:
        return jsonify({"error": "send float32 PCM as a file or raw body"}), 400

    if len(raw) % np.dtype(np.float32).itemsize:
        return jsonify({"error": "audio body is not aligned float32 PCM"}), 400

    audio = np.frombuffer(raw, dtype=np.float32)
    duration = len(audio) / SAMPLE_RATE
    if duration < 0.3:
        return jsonify({"text": "", "duration": duration})
    if duration > MAX_AUDIO_SECONDS:
        return jsonify({
            "error": f"audio is {duration:.2f}s; GigaAM short-form limit is {MAX_AUDIO_SECONDS:.0f}s"
        }), 413

    text = recognizer.transcribe_pcm(audio)
    return jsonify({"text": text, "duration": duration})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "backend": "gigaam-rocm" if getattr(torch.version, "hip", None) else "gigaam-cuda",
        "model": MODEL_ID,
        "revision": MODEL_REVISION,
        "device": str(recognizer.device),
        "max_audio_seconds": MAX_AUDIO_SECONDS,
    })


def write_pid():
    os.makedirs(os.path.dirname(PID_FILE), exist_ok=True)
    with open(PID_FILE, "w", encoding="utf-8") as handle:
        handle.write(str(os.getpid()))


def remove_pid():
    try:
        os.remove(PID_FILE)
    except FileNotFoundError:
        pass


if __name__ == "__main__":
    write_pid()
    atexit.register(remove_pid)
    print(f"GigaAM STT server on {HOST}:{PORT} (PID {os.getpid()})", flush=True)
    app.run(host=HOST, port=PORT, threaded=False)
