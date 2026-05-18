"""X11 hotkey and text insertion backend."""

import select
import subprocess
import time

from Xlib import X, XK, display


AUTOREPEAT_WINDOW = 0.030


def type_text(text):
    subprocess.run(
        ["xdotool", "type", "--clearmodifiers", "--delay", "0", "--", text],
        check=True,
    )


def run_hotkey_loop(recorder, args):
    key_name = args.key or "F13"
    d = display.Display()
    root = d.screen().root
    keysym = XK.string_to_keysym(key_name)
    if keysym == 0:
        raise SystemExit(f"Unknown keysym: {key_name!r}")
    keycode = d.keysym_to_keycode(keysym)
    if keycode == 0:
        raise SystemExit(f"No keycode maps to {key_name!r}")

    root.grab_key(keycode, X.AnyModifier, False, X.GrabModeAsync, X.GrabModeAsync)
    root.change_attributes(event_mask=X.KeyPressMask | X.KeyReleaseMask)
    d.sync()

    print(
        f"Push-to-talk bound on {key_name} (keycode {keycode}); "
        "events are suppressed from other X11 clients. Ctrl+C to exit.\n"
    )
    pending_release_at = None
    fd = d.fileno()

    try:
        while True:
            while d.pending_events():
                event = d.next_event()
                if event.type not in (X.KeyPress, X.KeyRelease):
                    continue
                if event.detail != keycode:
                    continue
                if event.type == X.KeyPress:
                    if pending_release_at is not None:
                        pending_release_at = None
                    else:
                        recorder.start()
                else:
                    pending_release_at = time.monotonic()

            if pending_release_at is not None:
                if time.monotonic() - pending_release_at >= AUTOREPEAT_WINDOW:
                    pending_release_at = None
                    recorder.stop_async()

            select.select([fd], [], [], AUTOREPEAT_WINDOW)
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        root.ungrab_key(keycode, X.AnyModifier)
        d.sync()
        d.close()
        print("Done.")
