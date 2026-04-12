#!/usr/bin/env python3
"""
Whisper STT server for AMD GPUs via ROCm + PyTorch + Transformers.

POST /stt     - multipart "audio" file or raw float32 PCM
GET  /health  - server status and backend details

This server is intentionally separate from stt_server.py so the existing
CUDA/faster-whisper path remains unchanged.
"""

import atexit
import os
import signal
import time

import numpy as np
from flask import Flask, jsonify, request

from config import LANGUAGE, MODEL_SIZE, SAMPLE_RATE, STT_PORT, STT_TOKEN

HOST = "0.0.0.0"
PID_FILE = os.path.expanduser("~/.config/voice-input/stt_server_rocm.pid")
DEFAULT_MODEL_MAP = {
    "tiny": "openai/whisper-tiny",
    "base": "openai/whisper-base",
    "small": "openai/whisper-small",
    "medium": "openai/whisper-medium",
    "large-v2": "openai/whisper-large-v2",
    "large-v3": "openai/whisper-large-v3",
    "large-v3-turbo": "openai/whisper-large-v3-turbo",
    "turbo": "openai/whisper-large-v3-turbo",
}


def resolve_model_id():
    override = os.environ.get("STT_MODEL_ID")
    if override:
        return override
    return DEFAULT_MODEL_MAP.get(MODEL_SIZE, MODEL_SIZE)


class RocmWhisper:
    def __init__(self, model_id, language, sample_rate):
        import torch
        from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor

        if not torch.cuda.is_available():
            raise RuntimeError("torch.cuda.is_available() is false; ROCm GPU is not available")
        if not getattr(torch.version, "hip", None):
            raise RuntimeError("PyTorch is not built with ROCm/HIP support")

        self.torch = torch
        self.language = language
        self.sample_rate = sample_rate
        self.model_id = model_id
        self.device = "cuda:0"
        self.dtype = torch.float16

        print(f"Loading Whisper model {model_id} on ROCm ({self.device})...")
        self.processor = AutoProcessor.from_pretrained(model_id)
        self.model = AutoModelForSpeechSeq2Seq.from_pretrained(
            model_id,
            torch_dtype=self.dtype,
            low_cpu_mem_usage=True,
            use_safetensors=True,
        )
        self.model.to(self.device)
        self.model.eval()
        print("Model loaded.")

    def transcribe(self, audio, prompt=None):
        inputs = self.processor(audio, sampling_rate=self.sample_rate, return_tensors="pt")
        input_features = inputs.input_features.to(device=self.device, dtype=self.dtype)

        generate_kwargs = {"task": "transcribe"}
        if self.language:
            generate_kwargs["language"] = self.language
        if prompt:
            prompt_ids = self.processor.get_prompt_ids(prompt)
            if prompt_ids is not None and len(prompt_ids) > 0:
                generate_kwargs["prompt_ids"] = self.torch.tensor(
                    prompt_ids, device=self.device, dtype=self.torch.long
                )

        with self.torch.inference_mode():
            generated_ids = self.model.generate(input_features, **generate_kwargs)

        text = self.processor.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()
        return text


MODEL_ID = resolve_model_id()
model = RocmWhisper(MODEL_ID, LANGUAGE, SAMPLE_RATE)

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
    text = model.transcribe(audio, prompt=prompt or None)
    return jsonify({"text": text, "duration": duration})


@app.route("/health", methods=["GET"])
def health():
    return jsonify(
        {
            "status": "ok",
            "backend": "transformers-rocm",
            "model": MODEL_ID,
            "device": model.device,
        }
    )


def write_pid():
    os.makedirs(os.path.dirname(PID_FILE), exist_ok=True)
    with open(PID_FILE, "w", encoding="utf-8") as f:
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
    try:
        with open(PID_FILE, encoding="utf-8") as f:
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
        print(f"Killed old ROCm server (PID {old_pid}).")
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
    print(f"ROCm STT server on {HOST}:{STT_PORT} (PID {os.getpid()})")
    app.run(host=HOST, port=STT_PORT, threaded=False)
