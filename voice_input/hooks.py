"""Optional external commands for the recording lifecycle; no audio is exposed."""

import math
import os
import subprocess
import threading


EVENTS = ('recording_start', 'recording_heartbeat', 'recording_stop')


class RecordingHooks:
    def __init__(self, config=None):
        config = {} if config is None else config
        if not isinstance(config, dict):
            raise ValueError('hooks must be an object')
        unknown = set(config) - set(EVENTS) - {'timeout_seconds', 'heartbeat_interval_seconds'}
        if unknown:
            raise ValueError('Unknown hooks settings: ' + ', '.join(sorted(unknown)))
        self.commands = {}
        for event in EVENTS:
            command = config.get(event, [])
            if not isinstance(command, list) or any(not isinstance(arg, str) or not arg or '\0' in arg
                                                    for arg in command):
                raise ValueError(f'hooks.{event} must be an argv array of nonempty strings')
            self.commands[event] = list(command)
        self.timeout = self._seconds(config.get('timeout_seconds', .5), 'timeout_seconds')
        self.interval = self._seconds(config.get('heartbeat_interval_seconds', 2.),
                                      'heartbeat_interval_seconds')
        self.lock = threading.Lock()
        self.session_id = None
        self.stop_event = None
        self.worker = None

    @staticmethod
    def _seconds(value, name):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f'hooks.{name} must be a positive finite number')
        return float(value)

    def _run(self, event, session_id, reason=''):
        command = self.commands[event]
        if not command:
            return
        env = dict(os.environ, VOICE_INPUT_EVENT=event,
                   VOICE_INPUT_SESSION_ID=session_id, VOICE_INPUT_REASON=reason)
        try:
            subprocess.run(command, env=env, shell=False, check=True, timeout=self.timeout,
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError) as exc:
            # No command arguments/output: handlers may contain private settings.
            print(f'  Hook {event} failed ({type(exc).__name__}); dictation continues.', flush=True)

    def start(self, session_id):
        with self.lock:
            if self.session_id is not None:
                return
            self.session_id = session_id
            self.stop_event = threading.Event()
            self._run('recording_start', session_id)
            if self.commands['recording_heartbeat']:
                self.worker = threading.Thread(target=self._heartbeat,
                                               args=(session_id, self.stop_event), daemon=True)
                self.worker.start()

    def _heartbeat(self, session_id, stop_event):
        while not stop_event.wait(self.interval):
            with self.lock:
                if self.session_id != session_id or stop_event.is_set():
                    return
                self._run('recording_heartbeat', session_id)

    def stop(self, reason='released'):
        with self.lock:
            if self.session_id is None:
                return
            session_id = self.session_id
            self.session_id = None
            self.stop_event.set()
            self._run('recording_stop', session_id, reason)
            worker, self.worker = self.worker, None
        if worker is not None:
            worker.join()

    def close(self):
        self.stop('closed')
