#!/usr/bin/python3
"""
System tray indicator for STT.
Manages stt_client.py (push-to-talk).

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
CLIENT_SCRIPT = os.path.join(SCRIPT_DIR, "stt_client.py")

# Read PYTHON from config.py
_config = {}
exec(open(os.path.join(SCRIPT_DIR, "config.py")).read(), _config)
PYTHON = _config.get("PYTHON", "python3")

ICON_OFF = "audio-input-microphone-muted"
ICON_ON = "audio-input-microphone"


class STTTray:
    def __init__(self):
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
        if self.client_proc is None:
            self.start_client()
        else:
            self.stop_client()

    def start_client(self):
        try:
            self.client_proc = subprocess.Popen(
                [PYTHON, CLIENT_SCRIPT],
                preexec_fn=os.setsid,
            )
            self.indicator.set_icon_full(ICON_ON, "STT Active")
            self.toggle_item.set_label("Stop Client")
            GLib.timeout_add(1000, self.check_processes)
        except Exception as e:
            print(f"Failed to start client: {e}")

    def stop_client(self):
        if self.client_proc:
            try:
                os.killpg(os.getpgid(self.client_proc.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
            self.client_proc.wait()
        self.client_proc = None
        self.indicator.set_icon_full(ICON_OFF, "STT Inactive")
        self.toggle_item.set_label("Start Client")

    def check_processes(self):
        if self.client_proc and self.client_proc.poll() is not None:
            self.stop_client()
            return False
        return self.client_proc is not None

    def on_quit(self, _):
        self.stop_client()
        Gtk.main_quit()


def main():
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    STTTray()
    Gtk.main()


if __name__ == "__main__":
    main()
