#!/usr/bin/env python3
"""
LT — Local Text
Chat over LAN, P2P (Internet), or Tor.

Usage:
  lt                Connect and chat
  lt --setup        Configure (works any time)
  lt --lan          Force LAN mode
  lt --p2p          Force P2P mode
  lt --tor          Force Tor mode
  lt --help         Show this
"""

import argparse
import base64
import json
import os
import platform
import queue
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.patch_stdout import patch_stdout
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn
    from rich.table import Table
    from rich.text import Text
    from rich.layout import Layout
except ImportError:
    print("Missing dependencies. Run: pip install rich prompt_toolkit --break-system-packages")
    sys.exit(1)

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

try:
    import pyperclip
    CLIP_AVAILABLE = True
except ImportError:
    CLIP_AVAILABLE = False

CONFIG_DIR = Path.home() / ".config" / "lt"
CONFIG_FILE = CONFIG_DIR / "settings.json"
OFFLINE_DIR = CONFIG_DIR / "offline"

console = Console()


# ─── Config ───────────────────────────────────────────────────────

DEFAULT_CONFIG = {
    "mode": "lan",
    "peer_ip": "",
    "port": 5050,
    "pair_password": "",
    "display_name": platform.node() or "MyDevice",
    "stun_server": "stun.l.google.com:19302",
    "auto_reconnect": True,
    "download_dir": str(Path.home() / "Downloads" / "LT"),
    "show_timestamps": True,
}


def load_config():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        return dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_FILE) as f:
            data = json.load(f)
        merged = dict(DEFAULT_CONFIG)
        merged.update(data)
        return merged
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_CONFIG)


def save_config(**kwargs):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    cfg = load_config()
    cfg.update(kwargs)
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    return cfg


def is_configured():
    cfg = load_config()
    if cfg["mode"] == "lan":
        return bool(cfg["peer_ip"])
    return bool(cfg["pair_password"])


# ─── Crypto ───────────────────────────────────────────────────────

def derive_key(password: str, salt: bytes = None):
    if salt is None:
        salt = os.urandom(16)
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100000)
    return kdf.derive(password.encode()), salt


def encrypt(password: str, plain: str) -> str:
    key, salt = derive_key(password)
    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, plain.encode(), None)
    return base64.urlsafe_b64encode(salt + nonce + ct).decode()


def decrypt(password: str, token: str) -> str:
    raw = base64.urlsafe_b64decode(token.encode())
    salt, nonce, ct = raw[:16], raw[16:28], raw[28:]
    key, _ = derive_key(password, salt)
    return AESGCM(key).decrypt(nonce, ct, None).decode()


def encrypt_file(password: str, data: bytes) -> bytes:
    key, salt = derive_key(password)
    nonce = os.urandom(12)
    return salt + nonce + AESGCM(key).encrypt(nonce, data, None)


def decrypt_file(password: str, data: bytes) -> bytes:
    salt, nonce, ct = data[:16], data[16:28], data[28:]
    key, _ = derive_key(password, salt)
    return AESGCM(key).decrypt(nonce, ct, None)


# ─── Protocol ─────────────────────────────────────────────────────

def ts():
    return datetime.now().strftime("%H:%M")


def make_msg(msg_type: str, data, sender="", msg_id=""):
    import uuid
    return {
        "type": msg_type,
        "id": msg_id or str(uuid.uuid4())[:8],
        "data": data,
        "time": ts(),
        "sender": sender,
    }


def pack(msg: dict) -> str:
    return json.dumps(msg, ensure_ascii=False) + "\n"


def unpack(line: str):
    line = line.strip()
    if not line:
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


# ─── Setup ────────────────────────────────────────────────────────

