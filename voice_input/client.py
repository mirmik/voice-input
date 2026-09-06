"""Common STT client logic shared by platform hotkey adapters."""

import sys
from types import MethodType

import nemor_link as nl

from voice_input.platforms import load_platform
from voice_input.recording import Recorder
from voice_input.settings import (
    build_nemor_config,
    client_defaults,
    ensure_runtime_configs,
    load_tool_config,
)



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
        try:
            platform.run_hotkey_loop(recorder, args)
        finally:
            recorder.close()
        return 0
    finally:
        stt.close()
