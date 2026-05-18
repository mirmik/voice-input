#!/usr/bin/env python3
"""Test Windows low-level keyboard hook for Right Alt -> F13 remapping.

Usage:
    python tools/win_ralt_f13_hook.py --log
    python tools/win_ralt_f13_hook.py --remap

Press Esc to exit.
"""

import argparse
import ctypes
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

VK_ESCAPE = 0x1B
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_RMENU = 0xA5
VK_F13 = 0x7C

LLKHF_EXTENDED = 0x01
LLKHF_INJECTED = 0x10
LLKHF_ALTDOWN = 0x20

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002


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


INPUT_UNION_FIELD = "u"


class INPUT(ctypes.Structure):
    _anonymous_ = (INPUT_UNION_FIELD,)
    _fields_ = (("type", wintypes.DWORD), (INPUT_UNION_FIELD, INPUT_UNION))


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
user32.PostQuitMessage.argtypes = (ctypes.c_int,)
user32.PostQuitMessage.restype = None
user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT
kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GetCurrentThreadId.argtypes = ()
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
kernel32.SetConsoleCtrlHandler.argtypes = (wintypes.HANDLE, wintypes.BOOL)
kernel32.SetConsoleCtrlHandler.restype = wintypes.BOOL
user32.PostThreadMessageW.argtypes = (
    wintypes.DWORD,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
)
user32.PostThreadMessageW.restype = wintypes.BOOL


NAMES = {
    VK_ESCAPE: "Esc",
    VK_LCONTROL: "LCtrl",
    VK_RCONTROL: "RCtrl",
    VK_RMENU: "RAlt",
    VK_F13: "F13",
}


def event_name(wparam):
    return {
        WM_KEYDOWN: "down",
        WM_KEYUP: "up",
        WM_SYSKEYDOWN: "sys-down",
        WM_SYSKEYUP: "sys-up",
    }.get(int(wparam), hex(int(wparam)))


def flag_text(flags):
    names = []
    if flags & LLKHF_EXTENDED:
        names.append("extended")
    if flags & LLKHF_INJECTED:
        names.append("injected")
    if flags & LLKHF_ALTDOWN:
        names.append("alt-down")
    return "|".join(names) or "-"


def send_f13(down):
    event = INPUT()
    event.type = INPUT_KEYBOARD
    event.ki = KEYBDINPUT(
        wVk=VK_F13,
        wScan=0,
        dwFlags=0 if down else KEYEVENTF_KEYUP,
        time=0,
        dwExtraInfo=0,
    )
    sent = user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))
    if sent != 1:
        raise ctypes.WinError(ctypes.get_last_error())


def install_hook(remap):
    hook_ref = {"handle": None}

    @LowLevelKeyboardProc
    def callback(n_code, w_param, l_param):
        if n_code == HC_ACTION:
            event = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            vk = int(event.vkCode)
            name = NAMES.get(vk, f"VK_{vk:02X}")
            action = event_name(w_param)

            if vk in (VK_RMENU, VK_LCONTROL, VK_RCONTROL, VK_F13, VK_ESCAPE):
                print(
                    f"{name:6} {action:8} scan={event.scanCode:<3} "
                    f"flags={flag_text(event.flags)}",
                    flush=True,
                )

            if vk == VK_ESCAPE and w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                user32.PostQuitMessage(0)
                return 1

            if remap and vk == VK_RMENU:
                if not (event.flags & LLKHF_INJECTED):
                    if w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                        send_f13(True)
                    elif w_param in (WM_KEYUP, WM_SYSKEYUP):
                        send_f13(False)
                return 1

        return user32.CallNextHookEx(hook_ref["handle"], n_code, w_param, l_param)

    module = kernel32.GetModuleHandleW(None)
    hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, callback, module, 0)
    if not hook:
        raise ctypes.WinError(ctypes.get_last_error())
    hook_ref["handle"] = hook
    return hook, callback


def run(remap):
    hook, callback = install_hook(remap)
    thread_id = kernel32.GetCurrentThreadId()
    quit_once = threading.Event()

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)
    def ctrl_handler(ctrl_type):
        if not quit_once.is_set():
            quit_once.set()
            print("\nInterrupted.", flush=True)
            user32.PostThreadMessageW(thread_id, WM_QUIT, 0, 0)
        return True

    if not kernel32.SetConsoleCtrlHandler(ctrl_handler, True):
        raise ctypes.WinError(ctypes.get_last_error())

    mode = "remap Right Alt to F13" if remap else "log only"
    print(f"Hook installed ({mode}). Press Right Alt to test, Ctrl+C or Esc to exit.")
    print("Open a browser/editor and watch whether Alt opens menus.")
    msg = wintypes.MSG()
    try:
        while True:
            result = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if result in (0, -1):
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        # Keep callback alive until after the hook is removed.
        _ = callback, ctrl_handler
        kernel32.SetConsoleCtrlHandler(ctrl_handler, False)
        user32.UnhookWindowsHookEx(hook)
        print("Hook removed.")


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--log", action="store_true", help="Only print relevant key events")
    group.add_argument("--remap", action="store_true", help="Suppress Right Alt and emit F13")
    args = parser.parse_args()
    run(remap=args.remap)


if __name__ == "__main__":
    main()
