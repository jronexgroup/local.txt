#!/usr/bin/env python3
"""
LT — Local Text
Chat over LAN or Internet (P2P).

Usage:
  lt [--setup] [--lan | --p2p]
"""

import argparse
import base64
import json
import os
import platform
import random
import socket
import string
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit import print_formatted_text as pt_print
    from rich.console import Console
    from rich.progress import Progress, BarColumn, TextColumn
except ImportError:
    print("Missing dependencies. Run: pip3 install rich prompt_toolkit --break-system-packages")
    sys.exit(1)

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
except ImportError:
    print("Missing: pip3 install cryptography --break-system-packages")
    sys.exit(1)

try:
    import pyperclip
    CLIP_OK = True
except ImportError:
    CLIP_OK = False

CONFIG_DIR = Path.home() / ".config" / "lt"
CONFIG_FILE = CONFIG_DIR / "settings.json"
OFFLINE_DIR = CONFIG_DIR / "offline"

console = Console()
session = PromptSession()


# ─── Config ───────────────────────────────────────────────────────

DEFAULTS = {
    "mode": "p2p",
    "port": 5050,
    "pair_password": "",
    "display_name": platform.node() or "Device",
    "stun_server": "stun.l.google.com:19302",
    "download_dir": str(Path.home() / "Downloads" / "LT"),
    "last_code": "",
}


def load():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        return dict(DEFAULTS)
    try:
        d = json.loads(CONFIG_FILE.read_text())
        merged = dict(DEFAULTS)
        merged.update(d)
        return merged
    except Exception:
        return dict(DEFAULTS)


def save(**kw):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    c = load()
    c.update(kw)
    CONFIG_FILE.write_text(json.dumps(c, indent=2, ensure_ascii=False))


def is_cfg():
    c = load()
    return bool(c["pair_password"]) or (c["mode"] == "lan" and bool(load().get("peer_ip", "")))


# ─── Crypto ───────────────────────────────────────────────────────

def _key(pw, salt=None):
    if salt is None:
        salt = os.urandom(16)
    k = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100000)
    return k.derive(pw.encode()), salt


def enc(password, plain):
    k, salt = _key(password)
    n = os.urandom(12)
    ct = AESGCM(k).encrypt(n, plain.encode(), None)
    return base64.urlsafe_b64encode(salt + n + ct).decode()


def dec(password, token):
    r = base64.urlsafe_b64decode(token.encode())
    k, _ = _key(password, r[:16])
    return AESGCM(k).decrypt(r[16:28], r[28:], None).decode()


# ─── Protocol ─────────────────────────────────────────────────────

def ts():
    return datetime.now().strftime("%H:%M")


def uid():
    return os.urandom(4).hex()


def pk(d):
    return json.dumps(d, ensure_ascii=False) + "\n"


def up(line):
    try:
        return json.loads(line.strip())
    except Exception:
        return None


def code6():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


# ─── Setup ────────────────────────────────────────────────────────

def setup_wizard():
    console.print("\n[bold cyan]== LT Setup ==[/]\n")
    m = console.input("[bold]Mode[/] ([green]lan[/]/[yellow]p2p[/], Enter=p2p): ").strip().lower() or "p2p"
    if m not in ("lan", "p2p"):
        m = "p2p"
    nm = console.input(f"[bold]Name[/] (Enter={DEFAULTS['display_name']}): ").strip() or DEFAULTS['display_name']
    cfg = {"mode": m, "display_name": nm}

    if m == "lan":
        ip = console.input("[bold]Peer IP[/]: ").strip()
        p = console.input("[bold]Port[/] (5050): ").strip() or "5050"
        cfg.update({"peer_ip": ip, "port": int(p)})
    else:
        pw = console.input("[bold]Password[/] (min 4 chars): ", password=True).strip()
        if len(pw) < 4:
            console.print("[red]Need at least 4 chars[/]")
            return setup_wizard()
        pw2 = console.input("[bold]Confirm[/]: ", password=True).strip()
        if pw != pw2:
            console.print("[red]Don't match[/]")
            return setup_wizard()
        p = console.input("[bold]Port[/] (5050): ").strip() or "5050"
        cfg.update({"pair_password": pw, "port": int(p)})

    save(**cfg)
    console.print(f"\n[green]Saved. Run: lt[/]\n")


