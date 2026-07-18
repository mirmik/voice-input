import unittest
from argparse import Namespace
from unittest.mock import patch

from voice_input import tray
from voice_input.settings import NEMOR_CONFIG_PATH


def args(**overrides):
    values = {
        "profile": None,
        "config": None,
        "sample_rate": None,
        "monitor": False,
        "health_timeout": None,
        "platform": None,
    }
    values.update(overrides)
    return Namespace(**values)


class TrayCommandTests(unittest.TestCase):
    @patch("voice_input.tray.configured_python", return_value="python3")
    @patch("voice_input.tray.ensure_runtime_configs")
    def test_nemor_mode_passes_profile_and_external_config(self, ensure, _python):
        ensure.return_value = {
            "sample_rate": 16000,
            "monitor": False,
            "health_timeout": 0.6,
            "platform": None,
            "stt": {
                "mode": "nemor-link",
                "nemor_link": {"profile": "stt-main"},
                "manual": {},
            },
        }

        command = tray.client_command(args())

        self.assertIn("stt-main", command)
        self.assertIn(NEMOR_CONFIG_PATH, command)

    @patch("voice_input.tray.configured_python", return_value="python3")
    @patch("voice_input.tray.ensure_runtime_configs")
    def test_manual_mode_does_not_pass_external_config(self, ensure, _python):
        ensure.return_value = {
            "sample_rate": 16000,
            "monitor": False,
            "health_timeout": 0.6,
            "platform": None,
            "stt": {
                "mode": "manual",
                "nemor_link": {"profile": "stt-main"},
                "manual": {"profile": "manual-stt"},
            },
        }

        command = tray.client_command(args())

        self.assertIn("manual-stt", command)
        self.assertNotIn("--config", command)


if __name__ == "__main__":
    unittest.main()
