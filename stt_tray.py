#!/usr/bin/python3
"""
System tray indicator for STT.
Manages stt_server.py (Whisper model) and stt_client.py (push-to-talk).

Run with: /usr/bin/python3 stt_tray.py
(must use system Python for GTK/AppIndicator bindings)
"""

import os
import signal
import subprocess

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('AyatanaAppIndicator3', '0.1')
from gi.repository import Gtk, AyatanaAppIndicator3, GLib

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_SCRIPT = os.path.join(SCRIPT_DIR, "stt_server.py")
CLIENT_SCRIPT = os.path.join(SCRIPT_DIR, "stt_client.py")

# Read PYTHON from config.py
_config = {}
exec(open(os.path.join(SCRIPT_DIR, "config.py")).read(), _config)
PYTHON = _config.get("PYTHON", "python3")

ICON_OFF = "audio-input-microphone-muted"
ICON_ON = "audio-input-microphone"


class STTTray:
    def __init__(self):
        self.server_proc = None
        self.client_proc = None

        self.indicator = AyatanaAppIndicator3.Indicator.new(
            "stt-indicator",
            ICON_OFF,
            AyatanaAppIndicator3.IndicatorCategory.APPLICATION_STATUS,
        )
        self.indicator.set_status(AyatanaAppIndicator3.IndicatorStatus.ACTIVE)

        self.menu = Gtk.Menu()

        self.toggle_item = Gtk.MenuItem(label="Start STT")
        self.toggle_item.connect("activate", self.on_toggle)
        self.menu.append(self.toggle_item)

        self.menu.append(Gtk.SeparatorMenuItem())

        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", self.on_quit)
        self.menu.append(quit_item)

        self.menu.show_all()
        self.indicator.set_menu(self.menu)

    def on_toggle(self, _):
        if self.server_proc is None:
            self.start_stt()
        else:
            self.stop_stt()

    def start_stt(self):
        try:
            # Start server first (loads Whisper model)
            self.server_proc = subprocess.Popen(
                [PYTHON, SERVER_SCRIPT],
                preexec_fn=os.setsid,
            )
            # Wait a moment for server to start, then launch client
            GLib.timeout_add(3000, self._start_client)
            self.indicator.set_icon_full(ICON_ON, "STT Active")
            self.toggle_item.set_label("Stop STT")
            GLib.timeout_add(1000, self.check_processes)
        except Exception as e:
            print(f"Failed to start server: {e}")

    def _start_client(self):
        try:
            self.client_proc = subprocess.Popen(
                [PYTHON, CLIENT_SCRIPT],
                preexec_fn=os.setsid,
            )
        except Exception as e:
            print(f"Failed to start client: {e}")
        return False  # don't repeat

    def stop_stt(self):
        for proc in [self.client_proc, self.server_proc]:
            if proc:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except ProcessLookupError:
                    pass
                proc.wait()
        self.client_proc = None
        self.server_proc = None
        self.indicator.set_icon_full(ICON_OFF, "STT Inactive")
        self.toggle_item.set_label("Start STT")

    def check_processes(self):
        if self.server_proc and self.server_proc.poll() is not None:
            self.stop_stt()
            return False
        return self.server_proc is not None

    def on_quit(self, _):
        self.stop_stt()
        Gtk.main_quit()


def main():
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    STTTray()
    Gtk.main()


if __name__ == "__main__":
    main()