def setup_interactive():
    console.print("\n[bold cyan]╔══ LT Setup ══╗[/]")
    console.print()

    mode = console.input("[bold]Connection mode[/] ([green]lan[/]/[yellow]p2p[/]/[magenta]tor[/], Enter=p2p): ").strip().lower() or "p2p"
    if mode not in ("lan", "p2p", "tor"):
        mode = "p2p"

    name = console.input(f"[bold]Display name[/] (Enter={DEFAULT_CONFIG['display_name']}): ").strip() or DEFAULT_CONFIG["display_name"]

    cfg = {"mode": mode, "display_name": name}

    if mode == "lan":
        ip = console.input("[bold]Peer IP address[/]: ").strip()
        port_str = console.input("[bold]Port[/] (Enter=5050): ").strip() or "5050"
        port = int(port_str) if port_str.isdigit() else 5050
        cfg.update({"peer_ip": ip, "port": port})

    else:
        pw = console.input("[bold]Pairing password[/] (secret, share with friend): ", password=True).strip()
        if len(pw) < 4:
            console.print("[red]Password must be at least 4 characters[/]")
            return setup_interactive()
        pw2 = console.input("[bold]Confirm password[/]: ", password=True).strip()
        if pw != pw2:
            console.print("[red]Passwords don't match[/]")
            return setup_interactive()
        cfg["pair_password"] = pw
        if mode == "p2p":
            port_str = console.input("[bold]Port[/] (Enter=5050): ").strip() or "5050"
            cfg["port"] = int(port_str) if port_str.isdigit() else 5050

    save_config(**cfg)
    console.print(f"\n[green]✓ Saved to {CONFIG_FILE}[/]")
    console.print("[green]✓ Run [bold]lt[/] to connect[/]")
    console.print()


# ─── Transport ────────────────────────────────────────────────────

class LANTransport:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.sock = None
        self.buf = ""
        self.running = False
        self.on_message = None
        self.on_status = None

    def connect(self):
        result = {"sock": None}

        def client():
            for _ in range(15):
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(2)
                    s.connect((self.host, self.port))
                    s.settimeout(None)
                    result["sock"] = s
                    return
                except (ConnectionRefusedError, socket.timeout, OSError):
                    time.sleep(1)

        def server():
            try:
                srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                srv.bind(("0.0.0.0", self.port))
                srv.listen(1)
                srv.settimeout(2)
                for _ in range(20):
                    if result["sock"]:
                        srv.close()
                        return
                    try:
                        c, a = srv.accept()
                        if not result["sock"]:
                            result["sock"] = c
                        else:
                            c.close()
                        srv.close()
                        return
                    except socket.timeout:
                        continue
                srv.close()
            except OSError:
                pass

        t1 = threading.Thread(target=client, daemon=True)
        t2 = threading.Thread(target=server, daemon=True)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        if not result["sock"]:
            return False

        self.sock = result["sock"]
        self.running = True
        if self.on_status:
            self.on_status("connected")
        threading.Thread(target=self._recv, daemon=True).start()
        return True

    def _recv(self):
        while self.running:
            try:
                data = self.sock.recv(65536)
                if not data:
                    raise ConnectionResetError
                self.buf += data.decode()
                while "\n" in self.buf:
                    line, self.buf = self.buf.split("\n", 1)
                    if self.on_message:
                        self.on_message(line)
            except (ConnectionResetError, BrokenPipeError, OSError):
                if self.on_status:
                    self.on_status("disconnected")
                if not self.running:
                    break
                if self.on_status:
                    self.on_status("reconnecting")
                if self._reconnect():
                    if self.on_status:
                        self.on_status("connected")
                    self.buf = ""

    def _reconnect(self):
        for _ in range(30):
            if not self.running:
                return False
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(3)
                s.connect((self.host, self.port))
                s.settimeout(None)
                self.sock = s
                return True
            except (ConnectionRefusedError, socket.timeout, OSError):
                time.sleep(2)
        return False

    def send(self, data: str):
        if not self.sock:
            return False
        try:
            self.sock.sendall(data.encode())
            return True
        except (BrokenPipeError, ConnectionResetError, OSError):
            return False

    def close(self):
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass


