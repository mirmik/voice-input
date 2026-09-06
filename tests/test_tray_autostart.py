import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from voice_input import settings, tray
from test_tray import args


class AutostartTests(unittest.TestCase):
    def test_preference_survives_reload_and_preserves_backend(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            settings, 'CONFIG_DIR', directory
        ), patch.object(settings, 'TOOL_CONFIG_PATH', str(Path(directory) / 'config.json')):
            self.assertFalse(tray.client_autostart_enabled())
            cfg = settings.default_tool_config()
            cfg['stt']['manual']['server_url'] = 'http://test-backend:5056'
            settings.save_tool_config(cfg)
            tray.set_client_autostart(True)
            self.assertTrue(tray.client_autostart_enabled())
            self.assertEqual(settings.load_tool_config()['stt']['manual']['server_url'],
                             'http://test-backend:5056')
            tray.set_client_autostart(False)
            self.assertFalse(tray.client_autostart_enabled())

    def test_linux_starts_client_once_only_when_enabled(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                gi = MagicMock()
                repository = MagicMock()
                glib = repository.GLib
                glib.idle_add.side_effect = lambda callback: callback()
                with patch.dict('sys.modules', {'gi': gi, 'gi.repository': repository}), \
                     patch.object(tray, 'client_autostart_enabled', return_value=enabled), \
                     patch.object(tray, 'client_command', return_value=['python', 'client']), \
                     patch.object(tray, 'client_log_path', return_value='/unused'), \
                     patch('builtins.open', MagicMock()), \
                     patch.object(tray.subprocess, 'Popen') as popen, \
                     patch.object(tray.signal, 'signal'):
                    tray._run_linux(args())
                    self.assertEqual(popen.call_count, int(enabled))
                    if enabled:
                        # GLib callbacks must not repeat the startup indefinitely.
                        self.assertIs(glib.idle_add.call_args.args[0](), False)
                        self.assertEqual(popen.call_count, 1)

    def test_windows_starts_client_once_only_when_enabled(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                pystray = MagicMock()
                icon = pystray.Icon.return_value
                icon.run.side_effect = lambda setup: setup(icon)
                with patch.dict('sys.modules', {'pystray': pystray, 'PIL': MagicMock()}), \
                     patch.object(tray, 'client_autostart_enabled', return_value=enabled), \
                     patch.object(tray, 'client_command', return_value=['python', 'client']), \
                     patch.object(tray, 'client_log_path', return_value='/unused'), \
                     patch('builtins.open', MagicMock()), \
                     patch.object(tray.subprocess, 'Popen') as popen:
                    tray._run_windows(args())
                    self.assertEqual(popen.call_count, int(enabled))
                    self.assertTrue(icon.visible)