# ─── Transport (LAN) ─────────────────────────────────────────────

class LAN:
    def __init__(self, host, port):
        self.host, self.port = host, port
        self.sock = None
        self.buf = ""
        self.running = False
        self.on_msg = None
        self.on_st = None

    def connect(self):
        # Try connecting to peer first
        for i in range(10):
            try:
                s = socket.socket(); s.settimeout(2)
                s.connect((self.host, self.port)); s.settimeout(None)
                self.sock = s
                self.running = True
                if self.on_st: self.on_st("connected")
                threading.Thread(target=self._r, daemon=True).start()
                return True
            except (ConnectionRefusedError, socket.timeout, OSError):
                if i == 0 and self.on_st:
                    self.on_st(f"connecting to {self.host}:{self.port}")
                time.sleep(1)

        # Failed to connect — start listening instead
        if self.on_st: self.on_st("waiting for incoming connection")
        try:
            sv = socket.socket(); sv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sv.bind(("0.0.0.0", self.port)); sv.listen(1); sv.settimeout(None)
            sv.settimeout(10)
            conn, addr = sv.accept()
            self.sock = conn
            self.running = True
            if self.on_st: self.on_st("connected")
            threading.Thread(target=self._r, daemon=True).start()
            sv.close()
            return True
        except Exception as e:
            if self.on_st: self.on_st(f"failed: {e}")
            return False

    def _r(self):
        while self.running:
            try:
                d = self.sock.recv(65536)
                if not d: raise ConnectionResetError
                self.buf += d.decode()
                while "\n" in self.buf:
                    l, self.buf = self.buf.split("\n", 1)
                    if self.on_msg: self.on_msg(l)
            except:
                if self.on_st: self.on_st("disconnected")
                if not self.running: break
                if self.on_st: self.on_st("reconnecting")
                for _ in range(30):
                    if not self.running: return
                    try:
                        s = socket.socket(); s.settimeout(3)
                        s.connect((self.host, self.port)); s.settimeout(None)
                        self.sock = s
                        if self.on_st: self.on_st("connected")
                        self.buf = ""
                        break
                    except: time.sleep(2)

    def send(self, d):
        if not self.sock: return False
        try:
            self.sock.sendall(d.encode()); return True
        except: return False

    def close(self):
        self.running = False
        if self.sock:
            try: self.sock.close()
            except: pass


# ─── Transport (P2P TCP) ─────────────────────────────────────────

class P2P:
    def __init__(self, password, port):
        self.password = password
        self.port = port
        self.sock = None
        self.buf = ""
        self.running = False
        self.on_msg = None
        self.on_st = None
        self._server = None
        self.mode = None  # "create" or "join"

    def create(self):
        """Start as server, wait for connection."""
        self.mode = "create"
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._server.bind(("0.0.0.0", self.port))
            self._server.listen(1)
            self._server.settimeout(None)
        except OSError:
            if self.on_st: self.on_st(f"Port {self.port} in use")
            return False
        if self.on_st: self.on_st(f"listening on port {self.port}")
        self.running = True
        threading.Thread(target=self._wait_peer, daemon=True).start()
        return True

    def _wait_peer(self):
        try:
            conn, addr = self._server.accept()
            self.sock = conn
            if self.on_st: self.on_st(f"connected from {addr[0]}:{addr[1]}")
            threading.Thread(target=self._r, daemon=True).start()
        except Exception as e:
            if self.on_st: self.on_st(f"error: {e}")

    def join(self, host, port):
        """Connect as client to peer."""
        self.mode = "join"
        self._server = None
        for _ in range(10):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(5)
                s.connect((host, int(port)))
                s.settimeout(None)
                self.sock = s
                self.running = True
                if self.on_st: self.on_st("connected")
                threading.Thread(target=self._r, daemon=True).start()
                return True
            except (ConnectionRefusedError, socket.timeout, OSError):
                time.sleep(1)
        if self.on_st: self.on_st("connection failed")
        return False

    def _r(self):
        while self.running:
            try:
                d = self.sock.recv(65536)
                if not d: raise ConnectionResetError
                self.buf += d.decode()
                while "\n" in self.buf:
                    l, self.buf = self.buf.split("\n", 1)
                    if self.on_msg: self.on_msg(l)
            except:
                if self.on_st: self.on_st("disconnected")
                if self.running and self.on_st:
                    self.on_st("reconnecting")
                break

    def send(self, d):
        if not self.sock: return False
        try:
            self.sock.sendall(d.encode()); return True
        except: return False

    def close(self):
        self.running = False
        if self.sock:
            try: self.sock.close()
            except: pass
        if self._server:
            try: self._server.close()
            except: pass