class P2PTransport:
    def __init__(self, password, stun_server="stun.l.google.com:19302"):
        self.password = password
        self.stun_server = stun_server
        self.sock = None
        self.peer_addr = None
        self.public_ip = None
        self.public_port = None
        self.running = False
        self.on_message = None
        self.on_status = None
        self.seq = 0

    def get_public(self):
        try:
            from stun import get_ip_info
            host = self.stun_server.split(":")[0]
            sport = int(self.stun_server.split(":")[1])
            nat, ip, port = get_ip_info(stun_host=host, stun_port=sport)
            self.public_ip = ip
            self.public_port = port
            return ip, port
        except Exception as e:
            return None, None

    def connect(self):
        ip, port = self.get_public()
        if not ip:
            if self.on_status:
                self.on_status("STUN failed — can't get public IP")
            return False

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("0.0.0.0", 0))
        cfg = load_config()
        cfg["p2p_port"] = self.sock.getsockname()[1]
        save_config(**cfg)

        if self.on_status:
            self.on_status(f"Your public: {ip}:{self.sock.getsockname()[1]}")
        self.running = True
        return True

    def set_peer(self, peer_ip, peer_port):
        self.peer_addr = (peer_ip, int(peer_port))
        if self.on_status:
            self.on_status("connecting")
        self.running = True
        threading.Thread(target=self._recv, daemon=True).start()
        if self.on_status:
            self.on_status("connected")
        return True

    def _recv(self):
        while self.running:
            try:
                self.sock.settimeout(2)
                data, addr = self.sock.recvfrom(65536)
                if data == b"\x06":
                    continue
                if data.startswith(b"\x01"):
                    seq = int.from_bytes(data[1:5], "big")
                    self.sock.sendto(b"\x06", addr)
                    payload = data[5:]
                    if self.on_message:
                        self.on_message(payload.decode())
                    continue
                if self.on_message:
                    self.on_message(data.decode())
            except socket.timeout:
                continue
            except OSError:
                break

    def send(self, data: str):
        if not self.sock or not self.peer_addr:
            return False
        payload = data.encode()
        seq = self.seq
        self.seq += 1
        packet = b"\x01" + seq.to_bytes(4, "big") + payload
        for _ in range(3):
            try:
                self.sock.sendto(packet, self.peer_addr)
                self.sock.settimeout(1)
                ack, _ = self.sock.recvfrom(64)
                if ack == b"\x06":
                    return True
            except socket.timeout:
                continue
            except OSError:
                return False
        return False

    def close(self):
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass


class TorTransport:
    def __init__(self, password, socks_port=9050, control_port=9051):
        self.password = password
        self.socks_port = socks_port
        self.control_port = control_port
        self.sock = None
        self.running = False
        self.on_message = None
        self.on_status = None
        self.buf = ""

    def connect(self):
        try:
            import stem.control
            with stem.control.Controller.from_port(port=self.control_port) as c:
                c.authenticate()
                svc = c.create_hidden_service({load_config().get("port", 5050): load_config().get("port", 5050)}, await_publication=True)
                addr = f"{svc.service_id}.onion"
                if self.on_status:
                    self.on_status(f"Your .onion: {addr}:{load_config().get('port', 5050)}")
            self.running = True
            return True
        except ImportError:
            if self.on_status:
                self.on_status("Tor mode requires: pip install stem")
            return False
        except Exception as e:
            if self.on_status:
                self.on_status(f"Tor error: {e}")
            return False

    def connect_to(self, onion_addr, port):
        try:
            import socks
            s = socks.socksocket()
            s.set_proxy(socks.SOCKS5, "127.0.0.1", self.socks_port)
            s.settimeout(10)
            s.connect((onion_addr, int(port)))
            s.settimeout(None)
            self.sock = s
            self.running = True
            if self.on_status:
                self.on_status("connected")
            threading.Thread(target=self._recv, daemon=True).start()
            return True
        except Exception as e:
            if self.on_status:
                self.on_status(f"Tor connect error: {e}")
            return False

    def _recv(self):
        while self.running:
            try:
                data = self.sock.recv(65536)
                if not data:
                    raise ConnectionResetError
                self.buf += data.decode()
                while "\n" in self.buf:
                    line, self.buf = self.buf.split("\n", 1)
                    if self.on_message:
                        self.on_message(line)
            except (ConnectionResetError, BrokenPipeError, OSError):
                if self.on_status:
                    self.on_status("disconnected")
                time.sleep(3)
                if not self.running:
                    break

    def send(self, data: str):
        if not self.sock:
            return False
        try:
            self.sock.sendall(data.encode())
            return True
        except (BrokenPipeError, ConnectionResetError, OSError):
            return False

    def close(self):
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass


