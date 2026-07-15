#!/usr/bin/env python3
"""
LT - Local Text
Peer-to-peer chat over LAN.

Usage:
  lt            Connect and chat
  lt --setup    Configure peer IP and port
  lt --help     Show help
"""

import argparse
import json
import os
import socket
import sys
import threading
import time
from datetime import datetime

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit import print_formatted_text as pprint

CONFIG_DIR = os.path.expanduser("~/.config/lt")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return None


def save_config(config):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def setup():
    print()
    print("[ LT Setup ]")
    print()
    peer_ip = input("Peer IP: ").strip()
    port_str = input("Port (Enter for 5050): ").strip()
    port = int(port_str) if port_str else 5050
    save_config({"peer_ip": peer_ip, "port": port})
    print(f"\nSaved to {CONFIG_FILE}")
    print("Run 'lt' to connect.")
    print()


def timestamp():
    return datetime.now().strftime("%H:%M")


def pack_msg(text):
    return json.dumps({"t": "m", "d": text, "s": timestamp()}) + "\n"


class Connection:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.sock = None
        self.lock = threading.Lock()

    def connect_or_listen(self):
        result = {"sock": None}
        rlock = threading.Lock()

        def try_connect():
            for i in range(15):
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(2)
                    s.connect((self.host, self.port))
                    s.settimeout(None)
                    with rlock:
                        if result["sock"] is None:
                            result["sock"] = s
                            return
                    s.close()
                except (ConnectionRefusedError, socket.timeout, OSError):
                    time.sleep(1)

        def try_listen():
            try:
                server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                server.bind(("0.0.0.0", self.port))
                server.listen(1)
                server.settimeout(2)
                for _ in range(20):
                    with rlock:
                        if result["sock"] is not None:
                            server.close()
                            return
                    try:
                        conn, addr = server.accept()
                        with rlock:
                            if result["sock"] is None:
                                result["sock"] = conn
                            else:
                                conn.close()
                        server.close()
                        return
                    except socket.timeout:
                        continue
                server.close()
            except OSError:
                pass

        ct = threading.Thread(target=try_connect, daemon=True)
        cl = threading.Thread(target=try_listen, daemon=True)
        ct.start()
        cl.start()
        ct.join()
        cl.join()

        self.sock = result["sock"]
        return self.sock

    def reconnect(self, stop):
        while not stop.is_set():
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(3)
                s.connect((self.host, self.port))
                s.settimeout(None)
                with self.lock:
                    old = self.sock
                    self.sock = s
                    if old:
                        try:
                            old.close()
                        except:
                            pass
                return True
            except (ConnectionRefusedError, socket.timeout, OSError):
                time.sleep(2)
        return False

    def send(self, data):
        with self.lock:
            if self.sock:
                try:
                    self.sock.sendall(data.encode())
                    return True
                except:
                    return False
        return False

    def close(self):
        with self.lock:
            if self.sock:
                try:
                    self.sock.close()
                except:
                    pass
                self.sock = None


def chat(conn, host, port):
    stop = threading.Event()
    session = PromptSession()

    def recv_worker():
        buf = ""
        while not stop.is_set():
            sock = None
            with conn.lock:
                sock = conn.sock
            if not sock:
                time.sleep(0.1)
                continue
            try:
                data = sock.recv(4096)
                if not data:
                    raise ConnectionResetError()
                buf += data.decode()
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line)
                        if msg.get("t") == "m":
                            text = msg.get("d", "")
                            if text == "__ping__":
                                conn.send(json.dumps({
                                    "t": "m", "d": "__pong__", "s": timestamp()
                                }) + "\n")
                            elif text == "__pong__":
                                pass
                            else:
                                pprint(HTML(
                                    "<ansigreen>Peer</ansigreen> "
                                    "<ansigray>({})</ansigray>: {}"
                                ).format(msg.get("s", ""), text))
                    except json.JSONDecodeError:
                        pass
            except (ConnectionResetError, BrokenPipeError, OSError):
                if stop.is_set():
                    break
                pprint(HTML("<ansired>\nReconnecting...</ansired>"))
                if conn.reconnect(stop):
                    pprint(HTML("<ansigreen>Connected.</ansigreen>"))
                    buf = ""
                else:
                    break
        stop.set()

    t = threading.Thread(target=recv_worker, daemon=True)
    t.start()

    print()
    pprint(HTML("<ansicyan>Connected! Type /help for commands, /exit to quit</ansicyan>"))
    print()

    try:
        while not stop.is_set():
            try:
                with patch_stdout():
                    user_input = session.prompt("You: ")
            except (EOFError, KeyboardInterrupt):
                break

            if not user_input.strip():
                continue

            cmd = user_input.strip()
            cmd_lower = cmd.lower()

            if cmd_lower == "/exit":
                break
            elif cmd_lower == "/clear":
                os.system("clear" if os.name == "posix" else "cls")
            elif cmd_lower == "/ping":
                ts = time.time()
                conn.send(json.dumps({
                    "t": "m", "d": "__ping__", "s": timestamp()
                }) + "\n")
                pprint(HTML("<ansiyellow>pong</ansiyellow>"))
            elif cmd_lower == "/time":
                pprint(HTML(
                    "<ansiyellow>{}</ansiyellow>"
                ).format(datetime.now().strftime("%H:%M:%S")))
            elif cmd_lower == "/help":
                pprint(HTML(
                    "<ansiyellow>/exit</ansiyellow>  Quit\n"
                    "<ansiyellow>/clear</ansiyellow> Clear screen\n"
                    "<ansiyellow>/ping</ansiyellow>  Check connection\n"
                    "<ansiyellow>/time</ansiyellow>  Show current time\n"
                    "<ansiyellow>/help</ansiyellow>  Show this help"
                ))
            elif cmd_lower.startswith("/"):
                pprint(HTML("<ansired>Unknown command: {}</ansired>").format(cmd))
            else:
                if conn.send(pack_msg(cmd)):
                    pprint(HTML(
                        "<ansiblue>You</ansiblue> "
                        "<ansigray>({})</ansigray>: {}"
                    ).format(timestamp(), cmd))
                else:
                    pprint(HTML("<ansired>Not connected</ansired>"))
    finally:
        stop.set()
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        prog="lt",
        description="LT - Local Text. Peer-to-peer chat over LAN.",
    )
    parser.add_argument("--setup", action="store_true", help="Configure peer IP and port")
    parser.add_argument("--daemon", action="store_true", help="Run as background daemon")
    args = parser.parse_args()

    if args.setup:
        setup()
        return

    if args.daemon:
        print("Daemon mode coming in Phase 2")
        return

    config = load_config()
    if not config:
        print("Not configured. Run: lt --setup")
        sys.exit(1)

    host = config["peer_ip"]
    port = config.get("port", 5050)

    print(f"Connecting to {host}:{port}...")
    conn = Connection(host, port)
    sock = conn.connect_or_listen()

    if sock:
        chat(conn, host, port)
    else:
        print("Could not connect. Make sure the peer is running 'lt' too.")
        sys.exit(1)


if __name__ == "__main__":
    main()