# ─── Chat Engine ──────────────────────────────────────────────────

CHUNK = 65536
file_buf = {}
file_meta = {}

def fmt(sz):
    for u in ("B","KB","MB","GB"):
        if sz < 1024: return f"{sz:.0f}{u}"
        sz /= 1024
    return f"{sz:.0f}TB"

class Chat:
    def __init__(self):
        self.tp = None
        self.ok = False
        self.cfg = load()

    def _st(self, text):
        if text == "connected":
            console.print(f"\n[bold green]✓ Connected[/]")
        elif text == "disconnected":
            console.print(f"\n[bold red]✗ Disconnected[/]")
        elif text == "reconnecting":
            console.print(f"\n[bold yellow]⟳ Reconnecting...[/]")
        else:
            console.print(f"  [dim]{text}[/]")

    def _incoming(self, raw):
        msg = up(raw)
        if not msg: return
        t = msg.get("type","")
        d = msg.get("data","")
        s = msg.get("sender","Peer")
        tm = msg.get("time", ts())
        pw = self.cfg.get("pair_password","")

        # decrypt
        if pw and self.cfg["mode"] != "lan" and t not in ("ping","pong","status"):
            try:
                inner = json.loads(dec(pw, d))
                t = inner.get("type", t)
                d = inner.get("data", d)
                s = inner.get("sender", s)
            except: pass

        if t == "ping":
            self.tp.send(pk({"type":"pong"}))
        elif t == "pong":
            pass
        elif t == "status":
            console.print(f"  [dim]{d}[/]")
        elif t == "text":
            console.print(f" [bold green]{s}[/] [dim]({tm})[/dim]: {d}")
        elif t == "clip":
            console.print(f" [bold magenta]📋 {s}[/] [dim]({tm})[/dim]")
            if CLIP_OK and d:
                try: pyperclip.copy(d); console.print("  [dim]✓ copied to clipboard[/]")
                except: pass
        elif t == "file_meta" and isinstance(d, dict):
            fid, nm, sz = d["file_id"], d["name"], d["size"]
            file_buf[fid] = []; file_meta[fid] = d
            console.print(f"\n  [bold]Incoming: {nm} ({fmt(sz)})[/]")
            a = console.input("  Accept? (y/n): ").strip().lower()
            if a == "y":
                self.tp.send(pk({"type":"file_accept","data":{"file_id":fid}}))
            else:
                self.tp.send(pk({"type":"file_reject","data":{"file_id":fid}}))
        elif t == "file_chunk" and isinstance(d, dict):
            fid = d["file_id"]
            if fid not in file_buf: file_buf[fid] = []
            file_buf[fid].append(d)
            if d["seq"]+1 >= d["total"]:
                self._assemble(fid)

    def _assemble(self, fid):
        ch = sorted(file_buf[fid], key=lambda x: x["seq"])
        m = file_meta[fid]
        nm = m["name"]
        dd = Path(self.cfg.get("download_dir","~/Downloads/LT")).expanduser()
        dd.mkdir(parents=True, exist_ok=True)
        p = dd / nm
        with open(p,"wb") as f:
            for c in ch:
                f.write(base64.b64decode(c["data"]))
        console.print(f"  [green]received: {nm} -> {p}[/]")
        del file_buf[fid]; del file_meta[fid]

    def start(self):
        self.cfg = load()
        m = self.cfg["mode"]
        pw = self.cfg["pair_password"]
        port = self.cfg.get("port", 5050)

        if m == "lan":
            self.tp = LAN(self.cfg["peer_ip"], port)
            self.tp.on_msg = self._incoming
            self.tp.on_st = self._st
            return self.tp.connect()

        # P2P mode
        self.tp = P2P(pw, port)
        self.tp.on_msg = self._incoming
        self.tp.on_st = self._st

        console.print("\n[bold]P2P Mode[/]")
        console.print("1. [green]Create[/] session (you wait for friend)")
        console.print("2. [yellow]Join[/] session (connect to friend)")
        ch = console.input("\nChoose [1/2]: ").strip()

        if ch == "2":
            # Join
            host = console.input("Friend's IP: ").strip()
            p = console.input("Port: ").strip() or str(port)
            return self.tp.join(host, p)
        else:
            # Create
            code = code6()
            save(last_code=code)
            console.print(f"\n  [bold green]Your session code: {code}[/]")
            console.print("  Share this with your friend.\n")
            ok = self.tp.create()
            return ok

    def send_text(self, text):
        self.cfg = load()
        pw = self.cfg.get("pair_password","")
        nm = self.cfg.get("display_name","")
        if pw and self.cfg["mode"] != "lan":
            inner = json.dumps({"type":"text","data":text,"sender":nm})
            self.tp.send(pk({"type":"text","data":enc(pw,inner)}))
        else:
            self.tp.send(pk({"type":"text","data":text,"sender":nm}))
        console.print(f" [bold blue]{nm}[/] [dim]({ts()})[/dim]: {text}")

    def send_clip(self):
        if not CLIP_OK:
            console.print("[red]pip3 install pyperclip --break-system-packages[/]")
            return
        t = pyperclip.paste()
        if not t.strip():
            console.print("[yellow]clipboard empty[/]")
            return
        self.cfg = load()
        pw = self.cfg.get("pair_password","")
        nm = self.cfg.get("display_name","")
        if pw and self.cfg["mode"] != "lan":
            inner = json.dumps({"type":"clip","data":t,"sender":nm})
            self.tp.send(pk({"type":"clip","data":enc(pw,inner)}))
        else:
            self.tp.send(pk({"type":"clip","data":t,"sender":nm}))
        console.print(f"[green]clip sent ({len(t)} chars)[/]")

    def send_file(self, path_str):
        p = Path(path_str).expanduser()
        if not p.exists():
            console.print(f"[red]not found: {p}[/]"); return
        nm, sz = p.name, p.stat().st_size
        fid = uid()
        self.cfg = load()
        pw = self.cfg.get("pair_password","")
        snd = self.cfg.get("display_name","")

        if pw and self.cfg["mode"] != "lan":
            inner = json.dumps({"type":"file_meta","data":{"name":nm,"size":sz,"file_id":fid},"sender":snd})
            self.tp.send(pk({"type":"file_meta","data":enc(pw,inner)}))
        else:
            self.tp.send(pk({"type":"file_meta","data":{"name":nm,"size":sz,"file_id":fid},"sender":snd}))
        console.print(f"  sending: {nm} ({fmt(sz)})")

        total = (sz + CHUNK - 1)//CHUNK
        with Progress(TextColumn("{task.description}"), BarColumn(), TextColumn("{task.percentage:>3.0f}%"), console=console) as pr:
            t = pr.add_task(f"[cyan]{nm}", total=total)
            with open(p,"rb") as f:
                for seq in range(total):
                    b64 = base64.b64encode(f.read(CHUNK)).decode()
                    if pw and self.cfg["mode"] != "lan":
                        inner = json.dumps({"type":"file_chunk","data":{"file_id":fid,"seq":seq,"total":total,"data":b64},"sender":snd})
                        self.tp.send(pk({"type":"file_chunk","data":enc(pw,inner)}))
                    else:
                        self.tp.send(pk({"type":"file_chunk","data":{"file_id":fid,"seq":seq,"total":total,"data":b64},"sender":snd}))
                    pr.update(t, advance=1)
                    time.sleep(0.01)
        console.print(f"  [green]sent: {nm}[/]")

    def close(self):
        if self.tp: self.tp.close()


