"""Small settings window for the tray application."""

import threading
import tkinter as tk
from tkinter import messagebox, ttk

import nemor_link as nl

from voice_input.settings import (
    build_nemor_config,
    client_defaults,
    load_tool_config,
    normalize_server_url,
    save_tool_config,
    stt_settings,
)


_window_lock = threading.Lock()
_window_open = False


def open_settings_window(on_saved=None, client_running=None):
    """Open the settings window in its own Tk thread."""
    global _window_open
    with _window_lock:
        if _window_open:
            return
        _window_open = True

    def run():
        try:
            _show_settings_window(on_saved=on_saved, client_running=client_running)
        finally:
            global _window_open
            with _window_lock:
                _window_open = False

    threading.Thread(target=run, daemon=True, name="settings-window").start()


def _show_settings_window(on_saved=None, client_running=None):
    cfg = load_tool_config()
    stt = stt_settings(cfg)
    defaults = client_defaults(cfg)

    root = tk.Tk()
    root.title("Voice Input Settings")
    root.resizable(False, False)
    root.columnconfigure(0, weight=1)

    frame = ttk.Frame(root, padding=14)
    frame.grid(row=0, column=0, sticky="nsew")
    frame.columnconfigure(1, weight=1)

    server_var = tk.StringVar(value=stt["server_url"])
    profile_var = tk.StringVar(value=stt["profile"])
    sample_rate_var = tk.StringVar(value=str(defaults["sample_rate"]))
    python_var = tk.StringVar(value=cfg.get("PYTHON") or "")
    health_var = tk.StringVar(value="" if defaults["health_timeout"] is None else str(defaults["health_timeout"]))
    platform_var = tk.StringVar(value=defaults["platform"] or "auto")
    monitor_var = tk.BooleanVar(value=defaults["monitor"])
    fingerprint_var = tk.StringVar(value=stt["tls_fingerprint"])
    token_var = tk.StringVar(value=stt["token"])
    host_id_var = tk.StringVar(value=stt["host_id"])
    restart_var = tk.BooleanVar(value=True)
    status_var = tk.StringVar(value="")

    row = 0
    ttk.Label(frame, text="STT server URL").grid(row=row, column=0, sticky="w", pady=4)
    ttk.Entry(frame, textvariable=server_var, width=44).grid(row=row, column=1, sticky="ew", pady=4)
    row += 1

    ttk.Label(frame, text="STT profile").grid(row=row, column=0, sticky="w", pady=4)
    ttk.Entry(frame, textvariable=profile_var).grid(row=row, column=1, sticky="ew", pady=4)
    row += 1

    ttk.Label(frame, text="Sample rate").grid(row=row, column=0, sticky="w", pady=4)
    ttk.Entry(frame, textvariable=sample_rate_var).grid(row=row, column=1, sticky="ew", pady=4)
    row += 1

    ttk.Label(frame, text="Python command").grid(row=row, column=0, sticky="w", pady=4)
    ttk.Entry(frame, textvariable=python_var).grid(row=row, column=1, sticky="ew", pady=4)
    row += 1

    ttk.Label(frame, text="Health timeout").grid(row=row, column=0, sticky="w", pady=4)
    ttk.Entry(frame, textvariable=health_var).grid(row=row, column=1, sticky="ew", pady=4)
    row += 1

    ttk.Label(frame, text="Platform").grid(row=row, column=0, sticky="w", pady=4)
    ttk.Combobox(
        frame,
        textvariable=platform_var,
        values=("auto", "win", "x11"),
        state="readonly",
    ).grid(row=row, column=1, sticky="ew", pady=4)
    row += 1

    ttk.Label(frame, text="TLS fingerprint").grid(row=row, column=0, sticky="w", pady=4)
    ttk.Entry(frame, textvariable=fingerprint_var).grid(row=row, column=1, sticky="ew", pady=4)
    row += 1

    ttk.Label(frame, text="Bearer token").grid(row=row, column=0, sticky="w", pady=4)
    ttk.Entry(frame, textvariable=token_var, show="*").grid(row=row, column=1, sticky="ew", pady=4)
    row += 1

    ttk.Label(frame, text="Host ID").grid(row=row, column=0, sticky="w", pady=4)
    ttk.Entry(frame, textvariable=host_id_var).grid(row=row, column=1, sticky="ew", pady=4)
    row += 1

    ttk.Checkbutton(frame, text="Monitor backend health", variable=monitor_var).grid(
        row=row, column=0, columnspan=2, sticky="w", pady=(8, 2)
    )
    row += 1

    if client_running and client_running():
        ttk.Checkbutton(
            frame,
            text="Restart running client after save",
            variable=restart_var,
        ).grid(row=row, column=0, columnspan=2, sticky="w", pady=2)
        row += 1

    status = ttk.Label(frame, textvariable=status_var)
    status.grid(row=row, column=0, columnspan=2, sticky="w", pady=(8, 2))
    row += 1

    buttons = ttk.Frame(frame)
    buttons.grid(row=row, column=0, columnspan=2, sticky="e", pady=(10, 0))

    def collect_config():
        profile = profile_var.get().strip() or "voice-input-stt"
        try:
            sample_rate = int(sample_rate_var.get().strip())
        except ValueError as exc:
            raise ValueError("Sample rate must be an integer.") from exc
        if sample_rate <= 0:
            raise ValueError("Sample rate must be greater than zero.")

        raw_health = health_var.get().strip()
        health_timeout = None
        if raw_health:
            try:
                health_timeout = float(raw_health)
            except ValueError as exc:
                raise ValueError("Health timeout must be a number.") from exc
            if health_timeout <= 0:
                raise ValueError("Health timeout must be greater than zero.")

        next_cfg = load_tool_config()
        next_cfg["version"] = 1
        next_cfg["PYTHON"] = python_var.get().strip() or next_cfg.get("PYTHON")
        next_cfg["profile"] = profile
        next_cfg["sample_rate"] = sample_rate
        next_cfg["monitor"] = bool(monitor_var.get())
        next_cfg["health_timeout"] = health_timeout
        next_cfg["platform"] = None if platform_var.get() == "auto" else platform_var.get()
        next_cfg["stt"] = {
            "server_url": normalize_server_url(server_var.get()),
            "profile": profile,
            "tls_fingerprint": fingerprint_var.get().strip(),
            "auth": {
                "token": token_var.get().strip(),
                "host_id": host_id_var.get().strip(),
            },
        }
        return next_cfg

    def save():
        try:
            next_cfg = collect_config()
            save_tool_config(next_cfg)
        except Exception as exc:
            messagebox.showerror("Voice Input Settings", str(exc), parent=root)
            return False
        status_var.set("Saved.")
        if on_saved:
            on_saved(restart_var.get())
        return True

    def save_and_close():
        if save():
            root.destroy()

    def test_connection():
        try:
            next_cfg = collect_config()
        except Exception as exc:
            messagebox.showerror("Voice Input Settings", str(exc), parent=root)
            return
        status_var.set("Testing...")
        test_button.configure(state="disabled")

        def worker():
            try:
                stt_cfg = stt_settings(next_cfg)
                client = nl.stt(name=stt_cfg["profile"], config=build_nemor_config(next_cfg))
                try:
                    results = client.pool.probe_all()
                finally:
                    client.close()
                ok = any(item[1] for item in results)
                detail = ", ".join(
                    f"{url}: {'OK' if reachable else 'FAIL'}"
                    for url, reachable, _latency in results
                )
                root.after(0, lambda: status_var.set(detail or ("OK" if ok else "FAIL")))
            except Exception as exc:
                message = str(exc)
                root.after(0, lambda: status_var.set(f"Error: {message}"))
            finally:
                root.after(0, lambda: test_button.configure(state="normal"))

        threading.Thread(target=worker, daemon=True).start()

    test_button = ttk.Button(buttons, text="Test", command=test_connection)
    test_button.grid(row=0, column=0, padx=(0, 6))
    ttk.Button(buttons, text="Save", command=save).grid(row=0, column=1, padx=(0, 6))
    ttk.Button(buttons, text="Save & Close", command=save_and_close).grid(row=0, column=2, padx=(0, 6))
    ttk.Button(buttons, text="Cancel", command=root.destroy).grid(row=0, column=3)

    root.bind("<Return>", lambda _event: save_and_close())
    root.bind("<Escape>", lambda _event: root.destroy())
    root.mainloop()
