"""Windows hotkey and text insertion backend."""

import ctypes
import queue
import threading
from ctypes import wintypes


user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


WH_KEYBOARD_LL = 13
HC_ACTION = 0

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_QUIT = 0x0012

VK_RMENU = 0xA5

LLKHF_INJECTED = 0x10

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = (
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    )


class KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    )


class MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    )


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = (
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    )


class INPUT_UNION(ctypes.Union):
    _fields_ = (
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    )


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = (("type", wintypes.DWORD), ("u", INPUT_UNION))


LowLevelKeyboardProc = ctypes.WINFUNCTYPE(
    ctypes.c_long,
    ctypes.c_int,
    wintypes.WPARAM,
    wintypes.LPARAM,
)


user32.SetWindowsHookExW.argtypes = (
    ctypes.c_int,
    LowLevelKeyboardProc,
    wintypes.HINSTANCE,
    wintypes.DWORD,
)
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = (
    wintypes.HHOOK,
    ctypes.c_int,
    wintypes.WPARAM,
    wintypes.LPARAM,
)
user32.CallNextHookEx.restype = ctypes.c_long
user32.UnhookWindowsHookEx.argtypes = (wintypes.HHOOK,)
user32.UnhookWindowsHookEx.restype = wintypes.BOOL
user32.GetMessageW.argtypes = (
    ctypes.POINTER(wintypes.MSG),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
)
user32.GetMessageW.restype = wintypes.BOOL
user32.TranslateMessage.argtypes = (ctypes.POINTER(wintypes.MSG),)
user32.TranslateMessage.restype = wintypes.BOOL
user32.DispatchMessageW.argtypes = (ctypes.POINTER(wintypes.MSG),)
user32.DispatchMessageW.restype = ctypes.c_long
user32.PostThreadMessageW.argtypes = (
    wintypes.DWORD,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
)
user32.PostThreadMessageW.restype = wintypes.BOOL
user32.SendInput.argtypes = (
    wintypes.UINT,
    ctypes.POINTER(INPUT),
    ctypes.c_int,
)
user32.SendInput.restype = wintypes.UINT
kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GetCurrentThreadId.argtypes = ()
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
kernel32.SetConsoleCtrlHandler.argtypes = (wintypes.HANDLE, wintypes.BOOL)
kernel32.SetConsoleCtrlHandler.restype = wintypes.BOOL


def type_text(text):
    """Insert text into the focused window without touching the clipboard."""
    utf16 = text.encode("utf-16-le")
    code_units = [
        int.from_bytes(utf16[offset : offset + 2], "little")
        for offset in range(0, len(utf16), 2)
    ]
    if not code_units:
        return

    inputs = (INPUT * (len(code_units) * 2))()
    for index, code_unit in enumerate(code_units):
        key_down = inputs[index * 2]
        key_down.type = INPUT_KEYBOARD
        key_down.ki = KEYBDINPUT(
            wVk=0,
            wScan=code_unit,
            dwFlags=KEYEVENTF_UNICODE,
            time=0,
            dwExtraInfo=0,
        )

        key_up = inputs[index * 2 + 1]
        key_up.type = INPUT_KEYBOARD
        key_up.ki = KEYBDINPUT(
            wVk=0,
            wScan=code_unit,
            dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP,
            time=0,
            dwExtraInfo=0,
        )

    sent = user32.SendInput(len(inputs), inputs, ctypes.sizeof(INPUT))
    if sent != len(inputs):
        error_code = ctypes.get_last_error()
        if error_code:
            raise ctypes.WinError(error_code)
        raise OSError(
            f"SendInput inserted {sent} of {len(inputs)} keyboard events; "
            "input may be blocked by Windows integrity-level restrictions"
        )


def _install_right_alt_hook(events):
    hook_ref = {"handle": None}
    state = {"right_alt_down": False}

    @LowLevelKeyboardProc
    def callback(n_code, w_param, l_param):
        if n_code == HC_ACTION:
            event = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            if int(event.vkCode) == VK_RMENU:
                if not (event.flags & LLKHF_INJECTED):
                    if w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                        if not state["right_alt_down"]:
                            state["right_alt_down"] = True
                            events.put("down")
                    elif w_param in (WM_KEYUP, WM_SYSKEYUP):
                        if state["right_alt_down"]:
                            state["right_alt_down"] = False
                            events.put("up")
                return 1

        return user32.CallNextHookEx(hook_ref["handle"], n_code, w_param, l_param)

    module = kernel32.GetModuleHandleW(None)
    hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, callback, module, 0)
    if not hook:
        raise ctypes.WinError(ctypes.get_last_error())
    hook_ref["handle"] = hook
    return hook, callback


def run_hotkey_loop(recorder, args):
    events = queue.SimpleQueue()
    worker_done = threading.Event()

    def worker():
        try:
            while True:
                event = events.get()
                if event is None:
                    return
                if event == "down":
                    recorder.start()
                elif event == "up":
                    recorder.stop_async()
        finally:
            worker_done.set()

    worker_thread = threading.Thread(target=worker, daemon=True)
    worker_thread.start()

    hook, callback = _install_right_alt_hook(events)
    thread_id = kernel32.GetCurrentThreadId()
    quit_once = threading.Event()

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)
    def ctrl_handler(ctrl_type):
        if not quit_once.is_set():
            quit_once.set()
            user32.PostThreadMessageW(thread_id, WM_QUIT, 0, 0)
        return True

    if not kernel32.SetConsoleCtrlHandler(ctrl_handler, True):
        user32.UnhookWindowsHookEx(hook)
        raise ctypes.WinError(ctypes.get_last_error())

    print("Push-to-talk: Right Alt. Ctrl+C to exit.\n")
    msg = wintypes.MSG()
    try:
        while True:
            result = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if result in (0, -1):
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
    except KeyboardInterrupt:
        print("\nExiting.")
    finally:
        # Keep ctypes callbacks alive until after they are unregistered.
        _ = callback, ctrl_handler, args
        kernel32.SetConsoleCtrlHandler(ctrl_handler, False)
        user32.UnhookWindowsHookEx(hook)
        events.put(None)
        worker_done.wait(2.0)
        print("Done.")


if __name__ == "__main__":
    class _TestRecorder:
        def __init__(self):
            self.active = False

        def start(self):
            if self.active:
                return
            self.active = True
            print("Right Alt down: start", flush=True)

        def stop_async(self):
            if not self.active:
                return
            self.active = False
            print("Right Alt up: stop", flush=True)

    run_hotkey_loop(_TestRecorder(), None)