# ─── Chat ─────────────────────────────────────────────────────────

CHUNK_SIZE = 65536
offline_queue = []
file_recv_buf = {}
file_recv_meta = {}

STATUS_ICONS = {
    "connected": "[bold green]✓ Connected[/]",
    "disconnected": "[bold red]✗ Disconnected[/]",
    "reconnecting": "[bold yellow]⟳ Reconnecting...[/]",
    "connecting": "[bold yellow]⟳ Connecting...[/]",
}


class Chat:
    def __init__(self):
        self.transport = None
        self.running = False
        self.peer_ok = False
        self.recv_count = 0
        self.cfg = load_config()
        self._lock = threading.Lock()
        self._file_buf = {}
        self._file_meta = {}

    def start(self, mode_override=None):
        self.cfg = load_config()
        mode = mode_override or self.cfg["mode"]
        password = self.cfg.get("pair_password", "")
        stun = self.cfg.get("stun_server", "stun.l.google.com:19302")
        port = self.cfg.get("port", 5050)

        if mode == "lan":
            self.transport = LANTransport(self.cfg["peer_ip"], port)
        elif mode == "p2p":
            self.transport = P2PTransport(password, stun)
        elif mode == "tor":
            self.transport = TorTransport(password)
        else:
            console.print("[red]Unknown mode[/]")
            return False

        self.transport.on_status = self._on_status
        self.transport.on_message = self._on_raw_msg
        ok = self.transport.connect()

        if mode == "p2p" and ok:
            ip, p = None, None
            try:
                from stun import get_ip_info
                shost = stun.split(":")[0]
                sport = int(stun.split(":")[1])
                nat, ip, p = get_ip_info(stun_host=shost, stun_port=sport)
            except:
                pass
            if ip:
                console.print(f"\n[yellow]Your public address: [bold]{ip}:{self.cfg.get('p2p_port', '?')}[/][/]")
                console.print("[yellow]Share this with your friend.[/]")
                console.print("[yellow]Then enter their address: [bold]IP:PORT[/][/]")
                addr = console.input("[bold]> [/]").strip()
                parts = addr.rsplit(":", 1)
                if len(parts) == 2:
                    self.transport.set_peer(parts[0], parts[1])
                else:
                    console.print("[red]Invalid address[/]")
                    return False
            return True

        if mode == "tor" and ok:
            console.print(f"\n[yellow]Your .onion is ready. Share it with your friend.[/]")
            console.print("[yellow]Enter friend's .onion address: [bold]address.onion:PORT[/][/]")
            addr = console.input("[bold]> [/]").strip()
            parts = addr.rsplit(":", 1)
            if len(parts) == 2:
                ok = self.transport.connect_to(parts[0], parts[1])
            else:
                console.print("[red]Invalid address[/]")
                return False

        return ok

    def _on_status(self, text):
        icon = STATUS_ICONS.get(text, f"[yellow]{text}[/]")
        with patch_stdout():
            console.print(Panel(icon, border_style="dim"))
        if text == "connected":
            self.peer_ok = True
            self._flush_offline()
        elif text == "disconnected":
            self.peer_ok = False

    def _on_raw_msg(self, raw_line):
        msg = unpack(raw_line)
        if not msg:
            return

        msg_type = msg.get("type", "")
        data = msg.get("data", "")
        sender = msg.get("sender", "Peer")
        t = msg.get("time", ts())

        cfg = self.cfg
        password = cfg.get("pair_password", "")

        # Decrypt if encrypted
        if password and cfg["mode"] != "lan" and msg_type not in ("ping", "pong", "status"):
            try:
                decrypted = decrypt(password, data)
                inner = json.loads(decrypted)
                msg_type = inner.get("type", msg_type)
                data = inner.get("data", data)
                sender = inner.get("sender", sender)
            except Exception:
                pass

        self.recv_count += 1

        if msg_type == "ping":
            self.transport.send(pack(make_msg("pong", "")))

        elif msg_type == "pong":
            pass

        elif msg_type == "status":
            with patch_stdout():
                console.print(Panel(f"[yellow]{data}[/]", border_style="dim"))

        elif msg_type == "text":
            with patch_stdout():
                console.print(f" [bold green]{sender}[/] [dim]({t})[/]: {data}")

        elif msg_type == "clip":
            with patch_stdout():
                console.print(f" [bold magenta]📋 {sender} sent clipboard[/] [dim]({t})[/]")
            if CLIP_AVAILABLE and data:
                try:
                    pyperclip.copy(data)
                    with patch_stdout():
                        console.print("[dim]✓ Copied to your clipboard[/]")
                except:
                    pass

        elif msg_type == "file_meta":
            if isinstance(data, dict):
                fid = data["file_id"]
                name = data["name"]
                size = data["size"]
                self._file_meta[fid] = data
                self._file_buf[fid] = []
                with patch_stdout():
                    console.print(f"\n[bold cyan]📁 {sender} wants to send: {name} ({fmt_size(size)})[/]")
                    resp = console.input("[bold]Accept? (y/n): [/]").strip().lower()
                if resp == "y":
                    self.transport.send(pack(make_msg("file_accept", {"file_id": fid})))
                    with patch_stdout():
                        console.print(f"[cyan]Receiving {name}...[/]")
                else:
                    self.transport.send(pack(make_msg("file_reject", {"file_id": fid})))

        elif msg_type == "file_accept":
            pass

        elif msg_type == "file_reject":
            fid = data.get("file_id", "")
            with patch_stdout():
                console.print(f"[red]File rejected[/]")

        elif msg_type == "file_chunk":
            if isinstance(data, dict):
                fid = data["file_id"]
                if fid not in self._file_buf:
                    self._file_buf[fid] = []
                    self._file_meta[fid] = data
                self._file_buf[fid].append(data)
                seq = data["seq"]
                total = data["total"]
                if seq + 1 >= total:
                    self._assemble_file(fid)

    def _assemble_file(self, file_id):
        chunks = sorted(self._file_buf[file_id], key=lambda x: x["seq"])
        meta = self._file_meta[file_id]
        name = meta["name"]
        down_dir = Path(self.cfg.get("download_dir", "~/Downloads/LT"))
        down_dir = down_dir.expanduser()
        down_dir.mkdir(parents=True, exist_ok=True)
        out = down_dir / name
        with open(out, "wb") as f:
            for chunk in chunks:
                f.write(base64.b64decode(chunk["data"]))
        with patch_stdout():
            console.print(f"[green]✓ Received: {name} → {out}[/]")
        del self._file_buf[file_id]
        del self._file_meta[file_id]

    def send_text(self, text, sender=""):
        cfg = self.cfg
        password = cfg.get("pair_password", "")
        sender = sender or cfg.get("display_name", "")

        if not self.peer_ok:
            self._queue_offline({"type": "text", "data": text, "sender": sender})
            console.print("[yellow]📨 Saved for later (friend offline)[/]")
            return True

        if password and cfg["mode"] != "lan":
            inner = json.dumps({"type": "text", "data": text, "sender": sender})
            encrypted = encrypt(password, inner)
            raw = pack(make_msg("text", encrypted))
        else:
            raw = pack(make_msg("text", text, sender))

        return self.transport.send(raw)

    def send_clip(self):
        if not CLIP_AVAILABLE:
            console.print("[red]Clipboard requires: pip install pyperclip --break-system-packages[/]")
            return
        text = pyperclip.paste()
        if not text.strip():
            console.print("[yellow]Clipboard is empty[/]")
            return

        cfg = self.cfg
        password = cfg.get("pair_password", "")
        sender = cfg.get("display_name", "")

        if password and cfg["mode"] != "lan":
            inner = json.dumps({"type": "clip", "data": text, "sender": sender})
            encrypted = encrypt(password, inner)
            raw = pack(make_msg("clip", encrypted))
        else:
            raw = pack(make_msg("clip", text, sender))

        ok = self.transport.send(raw)
        if ok:
            console.print(f"[green]✓ Clipboard sent ({len(text)} chars)[/]")

    def send_file(self, path_str):
        path = Path(path_str).expanduser()
        if not path.exists():
            console.print(f"[red]File not found: {path}[/]")
            return

        name = path.name
        size = path.stat().st_size
        fid = os.urandom(4).hex()
        cfg = self.cfg
        password = cfg.get("pair_password", "")
        sender = cfg.get("display_name", "")

        if not self.peer_ok:
            self._queue_offline({"type": "file_meta", "data": {"name": name, "size": size, "file_id": fid}, "sender": sender})
            console.print(f"[yellow]📨 Queued for later: {name}[/]")
            return

        if password and cfg["mode"] != "lan":
            inner = json.dumps({"type": "file_meta", "data": {"name": name, "size": size, "file_id": fid}, "sender": sender})
            encrypted = encrypt(password, inner)
            raw = pack(make_msg("file_meta", encrypted))
        else:
            raw = pack(make_msg("file_meta", {"name": name, "size": size, "file_id": fid}, sender))

        self.transport.send(raw)
        console.print(f"[cyan]Sending: {name} ({fmt_size(size)})[/]")

        total_chunks = (size + CHUNK_SIZE - 1) // CHUNK_SIZE
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=console,
        ) as progress:
            task = progress.add_task(f"[cyan]{name}", total=total_chunks)
            with open(path, "rb") as f:
                for seq in range(total_chunks):
                    chunk = f.read(CHUNK_SIZE)
                    b64 = base64.b64encode(chunk).decode()

                    if password and cfg["mode"] != "lan":
                        inner = json.dumps({
                            "type": "file_chunk",
                            "data": {"file_id": fid, "seq": seq, "total": total_chunks, "data": b64},
                            "sender": sender,
                        })
                        encrypted = encrypt(password, inner)
                        raw = pack(make_msg("file_chunk", encrypted))
                    else:
                        raw = pack(make_msg("file_chunk", {"file_id": fid, "seq": seq, "total": total_chunks, "data": b64}, sender))

                    self.transport.send(raw)
                    progress.update(task, advance=1)
                    time.sleep(0.01)

        console.print(f"[green]✓ Sent: {name}[/]")

    def _queue_offline(self, msg):
        OFFLINE_DIR.mkdir(parents=True, exist_ok=True)
        fname = OFFLINE_DIR / f"pending_{os.urandom(4).hex()}.json"
        with open(fname, "w") as f:
            json.dump(msg, f)

    def _flush_offline(self):
        if not OFFLINE_DIR.exists():
            return
        count = 0
        for fname in sorted(OFFLINE_DIR.iterdir()):
            if not fname.name.startswith("pending_"):
                continue
            try:
                with open(fname) as f:
                    msg = json.load(f)
                msg_type = msg.get("type", "")
                data = msg.get("data", "")
                sender = msg.get("sender", "")
                if msg_type == "text":
                    self.send_text(data, sender)
                elif msg_type == "file_meta":
                    if isinstance(data, dict):
                        dname = data.get("name", "")
                        dsize = data.get("size", 0)
                        dfid = data.get("file_id", "")
                        console.print(f"[yellow]📨 Resending queued file: {dname}[/]")
                        self.send_file(str(Path.cwd() / dname))
                fname.unlink()
                count += 1
            except Exception:
                pass
        if count:
            console.print(f"[green]📨 Delivered {count} pending message(s)[/]")

    def ping(self):
        if self.transport:
            self.transport.send(pack(make_msg("ping", "")))
            console.print("[yellow]ping sent[/]")

    def close(self):
        self.running = False
        if self.transport:
            self.transport.close()


