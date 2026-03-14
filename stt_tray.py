#!/usr/bin/python3
"""
System tray indicator for STT (voice_input.py).
Toggle Whisper model loading/unloading from tray.

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
VOICE_SCRIPT = os.path.join(SCRIPT_DIR, "voice_input.py")
PYTHON = os.path.expanduser("~/.pyenv/versions/3.10.19/bin/python3")

ICON_OFF = "audio-input-microphone-muted"
ICON_ON = "audio-input-microphone"


class STTTray:
    def __init__(self):
        self.process = None

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
        if self.process is None:
            self.start_stt()
        else:
            self.stop_stt()

    def start_stt(self):
        try:
            self.process = subprocess.Popen(
                [PYTHON, VOICE_SCRIPT],
                preexec_fn=os.setsid,
            )
            self.indicator.set_icon_full(ICON_ON, "STT Active")
            self.toggle_item.set_label("Stop STT")
            # Monitor process exit
            GLib.timeout_add(1000, self.check_process)
        except Exception as e:
            print(f"Failed to start: {e}")

    def stop_stt(self):
        if self.process:
            try:
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
            self.process.wait()
            self.process = None
        self.indicator.set_icon_full(ICON_OFF, "STT Inactive")
        self.toggle_item.set_label("Start STT")

    def check_process(self):
        if self.process and self.process.poll() is not None:
            # Process died on its own
            self.process = None
            self.indicator.set_icon_full(ICON_OFF, "STT Inactive")
            self.toggle_item.set_label("Start STT")
            return False  # stop checking
        return self.process is not None  # keep checking if running

    def on_quit(self, _):
        self.stop_stt()
        Gtk.main_quit()


def main():
    signal.signal(signal.SIGINT, signal.SIG_DFL)  # allow Ctrl+C
    STTTray()
    Gtk.main()


if __name__ == "__main__":
    main()
