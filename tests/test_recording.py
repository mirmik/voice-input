import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

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

    def test_inserts_during_recording_without_repeating_text_after_release(self):
        sent = threading.Event()
        self.insert.side_effect = lambda text: sent.set()
        self.recorder.start()
        self.feed(25)
        self.assertTrue(sent.wait(3))
        self.insert.assert_called_once_with('слово')
        self.assertTrue(self.recorder.active)
        self.recorder.stop_and_send()
        self.assertEqual(self.insert.call_args_list, [call('слово'), call(' слово')])
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
        self.assertEqual(self.insert.call_args_list, [call('текст'), call('текст')])
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

    def test_empty_segment_does_not_add_leading_space(self):
        self.stt.transcribe.side_effect = [{'text': ''}, {'text': 'конец'}]
        self.recorder.start()
        self.feed(25)
        self.recorder.stop_and_send()
        self.insert.assert_called_once_with('конец')

    def test_later_failure_keeps_inserted_text_without_repeating_it(self):
        self.stt.transcribe.side_effect = [{'text': 'начало'}, RuntimeError('offline')]
        self.recorder.start()
        self.feed(25)
        self.recorder.stop_and_send()
        self.insert.assert_called_once_with('начало')
        metadata = json.loads(next(Path(self.directory.name).glob('*.json')).read_text())
        self.assertEqual(metadata['inserted_segments'], 1)
        self.assertFalse(metadata['last_insertion_may_be_partial'])
        self.assertEqual(next(Path(self.directory.name).glob('*.f32')).stat().st_size,
                         25 * 16000 * 4)

    def test_partial_insertion_failure_is_recorded_and_not_retried(self):
        self.insert.side_effect = [None, RuntimeError('insertion failed')]
        self.recorder.start()
        self.feed(25)
        self.recorder.stop_and_send()
        self.assertEqual(self.insert.call_args_list, [call('слово'), call(' слово')])
        metadata = json.loads(next(Path(self.directory.name).glob('*.json')).read_text())
        self.assertEqual(metadata['inserted_segments'], 1)
        self.assertTrue(metadata['last_insertion_may_be_partial'])

    def test_stream_start_failure_does_not_leave_recording_active(self):
        with patch('voice_input.recording.sd.InputStream', side_effect=RuntimeError('no device')):
            with self.assertRaises(RuntimeError):
                self.recorder.start()
        self.recorder.wait()
        self.assertFalse(self.recorder.active)

    def test_configured_lower_threshold_sends_at_early_pause(self):
        self.recorder.close()
        self.recorder = Recorder(self.stt, 16000, self.insert, vad=FakeVAD(),
                                 recovery_dir=self.directory.name, target_seconds=5)
        inserted = threading.Event()
        self.insert.side_effect = lambda text: inserted.set()
        self.recorder.start()
        self.feed(5)
        silence = np.zeros((16000, 1), dtype=np.float32)
        self.recorder._callback(silence, len(silence), None, None)
        self.assertTrue(inserted.wait(3))
        self.assertTrue(self.recorder.active)
        duration = len(self.stt.transcribe.call_args.args[0]) / (16000 * 4)
        self.assertTrue(5 <= duration < 6)
        self.recorder.stop_and_send()

    def test_unsupported_sample_rate_is_rejected(self):
        with self.assertRaisesRegex(ValueError, '16000'):
            Recorder(self.stt, 48000, self.insert)
