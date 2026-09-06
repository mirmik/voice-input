"""Recording pipeline: audio callback -> local VAD -> ordered HTTP requests."""

import json
import queue
import threading
import uuid
from pathlib import Path

import numpy as np
import sounddevice as sd

from voice_input import settings
from voice_input.vad import SAMPLE_RATE, Segmenter, SileroVAD


class Recorder:
    def __init__(self, stt_client, sample_rate, type_text, vad=None, recovery_dir=None,
                 target_seconds=settings.DEFAULT_VAD_TARGET_SECONDS):
        if sample_rate != SAMPLE_RATE:
            raise ValueError('Client Silero segmentation requires sample_rate=16000')
        self.target_seconds = settings.validate_vad_target_seconds(target_seconds)
        self.stt = stt_client
        self.sample_rate = sample_rate
        self.type_text = type_text
        self.vad = vad if vad is not None else SileroVAD()
        self.recovery_dir = Path(recovery_dir or Path(settings.CONFIG_DIR) / 'pending')
        self.recovery_dir.mkdir(parents=True, exist_ok=True)
        self.stream = None
        self.active = False
        self.lock = threading.Lock()
        self.audio_queue = queue.Queue()
        self.send_queue = queue.Queue()
        self.closed = False
        self.workers = [
            threading.Thread(target=self._segment_loop, daemon=True),
            threading.Thread(target=self._send_loop, daemon=True),
        ]
        for worker in self.workers:
            worker.start()

    def start(self):
        with self.lock:
            if self.active or self.closed:
                return
            session = {'path': self.recovery_dir / (uuid.uuid4().hex + '.f32'),
                       'texts': [], 'inserted': 0, 'insertion_uncertain': False,
                       'error': None, 'samples': 0}
            # Establish recovery storage before accepting microphone input.
            session['file'] = session['path'].open('xb')
            self.audio_queue.put(('start', session))
            try:
                self.stream = sd.InputStream(
                    samplerate=self.sample_rate, channels=1, dtype='float32',
                    callback=self._callback,
                )
                self.stream.start()
            except Exception:
                if self.stream is not None:
                    self.stream.close()
                self.stream = None
                self.audio_queue.put(('end', None))
                raise
            self.active = True
            print('  Recording (local Silero VAD)...', flush=True)

    def _callback(self, indata, frames, time_, status):
        # Inference, network and disk I/O must never run in PortAudio's callback.
        self.audio_queue.put(('audio', (indata.copy().reshape(-1), str(status) if status else None)))

    def stop_async(self):
        # Stop capture before a subsequent key-down can start the next session.
        # Transcription and text insertion continue on the background worker.
        with self.lock:
            if not self.active:
                return
            try:
                self.stream.stop()
            finally:
                self.stream.close()
                self.stream = None
                self.active = False
                self.audio_queue.put(('end', None))
        print('  Recording stopped; finishing transcription.', flush=True)

    def stop_and_send(self):
        self.stop_async()
        self.wait()

    def wait(self):
        self.audio_queue.join()
        self.send_queue.join()

    def close(self):
        self.stop_async()
        self.closed = True
        self.audio_queue.put(('quit', None))
        for worker in self.workers:
            worker.join()

    def _segment_loop(self):
        session = None
        segmenter = None
        while True:
            kind, payload = self.audio_queue.get()
            try:
                if kind == 'quit':
                    self.send_queue.put((None, None))
                    return
                if kind == 'start':
                    session = payload
                    segmenter = Segmenter(
                        self.vad, lambda audio, s=session: self.send_queue.put((s, audio)),
                        target_seconds=self.target_seconds,
                    )
                elif kind == 'audio':
                    audio, status = payload
                    session['file'].write(audio.astype('<f4').tobytes())
                    session['file'].flush()
                    session['samples'] += len(audio)
                    if status:
                        session['error'] = f'Audio capture: {status}'
                    if not session['error']:
                        segmenter.feed(audio)
                elif kind == 'end':
                    session['file'].close()
                    if not session['error']:
                        segmenter.finish()
                    self.send_queue.put((session, None))
            except Exception as exc:
                if session is not None:
                    session['error'] = str(exc)
                    if kind == 'end':
                        self.send_queue.put((session, None))
                print(f'  Recording error: {exc}', flush=True)
            finally:
                self.audio_queue.task_done()

    def _send_loop(self):
        while True:
            session, audio = self.send_queue.get()
            try:
                if session is None:
                    return
                if audio is None:
                    self._finish_session(session)
                elif not session['error']:
                    # The server ignores <0.3s; pad a short final tail rather
                    # than losing the last syllable after a hard boundary.
                    if len(audio) < int(0.3 * self.sample_rate):
                        audio = np.pad(audio, (0, int(0.3 * self.sample_rate) - len(audio)))
                    print(f'  Sending segment: {len(audio) / self.sample_rate:.2f}s', flush=True)
                    result = self.stt.transcribe(audio.astype('<f4').tobytes())
                    text = (result or {}).get('text', '').strip()
                    if text:
                        session['texts'].append(text)
                        prefix = ' ' if session['inserted'] else ''
                        # An insertion adapter may fail after typing some characters.
                        session['insertion_uncertain'] = True
                        self.type_text(prefix + text)
                        session['insertion_uncertain'] = False
                        session['inserted'] += 1
                        print(f'  >>> {text}', flush=True)
            except Exception as exc:
                session['error'] = str(exc)
                if audio is None:
                    self._report_failure(session)
            finally:
                self.send_queue.task_done()

    def _finish_session(self, session):
        if session['error']:
            self._report_failure(session)
            return
        if not session['texts']:
            print('  (no speech detected)', flush=True)
        session['path'].unlink(missing_ok=True)

    def _report_failure(self, session):
        print(f"  Dictation failed: {session['error']}. Audio retained: {session['path']} "
              '(mono float32 little-endian, 16000 Hz).', flush=True)
        try:
            session['path'].with_suffix('.txt').write_text(
                '\n'.join(session['texts']), encoding='utf-8')
            session['path'].with_suffix('.json').write_text(json.dumps({
                'sample_rate': self.sample_rate,
                'error': session['error'],
                'inserted_segments': session['inserted'],
                'last_insertion_may_be_partial': session['insertion_uncertain'],
            }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        except OSError as exc:
            print(f'  Cannot save partial transcript: {exc}', flush=True)
