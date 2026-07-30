"""Plasma/Wayland hotkey and Unicode text insertion backend."""

import os
import shutil
import subprocess
import time

import evdev
from evdev import ecodes

from voice_input.settings import load_tool_config


DEFAULT_KEY_CODE = ecodes.KEY_RIGHTALT
PASTE_KEYS = ("SHIFT+INSERT",)
CLIPBOARD_RESTORE_DELAY = 0.35
TEXT_MIME_TYPES = ("text/plain;charset=utf-8", "text/plain", "UTF8_STRING")


def _require_command(name, package):
    if shutil.which(name) is None:
        raise RuntimeError(
            f"{name!r} is required by the Wayland backend; "
            f"install it with: sudo apt install {package}"
        )


def _set_clipboard_text(text):
    subprocess.run(
        ["wl-copy", "--type", "text/plain;charset=utf-8"],
        input=text,
        text=True,
        check=True,
    )


def _snapshot_clipboard():
    """Capture one representative MIME payload, including images and text."""
    types_result = subprocess.run(
        ["wl-paste", "--list-types"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if types_result.returncode != 0:
        return None
    offered = types_result.stdout.decode("utf-8", errors="replace").splitlines()
    if not offered:
        return None
    mime_type = next(
        (mime for mime in TEXT_MIME_TYPES if mime in offered),
        offered[0],
    )
    payload_result = subprocess.run(
        ["wl-paste", "--no-newline", "--type", mime_type],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if payload_result.returncode != 0:
        return None
    return mime_type, payload_result.stdout


def _clipboard_contains_text(text):
    result = subprocess.run(
        ["wl-paste", "--no-newline", "--type", "text/plain;charset=utf-8"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0 and result.stdout == text.encode("utf-8")


def _restore_clipboard(snapshot):
    if snapshot is None:
        subprocess.run(["wl-copy", "--clear"], check=True)
        return
    mime_type, payload = snapshot
    subprocess.run(
        ["wl-copy", "--type", mime_type],
        input=payload,
        check=True,
    )


def _restore_clipboard_if_unchanged(snapshot, inserted_text):
    # Do not overwrite something the user copied while STT was finishing.
    if _clipboard_contains_text(inserted_text):
        _restore_clipboard(snapshot)


def type_text(text):
    """Paste Unicode text and restore the previous Wayland clipboard value."""
    if not text:
        return
    _require_command("wl-copy", "wl-clipboard")
    _require_command("wl-paste", "wl-clipboard")
    _require_command("ydotool", "ydotool ydotoold")

    previous_clipboard = _snapshot_clipboard()
    _set_clipboard_text(text)
    try:
        subprocess.run(
            ["ydotool", "key", "--key-delay", "100", *PASTE_KEYS],
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        _restore_clipboard_if_unchanged(previous_clipboard, text)
        raise RuntimeError(
            "ydotool could not inject Shift+Insert. Make sure ydotoold is running "
            "and can access /dev/uinput."
        ) from exc
    time.sleep(CLIPBOARD_RESTORE_DELAY)
    _restore_clipboard_if_unchanged(previous_clipboard, text)


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


def _grab_with_passthrough(keyboard):
    """Grab a keyboard and expose a virtual clone for non-PTT events."""
    try:
        passthrough = evdev.UInput.from_device(
            keyboard,
            name=f"{keyboard.name} (voice-input passthrough)",
        )
    except (OSError, PermissionError) as exc:
        raise RuntimeError(
            "Cannot create a virtual keyboard through /dev/uinput. "
            "Make sure the current user has read/write access to /dev/uinput."
        ) from exc

    try:
        keyboard.grab()
    except (OSError, PermissionError) as exc:
        passthrough.close()
        raise RuntimeError(
            f"Cannot exclusively grab {keyboard.path}. Another input remapper "
            "may already own the device."
        ) from exc
    return passthrough


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
    passthrough = _grab_with_passthrough(keyboard)
    print(f"Keyboard: {keyboard.name} ({keyboard.path})")
    print(
        f"Push-to-talk: {key_name} ({key_code}). "
        "The PTT key is suppressed; all other keyboard events pass through. "
        "Ctrl+C to exit.\n"
    )

    down = False
    try:
        for event in keyboard.read_loop():
            if event.type != ecodes.EV_KEY or event.code != key_code:
                passthrough.write_event(event)
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
        keyboard.ungrab()
        passthrough.close()
        keyboard.close()
        print("Done.")
