"""Plasma/Wayland hotkey and Unicode text insertion backend."""

import os
import shutil
import subprocess

import evdev
from evdev import ecodes

from voice_input.settings import load_tool_config


DEFAULT_KEY_CODE = ecodes.KEY_RIGHTALT
PASTE_KEYS = ("29:1", "47:1", "47:0", "29:0")  # Ctrl+V


def _require_command(name, package):
    if shutil.which(name) is None:
        raise RuntimeError(
            f"{name!r} is required by the Wayland backend; "
            f"install it with: sudo apt install {package}"
        )


def type_text(text):
    """Insert arbitrary Unicode through the Wayland clipboard and Ctrl+V."""
    if not text:
        return
    _require_command("wl-copy", "wl-clipboard")
    _require_command("ydotool", "ydotool ydotoold")

    subprocess.run(
        ["wl-copy", "--type", "text/plain;charset=utf-8"],
        input=text,
        text=True,
        check=True,
    )
    try:
        subprocess.run(["ydotool", "key", *PASTE_KEYS], check=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            "ydotool could not inject Ctrl+V. Make sure ydotoold is running "
            "and can access /dev/uinput."
        ) from exc


def _supports_key(device, key_code):
    keys = device.capabilities().get(ecodes.EV_KEY, ())
    return key_code in keys


def _open_keyboard(path, key_code):
    try:
        device = evdev.InputDevice(path)
    except PermissionError as exc:
        raise RuntimeError(
            f"Cannot read {path}. Add the user to the input group and log in again."
        ) from exc
    except OSError as exc:
        raise RuntimeError(f"Cannot open keyboard device {path}: {exc}") from exc
    if not _supports_key(device, key_code):
        device.close()
        raise RuntimeError(f"{path} does not expose evdev key code {key_code}")
    return device


def _find_keyboard(configured_path, key_code):
    if configured_path:
        if os.path.exists(configured_path):
            return _open_keyboard(configured_path, key_code)
        print(
            f"Configured keyboard {configured_path} does not exist; "
            "searching evdev devices...",
            flush=True,
        )

    candidates = []
    permission_errors = []
    for path in evdev.list_devices():
        try:
            device = evdev.InputDevice(path)
            if _supports_key(device, key_code):
                candidates.append(device)
            else:
                device.close()
        except PermissionError:
            permission_errors.append(path)

    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        descriptions = ", ".join(f"{d.path} ({d.name})" for d in candidates)
        for device in candidates:
            device.close()
        raise RuntimeError(
            "Several keyboards expose the configured PTT key. "
            f"Choose one with --keyboard: {descriptions}"
        )
    if permission_errors:
        raise RuntimeError(
            "No readable keyboard devices. Add the user to the input group, "
            "log out and back in, then select a device with --keyboard."
        )
    raise RuntimeError(
        f"No evdev keyboard exposing key code {key_code} was found. "
        "Use --keyboard and --key-code to configure it."
    )


def run_hotkey_loop(recorder, args):
    cfg = load_tool_config()
    keyboard_path = args.keyboard or cfg.get("KEYBOARD_DEVICE")
    key_code = args.key_code
    if key_code is None:
        key_code = int(cfg.get("KEY_CODE", DEFAULT_KEY_CODE))

    _require_command("wl-copy", "wl-clipboard")
    _require_command("ydotool", "ydotool ydotoold")
    keyboard = _find_keyboard(keyboard_path, key_code)
    key_name = ecodes.KEY.get(key_code, f"code {key_code}")
    print(f"Keyboard: {keyboard.name} ({keyboard.path})")
    print(
        f"Push-to-talk: {key_name} ({key_code}). "
        "The physical key is not suppressed. Ctrl+C to exit.\n"
    )

    down = False
    try:
        for event in keyboard.read_loop():
            if event.type != ecodes.EV_KEY or event.code != key_code:
                continue
            if event.value == 1 and not down:
                down = True
                recorder.start()
            elif event.value == 0 and down:
                down = False
                recorder.stop_async()
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        keyboard.close()
        print("Done.")
