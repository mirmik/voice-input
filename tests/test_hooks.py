import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from voice_input.hooks import RecordingHooks


class HookTests(unittest.TestCase):
    def test_real_commands_receive_lifecycle_and_literal_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / 'events.jsonl'
            code = ("import json,os,sys; "
                    "open(sys.argv[1], 'a').write(json.dumps([os.environ[k] for k in "
                    "('VOICE_INPUT_EVENT','VOICE_INPUT_SESSION_ID','VOICE_INPUT_REASON')] "
                    "+ [sys.argv[2]])+'\\n')")
            command = [sys.executable, '-c', code, str(log), 'literal $(echo unsafe); *']
            hooks = RecordingHooks({'recording_start': command, 'recording_stop': command,
                                    'timeout_seconds': 3})
            hooks.start('session-one')
            hooks.start('duplicate')
            hooks.stop()
            hooks.stop()
            hooks.start('session-two')
            hooks.close()
            rows = [json.loads(line) for line in log.read_text().splitlines()]
            self.assertEqual([row[:3] for row in rows], [
                ['recording_start', 'session-one', ''],
                ['recording_stop', 'session-one', 'released'],
                ['recording_start', 'session-two', ''],
                ['recording_stop', 'session-two', 'closed'],
            ])
            self.assertTrue(all(row[3] == command[-1] for row in rows))

    def test_heartbeat_is_ordered_before_stop_and_never_renews_finished_session(self):
        hooks = RecordingHooks({'recording_heartbeat': ['unused'],
                                'heartbeat_interval_seconds': .01})
        entered, release = threading.Event(), threading.Event()
        rows = []
        def run(event, session, reason=''):
            rows.append((event, session))
            if event == 'recording_heartbeat':
                entered.set()
                release.wait(2)
        with patch.object(hooks, '_run', side_effect=run):
            hooks.start('one')
            self.assertTrue(entered.wait(2))
            stopped = threading.Event()
            thread = threading.Thread(target=lambda: (hooks.stop(), stopped.set()))
            thread.start()
            self.assertFalse(stopped.wait(.02))
            release.set()
            thread.join(2)
            self.assertTrue(stopped.is_set())
            self.assertEqual(rows[-1], ('recording_stop', 'one'))
            count = len(rows)
            time.sleep(.03)
            self.assertEqual(len(rows), count)

    def test_command_failures_do_not_break_lifecycle(self):
        for error in [FileNotFoundError(), subprocess.TimeoutExpired('private', .1),
                      subprocess.CalledProcessError(1, 'private')]:
            with self.subTest(error=type(error).__name__):
                hooks = RecordingHooks({'recording_start': ['private'],
                                        'recording_stop': ['private']})
                with patch('voice_input.hooks.subprocess.run', side_effect=error), patch('builtins.print') as log:
                    hooks.start('id')
                    hooks.stop()
                self.assertIsNone(hooks.session_id)
                self.assertEqual(log.call_count, 2)
                self.assertNotIn('private', str(log.call_args_list))

    def test_hung_command_is_killed_at_timeout(self):
        hooks = RecordingHooks({'recording_start': [sys.executable, '-c', 'import time; time.sleep(30)'],
                                'timeout_seconds': .1})
        begun = time.monotonic()
        hooks.start('id')
        hooks.stop()
        self.assertLess(time.monotonic() - begun, 2)

    def test_disabled_hooks_do_not_spawn_processes(self):
        with patch('voice_input.hooks.subprocess.run') as run:
            hooks = RecordingHooks()
            hooks.start('id')
            hooks.close()
            run.assert_not_called()
            self.assertIsNone(hooks.worker)

    def test_rejects_shell_strings_unknown_events_and_invalid_timing(self):
        for config in [[], {'recording_start': 'echo nope'}, {'recording_start': ['']},
                       {'recording_started': ['echo']}, {'timeout_seconds': float('nan')},
                       {'timeout_seconds': True}, {'heartbeat_interval_seconds': 0}]:
            with self.subTest(config=config), self.assertRaises(ValueError):
                RecordingHooks(config)