# ─── Main ─────────────────────────────────────────────────────────

def run(mode=None):
    cfg = load()
    if mode:
        save(mode=mode)
        cfg = load()

    chat = Chat()
    console.print("\n[bold cyan]== LT ==[/]")
    ok = chat.start()
    if not ok:
        console.print("[red]connection failed[/]")
        sys.exit(1)
    console.print("\n[bold green]--- Connected ---[/]")
    console.print("[dim]/help for commands, /exit to quit[/]\n")

    try:
        while True:
            try:
                inp = session.prompt("> ")
            except (EOFError, KeyboardInterrupt):
                break
            if not inp.strip(): continue
            cmd, *rest = inp.strip().split(" ", 1)
            low = cmd.lower()

            if low == "/exit": break
            elif low == "/clear": console.clear()
            elif low == "/ping":
                if chat.tp: chat.tp.send(pk({"type":"ping"}))
                console.print("[yellow]ping[/]")
            elif low == "/time":
                console.print(f"[yellow]{datetime.now():%H:%M:%S}[/]")
            elif low == "/clip":
                chat.send_clip()
            elif low in ("/file","/send"):
                if rest: chat.send_file(rest[0])
                else: console.print("[yellow]/file <path>[/]")
            elif low in ("/setting","/settings"):
                menu()
            elif low in ("/help","/?"):
                console.print(
                    "  [bold]/exit[/]     Quit\n"
                    "  [bold]/clear[/]    Clear screen\n"
                    "  [bold]/ping[/]     Ping peer\n"
                    "  [bold]/time[/]     Show time\n"
                    "  [bold]/clip[/]     Send clipboard\n"
                    "  [bold]/file[/] <p> Send file\n"
                    "  [bold]/setting[/]  Settings\n"
                    "  [bold]/help[/]     This help"
                )
            elif low.startswith("/"):
                console.print(f"[red]unknown: {cmd}[/]")
            else:
                chat.send_text(inp.strip())
    finally:
        chat.close()
        console.print("[dim]disconnected[/]")


