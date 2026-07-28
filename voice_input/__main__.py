"""Command line entrypoint for voice-input."""

import argparse
import sys

from voice_input import client, tray


def add_common_client_args(parser):
    parser.add_argument(
        "--profile",
        default=None,
        help="STT profile name (default: voice-input settings)",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to nemor-link config (default: generated voice-input config)",
    )
    parser.add_argument("--sample-rate", type=int, default=None)
    parser.add_argument(
        "--monitor",
        action="store_true",
        help="Enable background health-check of STT backends",
    )
    parser.add_argument(
        "--health-timeout",
        type=float,
        default=None,
        help="Health probe timeout in seconds",
    )
    parser.add_argument(
        "--platform",
        choices=("wayland", "x11", "win"),
        default=None,
        help="Override platform backend",
    )


def build_parser():
    p = argparse.ArgumentParser(prog="voice-input")
    sub = p.add_subparsers(dest="command")

    p_client = sub.add_parser("client", help="Run push-to-talk client")
    add_common_client_args(p_client)
    p_client.add_argument(
        "--key",
        default=None,
        help="X11 keysym to bind, for example F13, Alt_R, or ISO_Level3_Shift",
    )
    p_client.add_argument(
        "--keyboard",
        default=None,
        help="Wayland evdev keyboard device, for example /dev/input/event7",
    )
    p_client.add_argument(
        "--key-code",
        type=int,
        default=None,
        help="Wayland evdev PTT key code (default: configured KEY_CODE or 100)",
    )

    p_tray = sub.add_parser("tray", help="Run tray controller")
    add_common_client_args(p_tray)

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "client":
        return client.run(args)
    if args.command == "tray":
        return tray.run(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
