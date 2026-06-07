"""Shared voice-input configuration helpers."""

import json
import os


CONFIG_DIR = os.path.expanduser("~/.config/voice-input")
TOOL_CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
CLIENT_LOG_PATH = os.path.join(CONFIG_DIR, "client.log")

DEFAULT_STT_PROFILE = "voice-input-stt"
DEFAULT_STT_SERVER_URL = "http://localhost:5055"
DEFAULT_SAMPLE_RATE = 16000


def default_tool_config():
    return {
        "version": 1,
        "PYTHON": "python" if os.name == "nt" else "python3",
        "profile": DEFAULT_STT_PROFILE,
        "sample_rate": DEFAULT_SAMPLE_RATE,
        "monitor": False,
        "health_timeout": 0.6,
        "platform": None,
        "stt": {
            "server_url": DEFAULT_STT_SERVER_URL,
            "profile": DEFAULT_STT_PROFILE,
            "tls_fingerprint": "",
            "auth": {
                "token": "",
                "host_id": "",
            },
        },
    }


def _deep_merge(base, overrides):
    out = dict(base)
    for key, value in (overrides or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _legacy_overrides(raw):
    stt = {}
    if raw.get("STT_SERVER"):
        stt["server_url"] = raw["STT_SERVER"]
    if raw.get("TLS_FINGERPRINT"):
        stt["tls_fingerprint"] = raw["TLS_FINGERPRINT"]
    if raw.get("profile"):
        stt["profile"] = raw["profile"]
    if not stt:
        return raw
    merged = dict(raw)
    merged["stt"] = _deep_merge(raw.get("stt") or {}, stt)
    return merged


def load_tool_config():
    cfg = default_tool_config()
    if not os.path.isfile(TOOL_CONFIG_PATH):
        return cfg
    try:
        with open(TOOL_CONFIG_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError:
        return cfg
    if not isinstance(raw, dict):
        return cfg
    return _deep_merge(cfg, _legacy_overrides(raw))


def save_tool_config(config):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(TOOL_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
        f.write("\n")


def configured_python():
    cfg = load_tool_config()
    return cfg.get("PYTHON") or ("python" if os.name == "nt" else "python3")


def client_log_path():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    return CLIENT_LOG_PATH


def normalize_server_url(url):
    value = (url or "").strip()
    if not value:
        return DEFAULT_STT_SERVER_URL
    if "://" not in value:
        value = "http://" + value
    return value.rstrip("/")


def stt_settings(config=None):
    cfg = config or load_tool_config()
    stt = cfg.get("stt") or {}
    profile = stt.get("profile") or cfg.get("profile") or DEFAULT_STT_PROFILE
    server_url = normalize_server_url(stt.get("server_url"))
    auth = stt.get("auth") or {}
    return {
        "profile": profile,
        "server_url": server_url,
        "tls_fingerprint": stt.get("tls_fingerprint") or "",
        "token": auth.get("token") or "",
        "host_id": auth.get("host_id") or "",
    }


def build_nemor_config(config=None):
    stt = stt_settings(config)
    backend = {"url": stt["server_url"]}
    if stt["tls_fingerprint"]:
        backend["tls_fingerprint"] = stt["tls_fingerprint"]
    hosts = {}
    if stt["token"]:
        backend["auth"] = "voice-input"
        hosts["voice-input"] = {"token": stt["token"]}
        if stt["host_id"]:
            hosts["voice-input"]["host_id"] = stt["host_id"]
    return {
        "profiles": {
            stt["profile"]: {
                "kind": "stt",
                "backends": [backend],
            },
        },
        "defaults": {"stt": stt["profile"]},
        "hosts": hosts,
    }


def ensure_runtime_configs():
    cfg = load_tool_config()
    if not os.path.isfile(TOOL_CONFIG_PATH):
        save_tool_config(cfg)
    return cfg


def client_defaults(config=None):
    cfg = config or load_tool_config()
    stt = stt_settings(cfg)
    return {
        "profile": stt["profile"],
        "config": None,
        "sample_rate": int(cfg.get("sample_rate") or DEFAULT_SAMPLE_RATE),
        "monitor": bool(cfg.get("monitor")),
        "health_timeout": cfg.get("health_timeout"),
        "platform": cfg.get("platform"),
    }
