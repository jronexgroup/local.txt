import json
import os
import threading
import time

from . import config
from . import crypto
from . import protocol as p
from .transport import create_transport

CHUNK_SIZE = 65536


class ChatEngine:
    def __init__(self, on_message=None, on_status=None, on_file_progress=None):
        self.on_message = on_message
        self.on_status = on_status
        self.on_file_progress = on_file_progress
        self.transport = None
        self.running = False
        self.offline_queue = []
        self._recv_file_buffers = {}
        self._recv_file_metas = {}
        self._send_file_cancelled = False
        self._lock = threading.Lock()
        self.peer_connected = False

    def _emit_message(self, msg: dict):
        if self.on_message:
            self.on_message(msg)

    def _emit_status(self, text: str):
        if msg := p.unpack(p.status_msg(text)):
            if self.on_message:
                self.on_message(msg)

    def _emit_file_progress(self, file_id, name, current, total):
        if self.on_file_progress:
            self.on_file_progress(file_id, name, current, total)

    def start(self, mode=None):
        cfg = config.load()
        password = cfg.get("pair_password", "")

        def transport_msg(msg):
            if not password or cfg["mode"] == "lan":
                self._emit_message(msg)
                return

            if msg["type"] in ("ping", "pong", "status"):
                self._emit_message(msg)
                return

            try:
                decrypted = crypto.decrypt(password, msg["data"])
                inner = json.loads(decrypted)
                inner["sender"] = msg.get("sender", "peer")
                inner["id"] = msg.get("id")
                self._emit_message(inner)
            except Exception:
                self._emit_message(msg)

        def transport_status(text):
            if text == "connected":
                self.peer_connected = True
                self._flush_offline()
            elif text == "disconnected":
                self.peer_connected = False
            self._emit_status(text)

        self.transport = create_transport(mode, transport_msg, transport_status)
        if not self.transport:
            self._emit_status("error: no transport available")
            return False

        self.running = True
        ok = self.transport.connect()
        if ok and mode == "lan":
            self.peer_connected = True
            self._flush_offline()
        return ok

    def send_text(self, text: str, sender=None):
        cfg = config.load()
        password = cfg.get("pair_password", "")

        if not self.peer_connected:
            self._queue_offline(p.make_msg(p.MsgType.TEXT, text, sender))
            return True

        if password and cfg["mode"] != "lan":
            inner = json.dumps({"type": "text", "data": text})
            encrypted = crypto.encrypt(password, inner)
            msg = p.pack(p.make_msg(p.MsgType.TEXT, encrypted, sender or cfg.get("display_name", "")))
        else:
            msg = p.text_msg(text, sender or cfg.get("display_name", ""))

        return self.transport.send(msg)

    def send_clip(self, clip_text: str, sender=None):
        cfg = config.load()
        password = cfg.get("pair_password", "")

        if not self.peer_connected:
            self._queue_offline(p.make_msg(p.MsgType.CLIP, clip_text, sender))
            return True

        if password and cfg["mode"] != "lan":
            inner = json.dumps({"type": "clip", "data": clip_text})
            encrypted = crypto.encrypt(password, inner)
            msg = p.pack(p.make_msg(p.MsgType.CLIP, encrypted, sender or cfg.get("display_name", "")))
        else:
            msg = p.clip_msg(clip_text, sender or cfg.get("display_name", ""))

        return self.transport.send(msg)

    def send_file(self, filepath: str, sender=None):
        if not os.path.exists(filepath):
            self._emit_status(f"file not found: {filepath}")
            return False

        name = os.path.basename(filepath)
        size = os.path.getsize(filepath)
        file_id = p.new_id()
        cfg = config.load()

        if not self.peer_connected:
            self._queue_offline({
                "type": "file_meta", "data": {"name": name, "size": size, "file_id": file_id},
                "sender": sender or cfg.get("display_name", ""),
            })
            self._emit_status(f"queued for later: {name}")
            return True

        password = cfg.get("pair_password", "")
        if password and cfg["mode"] != "lan":
            inner = json.dumps({"type": "file_meta", "data": {"name": name, "size": size, "file_id": file_id}})
            encrypted = crypto.encrypt(password, inner)
            msg = p.pack(p.make_msg(p.MsgType.FILE_META, encrypted, sender or cfg.get("display_name", "")))
        else:
            msg = p.file_meta_msg(name, size, file_id, sender or cfg.get("display_name", ""))

        self.transport.send(msg)
        self._emit_status(f"sending: {name} ({_fmt_size(size)})")

        threading.Thread(
            target=self._send_file_worker,
            args=(filepath, file_id, name, size, password),
            daemon=True,
        ).start()
        return True

    def _send_file_worker(self, filepath, file_id, name, size, password):
        seq = 0
        total_chunks = (size + CHUNK_SIZE - 1) // CHUNK_SIZE
        cfg = config.load()
        sender = cfg.get("display_name", "")

        with open(filepath, "rb") as f:
            while seq < total_chunks:
                if self._send_file_cancelled:
                    break
                chunk = f.read(CHUNK_SIZE)
                import base64
                chunk_b64 = base64.b64encode(chunk).decode()

                if password and cfg["mode"] != "lan":
                    inner = json.dumps({
                        "type": "file_chunk", "data": {
                            "file_id": file_id, "seq": seq, "total": total_chunks, "data": chunk_b64
                        }
                    })
                    encrypted = crypto.encrypt(password, inner)
                    msg = p.pack(p.make_msg(p.MsgType.FILE_CHUNK, encrypted, sender))
                else:
                    msg = p.file_chunk_msg(file_id, seq, total_chunks, chunk_b64, sender)

                if not self.transport.send(msg):
                    self._emit_status("file send failed")
                    return

                self._emit_file_progress(file_id, name, seq + 1, total_chunks)
                seq += 1
                time.sleep(0.01)

        self._emit_status(f"sent: {name}")

    def handle_peer_message(self, msg: dict):
        msg_type = msg.get("type", "")
        data = msg.get("data", "")
        sender = msg.get("sender", "peer")

        if msg_type == "file_meta":
            if isinstance(data, dict):
                self._recv_file_metas[data["file_id"]] = data
                self._recv_file_buffers[data["file_id"]] = []
                self._emit_message(msg)
                self._emit_status(f"incoming file: {data['name']} ({_fmt_size(data['size'])})")
            return

        if msg_type == "file_chunk":
            if isinstance(data, dict):
                fid = data["file_id"]
                if fid not in self._recv_file_buffers:
                    self._recv_file_buffers[fid] = []
                    self._recv_file_metas[fid] = data
                self._recv_file_buffers[fid].append(data)
                self._emit_file_progress(fid, data.get("file_id", ""), data["seq"] + 1, data["total"])
                if data["seq"] + 1 >= data["total"]:
                    threading.Thread(target=self._assemble_file, args=(fid,), daemon=True).start()
            return

        if msg_type == "clip":
            self._emit_message(msg)
            try:
                import pyperclip
                pyperclip.copy(data)
                self._emit_status("copied to clipboard")
            except Exception:
                self._emit_status("clipboard received (install pyperclip for auto-copy)")
            return

        self._emit_message(msg)

    def _assemble_file(self, file_id):
        chunks = sorted(self._recv_file_buffers[file_id], key=lambda x: x["seq"])
        meta = self._recv_file_metas[file_id]
        name = meta["name"]
        download_dir = config.get("download_dir", os.path.expanduser("~/Downloads/LT"))
        os.makedirs(download_dir, exist_ok=True)
        outpath = os.path.join(download_dir, name)

        import base64
        with open(outpath, "wb") as f:
            for chunk in chunks:
                f.write(base64.b64decode(chunk["data"]))

        self._emit_status(f"received: {name} -> {outpath}")
        del self._recv_file_buffers[file_id]
        del self._recv_file_metas[file_id]

    def _queue_offline(self, msg):
        off_file = os.path.join(config.OFFLINE_DIR, f"pending_{p.new_id()}.json")
        os.makedirs(config.OFFLINE_DIR, exist_ok=True)
        with open(off_file, "w") as f:
            json.dump(msg, f)
        self._emit_status("saved for later delivery")

    def _flush_offline(self):
        off_dir = config.OFFLINE_DIR
        if not os.path.isdir(off_dir):
            return
        count = 0
        for fname in sorted(os.listdir(off_dir)):
            if not fname.startswith("pending_"):
                continue
            fpath = os.path.join(off_dir, fname)
            try:
                with open(fpath) as f:
                    msg = json.load(f)
                self.send_text(msg.get("data", ""), msg.get("sender", ""))
                os.remove(fpath)
                count += 1
            except Exception:
                pass
        if count > 0:
            self._emit_status(f"delivered {count} pending message(s)")

    def ping(self):
        self.transport.send(p.ping_msg())

    def close(self):
        self.running = False
        if self.transport:
            self.transport.close()


def _fmt_size(size):
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"
