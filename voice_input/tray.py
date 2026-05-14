"""Cross-platform tray entrypoint."""

import os
import signal
import subprocess
import sys

from voice_input.settings import configured_python


SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def client_command(args):
    cmd = [configured_python(), "-m", "voice_input", "client"]
    if args.profile:
        cmd += ["--profile", args.profile]
    if args.config:
        cmd += ["--config", args.config]
    if args.sample_rate:
        cmd += ["--sample-rate", str(args.sample_rate)]
    if args.monitor:
        cmd.append("--monitor")
    if args.health_timeout is not None:
        cmd += ["--health-timeout", str(args.health_timeout)]
    if args.platform:
        cmd += ["--platform", args.platform]
    return cmd


def run(args):
    if sys.platform.startswith("win"):
        return _run_windows(args)
    if sys.platform.startswith("linux"):
        return _run_linux(args)
    raise SystemExit(f"Unsupported platform: {sys.platform}")


def _run_windows(args):
    import pystray
    from PIL import Image, ImageDraw

    state = {"proc": None, "icon": None}

    def make_icon(active):
        image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        fill = (40, 150, 80, 255) if active else (120, 120, 120, 255)
        draw.rounded_rectangle((22, 10, 42, 38), radius=8, fill=fill)
        draw.rectangle((29, 38, 35, 50), fill=fill)
        draw.rectangle((22, 50, 42, 56), fill=fill)
        if not active:
            draw.line((14, 50, 50, 14), fill=(190, 40, 40, 255), width=6)
        return image

    def refresh(active):
        state["icon"].icon = make_icon(active)
        state["icon"].title = "STT Active" if active else "STT Inactive"
        state["icon"].menu = menu()

    def is_running():
        proc = state["proc"]
        return proc is not None and proc.poll() is None

    def start_client(_icon=None, _item=None):
        if is_running():
            return
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        state["proc"] = subprocess.Popen(
            client_command(args),
            creationflags=creationflags,
            cwd=SCRIPT_DIR,
        )
        refresh(True)

    def stop_client(_icon=None, _item=None):
        proc = state["proc"]
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)
        state["proc"] = None
        refresh(False)

    def quit_tray(icon, _item=None):
        stop_client()
        icon.stop()

    def menu():
        if is_running():
            toggle = pystray.MenuItem("Stop Client", stop_client)
        else:
            toggle = pystray.MenuItem("Start Client", start_client)
        return pystray.Menu(toggle, pystray.Menu.SEPARATOR, pystray.MenuItem("Quit", quit_tray))

    state["icon"] = pystray.Icon("voice-input", make_icon(False), "STT Inactive", menu())
    state["icon"].run()
    return 0


def _run_linux(args):
    import gi

    gi.require_version("Gtk", "3.0")
    gi.require_version("AyatanaAppIndicator3", "0.1")
    from gi.repository import AyatanaAppIndicator3, GLib, Gtk

    icon_off = "audio-input-microphone-muted"
    icon_on = "audio-input-microphone"
    client_proc = {"proc": None}

    indicator = AyatanaAppIndicator3.Indicator.new(
        "stt-indicator",
        icon_off,
        AyatanaAppIndicator3.IndicatorCategory.APPLICATION_STATUS,
    )
    indicator.set_status(AyatanaAppIndicator3.IndicatorStatus.ACTIVE)
    menu = Gtk.Menu()
    toggle_item = Gtk.MenuItem(label="Start Client")

    def stop_client():
        proc = client_proc["proc"]
        if proc:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
            proc.wait()
        client_proc["proc"] = None
        indicator.set_icon_full(icon_off, "STT Inactive")
        toggle_item.set_label("Start Client")

    def check_processes():
        proc = client_proc["proc"]
        if proc and proc.poll() is not None:
            stop_client()
            return False
        return client_proc["proc"] is not None

    def start_client():
        client_proc["proc"] = subprocess.Popen(
            client_command(args),
            preexec_fn=os.setsid,
            cwd=SCRIPT_DIR,
        )
        indicator.set_icon_full(icon_on, "STT Active")
        toggle_item.set_label("Stop Client")
        GLib.timeout_add(1000, check_processes)

    def on_toggle(_):
        if client_proc["proc"] is None:
            start_client()
        else:
            stop_client()

    def on_quit(_):
        stop_client()
        Gtk.main_quit()

    toggle_item.connect("activate", on_toggle)
    menu.append(toggle_item)
    menu.append(Gtk.SeparatorMenuItem())
    quit_item = Gtk.MenuItem(label="Quit")
    quit_item.connect("activate", on_quit)
    menu.append(quit_item)
    menu.show_all()
    indicator.set_menu(menu)

    signal.signal(signal.SIGINT, signal.SIG_DFL)
    Gtk.main()
    return 0
