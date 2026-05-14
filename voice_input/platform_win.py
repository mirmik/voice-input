"""Windows hotkey and text insertion backend."""

from pynput import keyboard as kb


DEFAULT_KEYS = {kb.Key.alt_r}
ALT_GR = getattr(kb.Key, "alt_gr", None)
if ALT_GR is not None:
    DEFAULT_KEYS.add(ALT_GR)


def type_text(text):
    import keyboard as kbmod
    import pyperclip

    pyperclip.copy(text)
    kbmod.press_and_release("ctrl+v")


def run_hotkey_loop(recorder, args):
    def on_press(key):
        if key in DEFAULT_KEYS:
            recorder.start()

    def on_release(key):
        if key in DEFAULT_KEYS:
            recorder.stop_async()

    print("Push-to-talk: Right Alt. Ctrl+C to exit.\n")
    listener = kb.Listener(on_press=on_press, on_release=on_release)
    listener.start()
    try:
        while listener.is_alive():
            listener.join(0.5)
    except KeyboardInterrupt:
        print("\nExiting.")
    finally:
        listener.stop()
        print("Done.")
