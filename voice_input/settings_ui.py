"""Small settings window for the tray application."""

import threading
import tkinter as tk
from tkinter import messagebox, ttk

import nemor_link as nl

from voice_input.settings import (
    NEMOR_CONFIG_PATH,
    STT_MODE_MANUAL,
    STT_MODE_NEMOR_LINK,
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

    nemor_config = None
    nemor_profile_names = []
    nemor_load_error = ""
    try:
        nemor_config = nl.load_config(NEMOR_CONFIG_PATH)
        nemor_profile_names = [
            name
            for name, profile in nemor_config["profiles"].items()
            if profile.get("kind") == "stt"
        ]
    except nl.ConfigError as exc:
        nemor_load_error = str(exc)

    root = tk.Tk()
    root.title("Voice Input Settings")
    root.resizable(False, False)
    root.columnconfigure(0, weight=1)

    frame = ttk.Frame(root, padding=14)
    frame.grid(row=0, column=0, sticky="nsew")
    frame.columnconfigure(1, weight=1)

    source_var = tk.StringVar(value=stt["mode"])
    server_var = tk.StringVar(value=stt["server_url"])
    manual_profile_var = tk.StringVar(value=stt["manual_profile"])
    nemor_profile = stt["nemor_profile"]
    if not nemor_profile and nemor_config is not None:
        default_stt = nemor_config["defaults"].get("stt")
        nemor_profile = default_stt if default_stt in nemor_profile_names else ""
    if not nemor_profile and nemor_profile_names:
        nemor_profile = nemor_profile_names[0]
    nemor_profile_var = tk.StringVar(value=nemor_profile)
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
    ttk.Label(frame, text="STT source").grid(row=row, column=0, sticky="nw", pady=4)
    source_buttons = ttk.Frame(frame)
    source_buttons.grid(row=row, column=1, sticky="w", pady=4)
    ttk.Radiobutton(
        source_buttons,
        text="Nemor Link profile",
        variable=source_var,
        value=STT_MODE_NEMOR_LINK,
    ).grid(row=0, column=0, sticky="w")
    ttk.Radiobutton(
        source_buttons,
        text="Manual configuration",
        variable=source_var,
        value=STT_MODE_MANUAL,
    ).grid(row=1, column=0, sticky="w")
    row += 1

    nemor_frame = ttk.LabelFrame(frame, text="Nemor Link", padding=8)
    nemor_frame.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(4, 8))
    nemor_frame.columnconfigure(1, weight=1)
    ttk.Label(nemor_frame, text="Config").grid(row=0, column=0, sticky="w", pady=4)
    ttk.Label(nemor_frame, text=NEMOR_CONFIG_PATH).grid(row=0, column=1, sticky="w", pady=4)
    ttk.Label(nemor_frame, text="STT profile").grid(row=1, column=0, sticky="w", pady=4)
    nemor_profile_combo = ttk.Combobox(
        nemor_frame,
        textvariable=nemor_profile_var,
        values=nemor_profile_names,
        state="readonly",
        width=36,
    )
    nemor_profile_combo.grid(row=1, column=1, sticky="ew", pady=4)
    row += 1

    manual_frame = ttk.LabelFrame(frame, text="Manual STT backend", padding=8)
    manual_frame.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(4, 8))
    manual_frame.columnconfigure(1, weight=1)
    ttk.Label(manual_frame, text="Profile name").grid(row=0, column=0, sticky="w", pady=4)
    ttk.Entry(manual_frame, textvariable=manual_profile_var).grid(
        row=0, column=1, sticky="ew", pady=4
    )
    ttk.Label(manual_frame, text="Server URL").grid(row=1, column=0, sticky="w", pady=4)
    ttk.Entry(manual_frame, textvariable=server_var, width=44).grid(
        row=1, column=1, sticky="ew", pady=4
    )
    ttk.Label(manual_frame, text="TLS fingerprint").grid(row=2, column=0, sticky="w", pady=4)
    ttk.Entry(manual_frame, textvariable=fingerprint_var).grid(
        row=2, column=1, sticky="ew", pady=4
    )
    ttk.Label(manual_frame, text="Bearer token").grid(row=3, column=0, sticky="w", pady=4)
    ttk.Entry(manual_frame, textvariable=token_var, show="*").grid(
        row=3, column=1, sticky="ew", pady=4
    )
    ttk.Label(manual_frame, text="Host ID").grid(row=4, column=0, sticky="w", pady=4)
    ttk.Entry(manual_frame, textvariable=host_id_var).grid(
        row=4, column=1, sticky="ew", pady=4
    )
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
        values=("auto", "wayland", "x11", "win"),
        state="readonly",
    ).grid(row=row, column=1, sticky="ew", pady=4)
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

    def update_source_fields(*_args):
        if source_var.get() == STT_MODE_NEMOR_LINK:
            manual_frame.grid_remove()
            nemor_frame.grid()
            if nemor_load_error:
                status_var.set(f"Nemor Link config error: {nemor_load_error}")
            elif not nemor_profile_names:
                status_var.set("No STT profiles found in the Nemor Link config.")
            else:
                status_var.set("")
        else:
            nemor_frame.grid_remove()
            manual_frame.grid()
            status_var.set("")

    def collect_config():
        mode = source_var.get()
        if mode not in (STT_MODE_MANUAL, STT_MODE_NEMOR_LINK):
            raise ValueError("Select an STT source.")
        manual_profile = manual_profile_var.get().strip() or "voice-input-stt"
        nemor_profile = nemor_profile_var.get().strip()
        if mode == STT_MODE_NEMOR_LINK:
            if nemor_load_error:
                raise ValueError(f"Cannot load Nemor Link config: {nemor_load_error}")
            if not nemor_profile:
                raise ValueError("Select a Nemor Link STT profile.")
            if nemor_profile not in nemor_profile_names:
                raise ValueError(f"Unknown Nemor Link STT profile: {nemor_profile}")
        try:
            sample_rate = int(sample_rate_var.get().strip())
        except ValueError as exc:
            raise ValueError("Sample rate must be an integer.") from exc
        if sample_rate != 16000:
            raise ValueError("Client Silero segmentation requires sample rate 16000.")

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
        next_cfg["version"] = 2
        next_cfg["PYTHON"] = python_var.get().strip() or next_cfg.get("PYTHON")
        next_cfg["sample_rate"] = sample_rate
        next_cfg["monitor"] = bool(monitor_var.get())
        next_cfg["health_timeout"] = health_timeout
        next_cfg["platform"] = None if platform_var.get() == "auto" else platform_var.get()
        next_cfg["stt"] = {
            "mode": mode,
            "nemor_link": {
                "profile": nemor_profile,
            },
            "manual": {
                "server_url": normalize_server_url(server_var.get()),
                "profile": manual_profile,
                "tls_fingerprint": fingerprint_var.get().strip(),
                "auth": {
                    "token": token_var.get().strip(),
                    "host_id": host_id_var.get().strip(),
                },
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
                if stt_cfg["mode"] == STT_MODE_NEMOR_LINK:
                    test_config = nl.load_config(NEMOR_CONFIG_PATH)
                else:
                    test_config = build_nemor_config(next_cfg)
                client = nl.stt(name=stt_cfg["profile"], config=test_config)
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

    source_var.trace_add("write", update_source_fields)
    update_source_fields()
    root.bind("<Return>", lambda _event: save_and_close())
    root.bind("<Escape>", lambda _event: root.destroy())
    root.mainloop()
