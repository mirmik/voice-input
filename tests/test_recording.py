import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

from voice_input.recording import Recorder
from test_vad import FakeVAD


class RecordingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.stt = Mock()
        self.stt.transcribe.return_value = {'text': 'слово'}
        self.insert = Mock()
        self.recorder = Recorder(self.stt, 16000, self.insert, vad=FakeVAD(),
                                 recovery_dir=self.directory.name)
        self.stream_patch = patch('voice_input.recording.sd.InputStream')
        self.stream_patch.start()

    def tearDown(self):
        self.recorder.close()
        self.stream_patch.stop()
        self.directory.cleanup()

    def feed(self, seconds):
        audio = np.ones((int(seconds * 16000), 1), dtype=np.float32)
        self.recorder._callback(audio, len(audio), None, None)

    def test_sends_during_recording_and_inserts_once_after_release(self):
        sent = threading.Event()
        self.stt.transcribe.side_effect = lambda audio: (sent.set() or {'text': 'слово'})
        self.recorder.start()
        self.feed(25)
        self.assertTrue(sent.wait(3))
        self.insert.assert_not_called()
        self.recorder.stop_and_send()
        self.insert.assert_called_once_with('слово слово')
        self.assertEqual(len(list(Path(self.directory.name).iterdir())), 0)
        self.assertTrue(all(len(c.args[0]) <= 24 * 16000 * 4
                            for c in self.stt.transcribe.call_args_list))

    def test_rapid_sessions_keep_order_even_while_first_request_waits(self):
        entered = threading.Event()
        release = threading.Event()
        def transcribe(audio):
            entered.set()
            release.wait(3)
            return {'text': 'текст'}
        self.stt.transcribe.side_effect = transcribe
        self.recorder.start()
        self.feed(1)
        self.recorder.stop_async()
        self.assertTrue(entered.wait(3))
        self.recorder.start()
        self.feed(1)
        self.recorder.stop_async()
        release.set()
        self.recorder.wait()
        self.assertEqual(self.insert.call_count, 2)
        self.assertEqual(self.stt.transcribe.call_count, 2)

    def test_failed_request_retains_whole_audio_without_partial_insertion(self):
        self.stt.transcribe.side_effect = RuntimeError('offline')
        self.recorder.start()
        self.feed(26)
        self.recorder.stop_and_send()
        self.insert.assert_not_called()
        files = list(Path(self.directory.name).glob('*.f32'))
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].stat().st_size, 26 * 16000 * 4)

    def test_insertion_failure_keeps_audio_and_transcript(self):
        self.insert.side_effect = RuntimeError('clipboard failed')
        self.recorder.start()
        self.feed(1)
        self.recorder.stop_and_send()
        transcript = next(Path(self.directory.name).glob('*.txt'))
        self.assertEqual(transcript.read_text(), 'слово')
        self.assertEqual(len(list(Path(self.directory.name).glob('*.f32'))), 1)

    def test_stream_start_failure_does_not_leave_recording_active(self):
        with patch('voice_input.recording.sd.InputStream', side_effect=RuntimeError('no device')):
            with self.assertRaises(RuntimeError):
                self.recorder.start()
        self.recorder.wait()
        self.assertFalse(self.recorder.active)

    def test_unsupported_sample_rate_is_rejected(self):
        with self.assertRaisesRegex(ValueError, '16000'):
            Recorder(self.stt, 48000, self.insert)
