import subprocess
import unittest
from unittest.mock import call, patch

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


if __name__ == "__main__":
    unittest.main()
