import unittest

import numpy as np

from voice_input.vad import SAMPLE_RATE, FRAME_SAMPLES, Segmenter, SileroVAD


class FakeVAD:
    def reset(self):
        pass

    def __call__(self, frame):
        return 0.9 if np.max(frame) > 0 else 0.01


class SegmenterTests(unittest.TestCase):
    def split(self, audio, sizes=(713, 125, 2048)):
        output = []
        segmenter = Segmenter(FakeVAD(), output.append)
        pos = 0
        index = 0
        while pos < len(audio):
            n = sizes[index % len(sizes)]
            segmenter.feed(audio[pos:pos+n])
            pos += n
            index += 1
        segmenter.finish()
        np.testing.assert_array_equal(np.concatenate(output), audio)
        self.assertTrue(all(len(part) <= 24 * SAMPLE_RATE for part in output))
        return output

    def test_continuous_speech_is_bounded_and_no_samples_lost(self):
        audio = np.ones(73 * SAMPLE_RATE + 117, dtype=np.float32)
        parts = self.split(audio)
        self.assertEqual([len(p) for p in parts[:3]], [24 * SAMPLE_RATE] * 3)

    def test_pause_splits_before_limit(self):
        audio = np.concatenate((np.ones(16 * SAMPLE_RATE), np.zeros(SAMPLE_RATE),
                                np.ones(10 * SAMPLE_RATE))).astype(np.float32)
        parts = self.split(audio)
        self.assertEqual(len(parts), 2)
        self.assertTrue(16 * SAMPLE_RATE < len(parts[0]) < 17 * SAMPLE_RATE)

    def test_short_tail_is_preserved(self):
        self.split(np.ones(24 * SAMPLE_RATE + 3, dtype=np.float32))

    def test_silence_is_not_discarded_by_segmentation(self):
        self.split(np.zeros(40 * SAMPLE_RATE, dtype=np.float32))

    def test_bundled_model_runs_offline_and_resets(self):
        try:
            import onnxruntime  # noqa: F401
        except ImportError:
            self.skipTest('onnxruntime is not installed')
        vad = SileroVAD()
        frame = np.zeros(FRAME_SAMPLES, dtype=np.float32)
        first = vad(frame)
        self.assertLess(first, 0.35)
        vad(frame)
        vad.reset()
        self.assertAlmostEqual(vad(frame), first, places=6)