def fmt_size(size):
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


# ─── Chat UI ──────────────────────────────────────────────────────

def run_chat(mode_override=None):
    chat = Chat()
    session = PromptSession()

    console.print()
    console.print(Panel("[bold cyan]LT[/] — Starting...", border_style="cyan"))

    ok = chat.start(mode_override)
    if not ok:
        console.print("[red]Connection failed[/]")
        sys.exit(1)

    cfg = load_config()
    console.print()
    console.print(Panel(
        f"[green]✓ Connected[/] • Mode: [bold]{cfg['mode'].upper()}[/] • "
        f"Type [bold]/help[/] for commands, [bold]/exit[/] to quit",
        border_style="green"
    ))
    console.print()

    try:
        while True:
            try:
                with patch_stdout():
                    user_input = session.prompt("\nYou: ")
            except (EOFError, KeyboardInterrupt):
                break

            if not user_input.strip():
                continue

            cmd = user_input.strip()
            lower = cmd.lower()

            if lower == "/exit":
                break

            elif lower == "/clear":
                console.clear()

            elif lower == "/ping":
                chat.ping()

            elif lower == "/time":
                console.print(f"[yellow]{datetime.now().strftime('%H:%M:%S')}[/]")

            elif lower == "/clip":
                chat.send_clip()

            elif lower.startswith("/file ") or lower.startswith("/send "):
                fpath = cmd.split(" ", 1)[1] if " " in cmd else ""
                if fpath:
                    chat.send_file(fpath)
                else:
                    console.print("[yellow]Usage: /file <path>[/]")

            elif lower in ("/setting", "/settings"):
                show_settings_menu()

            elif lower == "/connect":
                show_connect_menu(chat)

            elif lower in ("/help", "/?"):
                console.print(Panel(
                    "[bold]/exit[/]      Quit\n"
                    "[bold]/clear[/]     Clear screen\n"
                    "[bold]/ping[/]      Check connection\n"
                    "[bold]/time[/]      Show time\n"
                    "[bold]/clip[/]      Send clipboard\n"
                    "[bold]/file[/] <p>  Send a file\n"
                    "[bold]/setting[/]   Open settings\n"
                    "[bold]/connect[/]   Connect to new peer\n"
                    "[bold]/help[/]      This help",
                    title="Commands", border_style="cyan"
                ))

            else:
                if cmd.startswith("/"):
                    console.print(f"[red]Unknown: {cmd}. Type /help[/]")
                else:
                    chat.send_text(cmd)
                    t = ts()
                    name = cfg.get("display_name", "You")
                    console.print(f" [bold blue]{name}[/] [dim]({t})[/]: {cmd}")

    finally:
        chat.close()
        console.print("\n[dim]Disconnected[/]")