def menu():
    cfg = load()
    console.print("\n[bold]== Settings ==[/]")
    console.print(f"1. Name: {cfg.get('display_name','')}")
    console.print(f"2. Mode: {cfg['mode'].upper()}")
    console.print(f"3. Port: {cfg.get('port',5050)}")
    console.print(f"4. Password: {'****' if cfg.get('pair_password') else '(empty)'}")
    console.print(f"5. Download: {cfg.get('download_dir','')}")
    console.print("0. Done")
    ch = console.input("Edit #: ").strip()
    if ch == "1":
        n = console.input("Name: ").strip()
        if n: save(display_name=n)
    elif ch == "2":
        m = console.input("Mode (lan/p2p): ").strip().lower()
        if m in ("lan","p2p"): save(mode=m)
    elif ch == "3":
        p = console.input("Port: ").strip()
        if p.isdigit(): save(port=int(p))
    elif ch == "4":
        pw = console.input("Password: ", password=True).strip()
        save(pair_password=pw)
    elif ch == "5":
        d = console.input("Download dir: ").strip()
        if d: save(download_dir=d)


def main():
    ap = argparse.ArgumentParser(prog="lt", description="LT — Local Text")
    ap.add_argument("--setup", action="store_true", help="Configure")
    ap.add_argument("--lan", action="store_true", help="LAN mode")
    ap.add_argument("--p2p", action="store_true", help="P2P mode")
    args = ap.parse_args()

    if args.setup:
        setup_wizard()
        return

    if not is_cfg():
        console.print("[yellow]Run: lt --setup[/]")
        sys.exit(1)

    mode = None
    if args.lan: mode = "lan"
    elif args.p2p: mode = "p2p"
    run(mode)


if __name__ == "__main__":
    main()
