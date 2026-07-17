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
import struct
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit import print_formatted_text as pt_print
    from prompt_toolkit.completion import WordCompleter
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
CMD_COMPLETER = WordCompleter(["/exit", "/clear", "/ping", "/time", "/clip", "/file", "/help", "/setting"])
session = PromptSession(completer=CMD_COMPLETER)


# ─── Config ───────────────────────────────────────────────────────

DEFAULTS = {
    "port": 5050,
    "display_name": platform.node() or "Device",
    "download_dir": str(Path.home() / "Downloads" / "LT"),
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
    return bool(c.get("display_name", ""))


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
    nm = console.input(f"Your display name (Enter={DEFAULTS['display_name']}): ").strip() or DEFAULTS['display_name']
    save(display_name=nm)
    console.print(f"\n[green]Saved! Run: lt[/]\n")


# ─── Friends History ─────────────────────────────────────────────

FRIENDS_FILE = CONFIG_DIR / "friends.json"

def load_friends():
    if not FRIENDS_FILE.exists(): return []
    try: return json.loads(FRIENDS_FILE.read_text())
    except: return []

def save_friend(name, ip, port, mode):
    fr = load_friends()
    fr = [f for f in fr if not (f.get("name")==name and f.get("ip")==ip and f.get("mode")==mode)]
    fr.append({"name":name,"ip":ip,"port":port,"mode":mode,"last_seen":datetime.now().isoformat()})
    fr = sorted(fr, key=lambda x: x["last_seen"], reverse=True)[:10]
    FRIENDS_FILE.write_text(json.dumps(fr, indent=2, ensure_ascii=False))

def pick_friend(mode):
    fr = [f for f in load_friends() if f["mode"]==mode]
    if not fr: return None
    console.print(f"\n[bold]Saved {mode.upper()} friends:[/]")
    for i, f in enumerate(fr, 1):
        ts = f["last_seen"][:10] if len(f["last_seen"])>=10 else f["last_seen"]
        console.print(f"  {i}. [green]{f['name']}[/] ({f['ip']}:{f['port']}) — [dim]{ts}[/]")
    console.print(f"  {len(fr)+1}. [yellow]New connection...[/]")
    ch = console.input("\nChoose: ").strip()
    if ch.isdigit() and 1 <= int(ch) <= len(fr):
        return fr[int(ch)-1]
    return None


# ─── Transport (LAN) ─────────────────────────────────────────────

class LAN:
    def __init__(self, port):
        self.port = port
        self.sock = None
        self.buf = ""
        self.running = False
        self.on_msg = None
        self.on_st = None
        self.peer_host = None

    def listen(self):
        if self.on_st: self.on_st("waiting for incoming connection...")
        try:
            sv = socket.socket(); sv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sv.bind(("0.0.0.0", self.port)); sv.listen(1); sv.settimeout(None)
            sv.settimeout(60)
            conn, addr = sv.accept()
            self.sock = conn; self.peer_host = addr[0]
            self.running = True
            if self.on_st: self.on_st("connected")
            threading.Thread(target=self._r, daemon=True).start()
            sv.close(); return True
        except socket.timeout:
            if self.on_st: self.on_st("timed out waiting for connection")
            sv.close(); return False
        except Exception as e:
            if self.on_st: self.on_st(f"failed: {e}")
            return False

    def connect(self, host):
        self.peer_host = host
        for i in range(10):
            try:
                s = socket.socket(); s.settimeout(3)
                s.connect((host, self.port)); s.settimeout(None)
                self.sock = s; self.running = True
                if self.on_st: self.on_st("connected")
                threading.Thread(target=self._r, daemon=True).start()
                return True
            except:
                if i == 0 and self.on_st:
                    self.on_st(f"connecting to {host}:{self.port}")
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
                if not self.running: break
                if not self.peer_host: break
                if self.on_st: self.on_st("reconnecting")
                for _ in range(30):
                    if not self.running: return
                    try:
                        s = socket.socket(); s.settimeout(3)
                        s.connect((self.peer_host, self.port)); s.settimeout(None)
                        self.sock = s; self.buf = ""
                        if self.on_st: self.on_st("connected")
                        break
                    except: time.sleep(2)

    def send(self, d):
        if not self.sock: return False
        try: self.sock.sendall(d.encode()); return True
        except: return False

    def close(self):
        self.running = False
        if self.sock:
            try: self.sock.close()
            except: pass


# ─── Helper: IPs ─────────────────────────────────────────────

def get_ips():
    """Return list of local IP addresses."""
    ips = set()
    # Try hostname
    try:
        ips.add(socket.gethostbyname(socket.gethostname()))
    except: pass
    # Try all interfaces
    try:
        import subprocess
        r = subprocess.run(["hostname", "-I"], capture_output=True, text=True)
        if r.returncode == 0:
            for ip in r.stdout.strip().split():
                if ip: ips.add(ip)
    except: pass
    # Fallback
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except: pass
    # Remove loopback
    ips = sorted(ip for ip in ips if not ip.startswith("127."))
    return ips or ["127.0.0.1"]


# ─── Transport (P2P UDP + Hole Punching) ─────────────────────────

class P2P:
    """UDP-based P2P with STUN hole punching. Works behind NAT, no port forwarding needed."""

    STUN_HOST = "stun.l.google.com"
    STUN_PORT = 19302

    def __init__(self, password, port):
        self.password = password
        self.port = port
        self.sock = None
        self.running = False
        self.on_msg = None
        self.on_st = None
        self.peer_addr = None
        self.public_ip = None
        self.public_port = None
        self._seq = 0
        self._acks = {}
        self._lock = threading.Lock()

    # ── Minimal STUN (stdlib only) ─────────────────────────────

    @staticmethod
    def _stun_lookup(host=STUN_HOST, port=STUN_PORT, timeout=4):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(timeout)
            tid = os.urandom(12)
            magic = 0x2112A442
            req = struct.pack("!HH", 0x0001, 0) + struct.pack("!I", magic) + tid
            s.sendto(req, (host, port))
            res, _ = s.recvfrom(1024)
            s.close()
            if len(res) < 20: return None
            cookie = struct.unpack("!I", res[4:8])[0]
            if cookie != magic: return None
            pos = 20
            while pos + 4 <= len(res):
                atype, alen = struct.unpack("!HH", res[pos:pos+4])
                pos += 4
                if atype == 0x0020 and alen >= 8:  # XOR-MAPPED-ADDRESS
                    family = res[pos+1]
                    pval = struct.unpack("!H", res[pos+2:pos+4])[0] ^ (magic >> 16)
                    if family == 0x01:
                        ipb = bytes(a ^ b for a, b in zip(res[pos+4:pos+8], struct.pack("!I", magic)))
                        return socket.inet_ntoa(ipb), pval
                elif atype == 0x0001 and alen >= 8:  # MAPPED-ADDRESS
                    family = res[pos+1]
                    pval = struct.unpack("!H", res[pos+2:pos+4])[0]
                    if family == 0x01:
                        return socket.inet_ntoa(res[pos+4:pos+8]), pval
                pos += alen
        except: pass
        return None

    def _get_public(self):
        r = self._stun_lookup(self.STUN_HOST, self.STUN_PORT)
        if r:
            self.public_ip, self.public_port = r

    def _local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]; s.close(); return ip
        except: return "?"

    # ── Socket ───────────────────────────────────────────────────

    def _make_sock(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("0.0.0.0", self.port))
        self.port = self.sock.getsockname()[1]
        self.sock.settimeout(3)

    # ── Create (wait for peer) ───────────────────────────────────

    def create(self):
        self._make_sock()
        self._get_public()
        pub = f"{self.public_ip}:{self.public_port}" if self.public_ip else "?"
        loc = self._local_ip()
        if self.on_st: self.on_st(f"Your public: {pub}  (local: {loc}:{self.port})")
        self.running = True

        while self.running and not self.peer_addr:
            try:
                data, addr = self.sock.recvfrom(65536)
                if data == b"PUNCH":
                    self.peer_addr = addr
                    self.sock.sendto(b"PUNCH_ACK", addr)
                    self.sock.settimeout(None); self.sock.settimeout(3)
                    threading.Thread(target=self._recv, daemon=True).start()
                    if self.on_st: self.on_st("connected")
                    return True
            except socket.timeout: continue
            except OSError: break
        return False

    # ── Join (connect to peer) ──────────────────────────────────

    def join(self, host, port):
        self._make_sock()
        self._get_public()
        self.peer_addr = (host, int(port))
        pub = f"{self.public_ip}:{self.public_port}" if self.public_ip else "?"
        if self.on_st: self.on_st(f"Your public: {pub}")
        self.running = True

        for _ in range(5):
            try: self.sock.sendto(b"PUNCH", self.peer_addr)
            except: pass
            time.sleep(0.3)

        for _ in range(10):
            try:
                data, addr = self.sock.recvfrom(65536)
                if data == b"PUNCH_ACK":
                    self.peer_addr = addr
                    self.sock.settimeout(None); self.sock.settimeout(3)
                    threading.Thread(target=self._recv, daemon=True).start()
                    if self.on_st: self.on_st("connected")
                    return True
            except socket.timeout: continue
            except OSError: break

        if self.on_st: self.on_st("connection failed (peer unreachable)")
        return False

    # ── Receive (runs in bg thread) ─────────────────────────────

    def _recv(self):
        while self.running:
            try: data, addr = self.sock.recvfrom(65536)
            except socket.timeout: continue
            except OSError: break

            # ACK for sent message → signal send()
            if data.startswith(b"ACK"):
                sseq = int.from_bytes(data[3:7], "big") if len(data) >= 7 else 0
                ev = self._acks.pop(sseq, None)
                if ev: ev.set()
                continue

            # Hole punch re-establish
            if data == b"PUNCH":
                self.peer_addr = addr
                try: self.sock.sendto(b"PUNCH_ACK", addr)
                except: pass
                continue
            if data == b"PUNCH_ACK":
                self.peer_addr = addr
                continue

            # Reliable data message
            if data.startswith(b"DATA"):
                sseq = int.from_bytes(data[4:8], "big") if len(data) >= 8 else 0
                try: self.sock.sendto(b"ACK" + sseq.to_bytes(4, "big"), addr)
                except: pass
                payload = data[8:]
                if self.on_msg: self.on_msg(payload.decode())
                continue

            # Raw (fallback)
            if self.on_msg: self.on_msg(data.decode())

    # ── Send (reliable with retry + ACK) ────────────────────────

    def send(self, data):
        if not self.sock or not self.peer_addr:
            return False
        payload = data.encode()
        with self._lock:
            seq = self._seq
            self._seq += 1
        ev = threading.Event()
        self._acks[seq] = ev
        packet = b"DATA" + seq.to_bytes(4, "big") + payload

        for _ in range(3):
            try:
                self.sock.sendto(packet, self.peer_addr)
                if ev.wait(timeout=2):
                    return True
            except OSError:
                break
        self._acks.pop(seq, None)
        return False

    # ── Close ──────────────────────────────────────────────────

    def close(self):
        self.running = False
        if self.sock:
            try: self.sock.close()
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
        self._pw = ""
        self._nm = self.cfg.get("display_name", "")
        self._mode = ""

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

        pw = self._pw
        if pw and self._mode != "lan" and t not in ("ping","pong","status"):
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
        self._nm = self.cfg.get("display_name", "")
        port = self.cfg.get("port", 5050)

        # If no mode flag passed, ask
        if not self._mode:
            console.print("\n[bold]Choose mode:[/]")
            console.print("  1. [green]LAN[/] (same network)")
            console.print("  2. [yellow]P2P[/] (internet)")
            ch = console.input("> ").strip()
            self._mode = "p2p" if ch == "2" else "lan"

        # Show saved friends for this mode, try auto-connect
        friend = pick_friend(self._mode)
        if friend:
            return self._connect_friend(friend, port)

        return self._new_connection(port)

    def _connect_friend(self, friend, port):
        ip = friend["ip"]
        if self._mode == "lan":
            self.tp = LAN(port)
            self.tp.on_msg = self._incoming
            self.tp.on_st = self._st
            ok = self.tp.connect(ip)
        else:
            pw = console.input("Password for encryption: ", password=True).strip()
            self._pw = pw
            self.tp = P2P(pw, port)
            self.tp.on_msg = self._incoming
            self.tp.on_st = self._st
            ok = self.tp.join(ip, friend.get("port", port))
        if ok:
            save_friend(friend["name"], ip, port, self._mode)
        return ok

    def _new_connection(self, port):
        if self._mode == "lan":
            return self._lan_new(port)
        return self._p2p_new(port)

    def _lan_new(self, port):
        console.print("\n[bold]LAN mode[/]")
        console.print("  1. [green]Create[/] (wait for friend)")
        console.print("  2. [yellow]Connect[/] (enter friend's IP)")
        ch = console.input("> ").strip()

        self.tp = LAN(port)
        self.tp.on_msg = self._incoming
        self.tp.on_st = self._st

        if ch == "2":
            host = console.input("Friend's IP: ").strip()
            ok = self.tp.connect(host)
            if ok:
                nm = console.input("Friend's name: ").strip() or host
                save_friend(nm, host, port, "lan")
            return ok
        else:
            ips = get_ips()
            console.print(f"\n  Your IP: [bold]{ips[0] if ips else '?'}[/]")
            console.print(f"  Port: [bold]{port}[/]")
            console.print(f"  [yellow]Waiting for friend to connect...[/]")
            ok = self.tp.listen()
            if ok:
                nm = console.input("Friend's name: ").strip() or self.tp.peer_host
                save_friend(nm, self.tp.peer_host, port, "lan")
            return ok

    def _p2p_new(self, port):
        console.print("\n[bold]P2P mode (over internet)[/]")
        console.print("  1. [green]Create[/] (you wait for friend)")
        console.print("  2. [yellow]Join[/] (connect to friend)")
        ch = console.input("> ").strip()

        pw = console.input("Password for encryption: ", password=True).strip()
        self._pw = pw

        self.tp = P2P(pw, port)
        self.tp.on_msg = self._incoming
        self.tp.on_st = self._st

        if ch == "2":
            addr = console.input("Friend's IP:Port (e.g. 1.2.3.4:5050): ").strip()
            if ":" in addr:
                host, p = addr.rsplit(":", 1)
            else:
                host, p = addr, str(port)
            console.print("[yellow]Connecting...[/]")
            ok = self.tp.join(host, p)
            if ok:
                nm = console.input("Friend's name: ").strip() or host
                save_friend(nm, host, int(p), "p2p")
            return ok
        else:
            ips = get_ips()
            console.print(f"\n  Tell your friend this address:")
            stun_ip = self.tp.public_ip or ips[0] if ips else "?"
            stun_port = self.tp.public_port or port
            console.print(f"  [bold yellow]{stun_ip}:{stun_port}[/]")
            console.print(f"  (local: [dim]{ips[0] if ips else '?'}:{port}[/])")
            console.print(f"\n  [yellow]Waiting for friend to connect...[/]")
            ok = self.tp.create()
            if ok:
                nm = console.input("Friend's name: ").strip() or "Peer"
                save_friend(nm, stun_ip, stun_port, "p2p")
            return ok

    def send_text(self, text):
        pw = self._pw
        nm = self._nm
        if pw and self._mode != "lan":
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
        pw = self._pw
        nm = self._nm
        if pw and self._mode != "lan":
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
        pw = self._pw
        snd = self._nm

        if pw and self._mode != "lan":
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
                    if pw and self._mode != "lan":
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
    chat = Chat()
    if mode:
        chat._mode = mode

    ok = chat.start()
    if not ok:
        console.print("[red]connection failed[/]")
        sys.exit(1)

    console.clear()
    console.print("[bold cyan]== LT Chat ==[/]")
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
    ap.add_argument("--lan", action="store_true", help="LAN mode (same network)")
    ap.add_argument("--p2p", action="store_true", help="P2P mode (over internet)")
    args = ap.parse_args()

    if args.setup:
        setup_wizard()
        return

    if not is_cfg():
        console.print("[yellow]Run: lt --setup[/]")
        sys.exit(1)

    if args.lan: run("lan")
    elif args.p2p: run("p2p")
    else: run()  # no flag → interactive mode select


if __name__ == "__main__":
    main()
