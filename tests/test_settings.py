import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from voice_input import settings


class SettingsTests(unittest.TestCase):
    def test_current_stt_section_wins_over_legacy_keys(self):
        raw = {
            "profile": "current-profile",
            "STT_SERVER": "http://old.example:5079",
            "TLS_FINGERPRINT": "old-fingerprint",
            "STT_TOKEN": "old-token",
            "stt": {
                "server_url": "https://new.example:9002/stt",
                "profile": "current-profile",
                "tls_fingerprint": "new-fingerprint",
                "auth": {"token": "new-token", "host_id": "new-host"},
            },
        }

        migrated = settings._legacy_overrides(raw)

        self.assertEqual(migrated["stt"], raw["stt"])

    def test_legacy_config_migrates_token(self):
        migrated = settings._legacy_overrides(
            {
                "profile": "legacy-profile",
                "STT_SERVER": "http://legacy.example:5079",
                "STT_TOKEN": "legacy-token",
            }
        )

        self.assertEqual(migrated["stt"]["server_url"], "http://legacy.example:5079")
        self.assertEqual(migrated["stt"]["profile"], "legacy-profile")
        self.assertEqual(migrated["stt"]["auth"]["token"], "legacy-token")

    def test_save_removes_obsolete_legacy_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            config = settings.default_tool_config()
            config["STT_SERVER"] = "http://old.example:5079"
            config["STT_TOKEN"] = "old-token"

            with (
                patch.object(settings, "CONFIG_DIR", directory),
                patch.object(settings, "TOOL_CONFIG_PATH", str(config_path)),
            ):
                settings.save_tool_config(config)

            saved = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertNotIn("STT_SERVER", saved)
            self.assertNotIn("STT_TOKEN", saved)


if __name__ == "__main__":
    unittest.main()