def show_settings_menu():
    cfg = load_config()
    console.print()
    console.print(Panel("[bold cyan]Settings[/]", border_style="cyan"))
    console.print(f"1. Mode: [bold]{cfg['mode'].upper()}[/]")
    console.print(f"2. Display name: [bold]{cfg.get('display_name', '')}[/]")
    console.print(f"3. Port: [bold]{cfg.get('port', 5050)}[/]")
    console.print(f"4. Pair password: [bold]{'****' if cfg.get('pair_password') else '(none)'}[/]")
    console.print(f"5. Download dir: [bold]{cfg.get('download_dir', '')}[/]")
    console.print(f"6. Show timestamps: [bold]{cfg.get('show_timestamps', True)}[/]")
    console.print(f"7. STUN server: [bold]{cfg.get('stun_server', 'stun.l.google.com:19302')}[/]")
    console.print(f"0. [bold green]Save & Exit[/]")
    console.print()

    choice = console.input("Edit # (Enter=0): ").strip()
    if choice == "1":
        m = console.input("Mode (lan/p2p/tor): ").strip().lower()
        if m in ("lan", "p2p", "tor"):
            save_config(mode=m)
            console.print("[green]✓ Mode updated (restart to apply)[/]")
    elif choice == "2":
        n = console.input("Display name: ").strip()
        if n:
            save_config(display_name=n)
            console.print("[green]✓ Name updated[/]")
    elif choice == "3":
        p = console.input("Port: ").strip()
        if p.isdigit():
            save_config(port=int(p))
            console.print("[green]✓ Port updated[/]")
    elif choice == "4":
        pw = console.input("New password (Enter to clear): ", password=True).strip()
        save_config(pair_password=pw)
        console.print("[green]✓ Password updated[/]")
    elif choice == "5":
        d = console.input("Download dir: ").strip()
        if d:
            save_config(download_dir=d)
            console.print("[green]✓ Download dir updated[/]")
    elif choice == "6":
        save_config(show_timestamps=not cfg.get("show_timestamps", True))
        console.print("[green]✓ Toggled[/]")
    elif choice == "7":
        s = console.input("STUN server (host:port): ").strip()
        if s:
            save_config(stun_server=s)
            console.print("[green]✓ STUN server updated[/]")

    console.print("[green]✓ Done[/]")


