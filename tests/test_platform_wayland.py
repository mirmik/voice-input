import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from evdev import ecodes
from voice_input import platform_wayland


class WaylandTextInsertionTests(unittest.TestCase):
    @patch("voice_input.platform_wayland.shutil.which", return_value="/usr/bin/tool")
    @patch("voice_input.platform_wayland.time.sleep")
    @patch("voice_input.platform_wayland._restore_clipboard_if_unchanged")
    @patch("voice_input.platform_wayland._set_clipboard_text")
    @patch(
        "voice_input.platform_wayland._snapshot_clipboard",
        return_value=("text/plain", b"old text"),
    )
    @patch("voice_input.platform_wayland.subprocess.run")
    def test_unicode_is_pasted_then_clipboard_is_restored(
        self,
        run,
        snapshot,
        set_clipboard,
        restore,
        sleep,
        _which,
    ):
        platform_wayland.type_text("Привет")

        snapshot.assert_called_once_with()
        set_clipboard.assert_called_once_with("Привет")
        run.assert_called_once_with(
            [
                "ydotool",
                "key",
                "--key-delay",
                "100",
                "SHIFT+INSERT",
            ],
            check=True,
        )
        sleep.assert_called_once_with(platform_wayland.CLIPBOARD_RESTORE_DELAY)
        restore.assert_called_once_with(("text/plain", b"old text"), "Привет")

    @patch("voice_input.platform_wayland.shutil.which", return_value="/usr/bin/tool")
    @patch("voice_input.platform_wayland._restore_clipboard_if_unchanged")
    @patch("voice_input.platform_wayland._set_clipboard_text")
    @patch("voice_input.platform_wayland._snapshot_clipboard", return_value=None)
    @patch(
        "voice_input.platform_wayland.subprocess.run",
        side_effect=subprocess.CalledProcessError(1, ["ydotool"]),
    )
    def test_ydotool_failure_restores_clipboard(
        self, _run, snapshot, set_clipboard, restore, _which
    ):
        with self.assertRaisesRegex(RuntimeError, "ydotoold"):
            platform_wayland.type_text("text")
        snapshot.assert_called_once_with()
        set_clipboard.assert_called_once_with("text")
        restore.assert_called_once_with(None, "text")

    @patch("voice_input.platform_wayland._restore_clipboard")
    @patch("voice_input.platform_wayland._clipboard_contains_text")
    def test_new_user_clipboard_is_not_overwritten(self, contains, restore):
        contains.return_value = False

        platform_wayland._restore_clipboard_if_unchanged(
            ("text/plain", b"old"),
            "transcript",
        )

        restore.assert_not_called()


class WaylandHotkeyTests(unittest.TestCase):
    @patch("voice_input.platform_wayland.load_tool_config", return_value={})
    @patch("voice_input.platform_wayland._require_command")
    @patch("voice_input.platform_wayland.evdev.UInput.from_device")
    @patch("voice_input.platform_wayland._find_keyboard")
    def test_ptt_is_suppressed_and_other_events_are_forwarded(
        self,
        find_keyboard,
        from_device,
        _require_command,
        _load_config,
    ):
        ordinary_key = SimpleNamespace(
            type=ecodes.EV_KEY,
            code=ecodes.KEY_A,
            value=1,
        )
        sync = SimpleNamespace(type=ecodes.EV_SYN, code=0, value=0)
        ptt_down = SimpleNamespace(
            type=ecodes.EV_KEY,
            code=ecodes.KEY_RIGHTALT,
            value=1,
        )
        ptt_repeat = SimpleNamespace(
            type=ecodes.EV_KEY,
            code=ecodes.KEY_RIGHTALT,
            value=2,
        )
        ptt_up = SimpleNamespace(
            type=ecodes.EV_KEY,
            code=ecodes.KEY_RIGHTALT,
            value=0,
        )
        keyboard = Mock()
        keyboard.name = "Test keyboard"
        keyboard.path = "/dev/input/event7"
        keyboard.read_loop.return_value = iter(
            [ordinary_key, sync, ptt_down, ptt_repeat, ptt_up]
        )
        find_keyboard.return_value = keyboard
        passthrough = from_device.return_value
        recorder = Mock()
        args = SimpleNamespace(keyboard=None, key_code=ecodes.KEY_RIGHTALT)

        platform_wayland.run_hotkey_loop(recorder, args)

        from_device.assert_called_once_with(
            keyboard,
            name="Test keyboard (voice-input passthrough)",
        )
        keyboard.grab.assert_called_once_with()
        passthrough.write_event.assert_has_calls(
            [call(ordinary_key), call(sync)]
        )
        self.assertEqual(passthrough.write_event.call_count, 2)
        recorder.start.assert_called_once_with()
        recorder.stop_async.assert_called_once_with()
        keyboard.ungrab.assert_called_once_with()
        passthrough.close.assert_called_once_with()
        keyboard.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
