import subprocess
import unittest
from unittest.mock import call, patch

from voice_input import platform_wayland


class WaylandTextInsertionTests(unittest.TestCase):
    @patch("voice_input.platform_wayland.shutil.which", return_value="/usr/bin/tool")
    @patch("voice_input.platform_wayland.subprocess.run")
    def test_unicode_is_copied_then_pasted(self, run, _which):
        platform_wayland.type_text("Привет")

        self.assertEqual(
            run.call_args_list,
            [
                call(
                    ["wl-copy", "--type", "text/plain;charset=utf-8"],
                    input="Привет",
                    text=True,
                    check=True,
                ),
                call(
                    [
                        "ydotool",
                        "key",
                        "29:1",
                        "47:1",
                        "47:0",
                        "29:0",
                    ],
                    check=True,
                ),
            ],
        )

    @patch("voice_input.platform_wayland.shutil.which", return_value="/usr/bin/tool")
    @patch(
        "voice_input.platform_wayland.subprocess.run",
        side_effect=[
            None,
            subprocess.CalledProcessError(1, ["ydotool"]),
        ],
    )
    def test_ydotool_failure_has_actionable_message(self, _run, _which):
        with self.assertRaisesRegex(RuntimeError, "ydotoold"):
            platform_wayland.type_text("text")


if __name__ == "__main__":
    unittest.main()