def show_connect_menu(chat):
    cfg = load_config()
    console.print()
    console.print(Panel("[bold cyan]Connect to Peer[/]", border_style="cyan"))

    if cfg["mode"] == "lan":
        ip = console.input("Peer IP: ").strip()
        chat.transport = LANTransport(ip, cfg.get("port", 5050))
    elif cfg["mode"] == "p2p":
        console.print(f"[yellow]Your public: {cfg.get('p2p_port', '?')}[/]")
        addr = console.input("Friend's IP:PORT: ").strip()
        parts = addr.rsplit(":", 1)
        if len(parts) == 2:
            if hasattr(chat.transport, "set_peer"):
                chat.transport.set_peer(parts[0], parts[1])
    elif cfg["mode"] == "tor":
        addr = console.input("Friend's .onion:PORT: ").strip()
        parts = addr.rsplit(":", 1)
        if len(parts) == 2 and hasattr(chat.transport, "connect_to"):
            chat.transport.connect_to(parts[0], parts[1])


# ─── Entry ────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="lt",
        description="LT — Local Text: Chat over LAN, P2P, or Tor",
        usage="lt [--setup | --lan | --p2p | --tor]",
    )
    parser.add_argument("--setup", action="store_true", help="Configure")
    parser.add_argument("--lan", action="store_true", help="Force LAN mode")
    parser.add_argument("--p2p", action="store_true", help="Force P2P mode")
    parser.add_argument("--tor", action="store_true", help="Force Tor mode")
    args = parser.parse_args()

    if args.setup:
        setup_interactive()
        return

    if not is_configured():
        console.print("[yellow]Not configured. Run: [bold]lt --setup[/][/]")
        sys.exit(1)

    mode = None
    if args.lan:
        save_config(mode="lan")
    elif args.p2p:
        save_config(mode="p2p")
    elif args.tor:
        save_config(mode="tor")

    run_chat(mode)


if __name__ == "__main__":
    main()
