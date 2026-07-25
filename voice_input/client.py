"""Common STT client logic shared by platform hotkey adapters."""

import sys
import threading
from types import MethodType

import nemor_link as nl
import numpy as np
import sounddevice as sd

from voice_input.platforms import load_platform
from voice_input.settings import (
    build_nemor_config,
    client_defaults,
    ensure_runtime_configs,
    load_tool_config,
)


class Recorder:
    def __init__(self, stt_client, sample_rate, type_text):
        self.stt = stt_client
        self.sample_rate = sample_rate
        self.type_text = type_text
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
            print("  Recording...", end="", flush=True)

    def _callback(self, indata, frames, time_, status):
        self.chunks.append(indata.copy())

    def stop_async(self):
        threading.Thread(target=self.stop_and_send, daemon=True).start()

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
                self.type_text(text)
            else:
                print("  (no speech detected)")
        except nl.STTError as e:
            print(f" error: {e}")
        except Exception as e:
            print(f" error: {e}")


def build_stt(
    profile=None,
    config_path=None,
    config=None,
    monitor=False,
    health_timeout=None,
):
    cfg = nl.load_config(config_path) if config_path else config
    kwargs = {}
    if health_timeout is not None:
        kwargs["health_timeout"] = health_timeout
    client = nl.stt(name=profile, monitor=monitor, config=cfg, **kwargs)

    # Some proxies expose several STT runtimes through one /stt endpoint.
    # Nemor Link owns authentication, so extend its header factory here rather
    # than duplicating the STT client.  Profiles may add a ``headers`` object
    # to a backend, e.g. {"X-STT-Runtime": "stt-gigaam"}.
    original_auth_headers = client.auth_headers

    def auth_headers(self, backend):
        headers = original_auth_headers(backend)
        extra_headers = backend.get("headers") or {}
        if not isinstance(extra_headers, dict):
            raise ValueError("STT backend 'headers' must be an object")
        headers.update({str(key): str(value) for key, value in extra_headers.items()})
        return headers

    client.auth_headers = MethodType(auth_headers, client)
    return client


def run(args):
    ensure_runtime_configs()
    tool_cfg = load_tool_config()
    defaults = client_defaults(tool_cfg)
    profile = args.profile or defaults["profile"]
    config_path = args.config or defaults["config"]
    nemor_config = None if config_path else build_nemor_config(tool_cfg)
    sample_rate = args.sample_rate or defaults["sample_rate"]
    monitor = args.monitor or defaults["monitor"]
    health_timeout = (
        args.health_timeout
        if args.health_timeout is not None
        else defaults["health_timeout"]
    )
    platform = load_platform(args.platform or defaults["platform"])

    try:
        stt = build_stt(
            profile=profile,
            config_path=config_path,
            config=nemor_config,
            monitor=monitor,
            health_timeout=health_timeout,
        )
    except nl.ConfigError as e:
        print(f"Config error: {e}", file=sys.stderr)
        return 2

    try:
        print(f"STT profile: {stt.name}")
        ok_any = False
        for url, ok, _latency in stt.pool.probe_all():
            print(f"  {'OK  ' if ok else 'FAIL'}  {url}")
            ok_any = ok_any or ok
        if not ok_any:
            print("No STT backend is reachable.", file=sys.stderr)
            return 1

        recorder = Recorder(stt, sample_rate, platform.type_text)
        platform.run_hotkey_loop(recorder, args)
        return 0
    finally:
        stt.close()
