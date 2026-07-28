import os
import unittest
from unittest.mock import patch

from voice_input import platforms


class PlatformDetectionTests(unittest.TestCase):
    @patch("voice_input.platforms.sys.platform", "linux")
    def test_detects_wayland_session(self):
        with patch.dict(
            os.environ,
            {"XDG_SESSION_TYPE": "wayland", "WAYLAND_DISPLAY": "wayland-0"},
            clear=True,
        ):
            self.assertEqual(platforms.platform_name(), "wayland")

    @patch("voice_input.platforms.sys.platform", "linux")
    def test_detects_x11_session(self):
        with patch.dict(
            os.environ,
            {"XDG_SESSION_TYPE": "x11", "DISPLAY": ":0"},
            clear=True,
        ):
            self.assertEqual(platforms.platform_name(), "x11")


if __name__ == "__main__":
    unittest.main()
