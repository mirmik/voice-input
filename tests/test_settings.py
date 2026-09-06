import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from voice_input import settings


class SettingsTests(unittest.TestCase):
    def test_vad_target_validation_and_persistence(self):
        for value in (0, -1, 24, 25, "nan", "inf", None, True, "bad"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                settings.validate_vad_target_seconds(value)
        self.assertEqual(settings.validate_vad_target_seconds("5.5"), 5.5)
        with tempfile.TemporaryDirectory() as directory, patch.object(
            settings, "CONFIG_DIR", directory
        ), patch.object(settings, "TOOL_CONFIG_PATH", str(Path(directory) / "config.json")):
            cfg = settings.load_tool_config()
            self.assertEqual(cfg["vad_target_seconds"], 15)
            cfg["vad_target_seconds"] = 5.5
            settings.save_tool_config(cfg)
            self.assertEqual(settings.load_tool_config()["vad_target_seconds"], 5.5)

    def test_flat_stt_config_migrates_to_manual_mode(self):
        normalized = settings._normalize_stt_schema(
            {
                "stt": {
                    "server_url": "https://proxy.example:8090",
                    "profile": "old-profile",
                    "tls_fingerprint": "AA:BB",
                    "auth": {"token": "old-token", "host_id": "old-host"},
                }
            }
        )

        self.assertEqual(normalized["stt"]["mode"], settings.STT_MODE_MANUAL)
        self.assertEqual(normalized["stt"]["manual"]["profile"], "old-profile")
        self.assertEqual(
            normalized["stt"]["manual"]["server_url"],
            "https://proxy.example:8090",
        )
        self.assertEqual(normalized["stt"]["manual"]["auth"]["token"], "old-token")

    def test_manual_mode_builds_inline_nemor_profile(self):
        config = settings.default_tool_config()
        config["stt"]["manual"] = {
            "server_url": "https://proxy.example:8090/stt",
            "profile": "manual-stt",
            "tls_fingerprint": "AA:BB",
            "auth": {"token": "token", "host_id": "workstation"},
        }

        generated = settings.build_nemor_config(config)

        backend = generated["profiles"]["manual-stt"]["backends"][0]
        self.assertEqual(backend["url"], "https://proxy.example:8090/stt")
        self.assertEqual(backend["auth"], "voice-input")
        self.assertEqual(generated["hosts"]["voice-input"]["token"], "token")

    def test_nemor_link_mode_uses_external_config_and_selected_profile(self):
        config = settings.default_tool_config()
        config["stt"]["mode"] = settings.STT_MODE_NEMOR_LINK
        config["stt"]["nemor_link"]["profile"] = "stt-main"

        active = settings.stt_settings(config)
        defaults = settings.client_defaults(config)

        self.assertEqual(active["profile"], "stt-main")
        self.assertEqual(active["config"], settings.NEMOR_CONFIG_PATH)
        self.assertEqual(defaults["profile"], "stt-main")
        self.assertEqual(defaults["config"], settings.NEMOR_CONFIG_PATH)

    def test_switching_modes_preserves_both_profile_selections(self):
        config = settings.default_tool_config()
        config["stt"]["nemor_link"]["profile"] = "remote-stt"
        config["stt"]["manual"]["profile"] = "direct-stt"

        config["stt"]["mode"] = settings.STT_MODE_NEMOR_LINK
        self.assertEqual(settings.stt_settings(config)["profile"], "remote-stt")
        config["stt"]["mode"] = settings.STT_MODE_MANUAL
        self.assertEqual(settings.stt_settings(config)["profile"], "direct-stt")

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
            self.assertNotIn("profile", saved)
            self.assertEqual(saved["version"], 2)
            self.assertEqual(saved["stt"]["mode"], settings.STT_MODE_MANUAL)


if __name__ == "__main__":
    unittest.main()
