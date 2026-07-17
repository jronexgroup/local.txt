#!/usr/bin/env python3
"""
LT - Local Text
Peer-to-peer chat over LAN, P2P (Internet), or Tor.

Usage:
  lt                Connect and chat (auto-detect mode)
  lt --setup        First-run setup wizard
  lt --lan          Force LAN mode
  lt --p2p          Force P2P (Internet) mode
  lt --tor          Force Tor mode
  lt --help         Show this help
"""

import argparse
import sys

from lt import config
from lt.tui import run as run_tui


def setup_wizard():
    from lt.tui import LTApp, OnboardingScreen

    class SetupApp(LTApp):
        def on_mount(self):
            self.push_screen(OnboardingScreen())

    SetupApp().run()


def main():
    parser = argparse.ArgumentParser(
        prog="lt",
        description="LT — Local Text: Chat over LAN, P2P, or Tor",
        usage="lt [--setup | --lan | --p2p | --tor]",
    )
    parser.add_argument("--setup", action="store_true", help="Run setup wizard")
    parser.add_argument("--lan", action="store_true", help="Force LAN mode")
    parser.add_argument("--p2p", action="store_true", help="Force P2P (Internet) mode")
    parser.add_argument("--tor", action="store_true", help="Force Tor mode")
    args = parser.parse_args()

    if args.setup:
        setup_wizard()
        return

    if not config.is_configured():
        print("LT is not configured. Run: lt --setup")
        sys.exit(1)

    if args.lan:
        config.save({"mode": "lan"})
    elif args.p2p:
        config.save({"mode": "p2p"})
    elif args.tor:
        config.save({"mode": "tor"})

    run_tui()


if __name__ == "__main__":
    main()
