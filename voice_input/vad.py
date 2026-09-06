"""Local Silero ONNX inference and bounded, pause-aware audio segmentation."""

from pathlib import Path

import numpy as np

SAMPLE_RATE = 16000
FRAME_SAMPLES = 512


class SileroVAD:
    """Silero v6.2 recurrent ONNX contract, with no PyTorch dependency."""

    def __init__(self):
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.inter_op_num_threads = 1
        options.intra_op_num_threads = 1
        self.session = ort.InferenceSession(
            str(Path(__file__).with_name('assets') / 'silero_vad.onnx'),
            sess_options=options,
            providers=['CPUExecutionProvider'],
        )
        self.reset()

    def reset(self):
        self.state = np.zeros((2, 1, 128), dtype=np.float32)
        self.context = np.zeros((1, 64), dtype=np.float32)

    def __call__(self, frame):
        audio = np.concatenate((self.context, frame.reshape(1, FRAME_SAMPLES)), axis=1)
        probability, self.state = self.session.run(None, {
            'input': audio,
            'state': self.state,
            'sr': np.array(SAMPLE_RATE, dtype=np.int64),
        })
        self.context = audio[:, -64:].copy()
        return float(probability[0, 0])


class Segmenter:
    """Keep audio intact; prefer pauses after 15s, enforce a 24s ceiling.

    No overlap or text deduplication: even repeated words remain meaningful.
    VAD controls cut positions, not deletion of low-confidence audio.
    """

    def __init__(self, vad, emit, target_seconds=15, max_seconds=24):
        self.vad = vad
        self.emit = emit
        self.target = int(target_seconds * SAMPLE_RATE)
        self.limit = int(max_seconds * SAMPLE_RATE)
        if not FRAME_SAMPLES <= self.target < self.limit:
            raise ValueError('Expected 0 < target duration < maximum duration')
        self.pending = np.empty(0, dtype=np.float32)
        self.frames = []
        self.size = 0
        self.silence = 0
        self.last_pause = 0
        self.vad.reset()

    def feed(self, audio):
        data = np.concatenate((self.pending, np.asarray(audio, dtype=np.float32).reshape(-1)))
        end = len(data) - len(data) % FRAME_SAMPLES
        for offset in range(0, end, FRAME_SAMPLES):
            self._frame(data[offset:offset + FRAME_SAMPLES])
        self.pending = data[end:].copy()

    def _frame(self, frame):
        probability = self.vad(frame)
        self.frames.append(frame.copy())
        self.size += len(frame)
        if probability < 0.35:
            self.silence += len(frame)
            if self.silence >= int(0.12 * SAMPLE_RATE):
                self.last_pause = self.size
        else:
            self.silence = 0
        if self.size >= self.target and self.silence >= int(0.3 * SAMPLE_RATE):
            self._cut(self.size)
        elif self.size >= self.limit:
            # A recent brief pause is better than cutting continuous speech.
            cut = self.last_pause if self.last_pause >= self.target else self.limit
            self._cut(min(cut, self.limit))

    def _cut(self, count):
        audio = np.concatenate(self.frames)
        self.emit(audio[:count])
        rest = audio[count:]
        self.frames = [rest] if len(rest) else []
        self.size = len(rest)
        self.last_pause = max(0, self.last_pause - count)
        self.silence = min(self.silence, self.size)

    def finish(self):
        if len(self.pending):
            self.frames.append(self.pending)
            self.size += len(self.pending)
            self.pending = np.empty(0, dtype=np.float32)
        if self.size:
            self._cut(self.size)
