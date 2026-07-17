import json
import uuid
from datetime import datetime
from enum import Enum


class MsgType(Enum):
    TEXT = "text"
    FILE_META = "file_meta"
    FILE_CHUNK = "file_chunk"
    FILE_ACK = "file_ack"
    FILE_REJECT = "file_reject"
    CLIP = "clip"
    PING = "ping"
    PONG = "pong"
    PAIR_REQUEST = "pair_request"
    PAIR_ACCEPT = "pair_accept"
    STATUS = "status"


def new_id():
    return str(uuid.uuid4())[:8]


def timestamp():
    return datetime.now().strftime("%H:%M")


def make_msg(msg_type: MsgType, data, sender=None, msg_id=None):
    return {
        "type": msg_type.value,
        "id": msg_id or new_id(),
        "data": data,
        "time": timestamp(),
        "sender": sender or "",
    }


def pack(msg: dict) -> str:
    return json.dumps(msg, ensure_ascii=False) + "\n"


def unpack(line: str) -> dict | None:
    line = line.strip()
    if not line:
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


def text_msg(text: str, sender: str = None) -> str:
    return pack(make_msg(MsgType.TEXT, text, sender))


def file_meta_msg(name: str, size: int, file_id: str, sender: str = None) -> str:
    return pack(make_msg(MsgType.FILE_META, {"name": name, "size": size, "file_id": file_id}, sender))


def file_chunk_msg(file_id: str, seq: int, total: int, chunk_b64: str, sender: str = None) -> str:
    return pack(make_msg(MsgType.FILE_CHUNK, {
        "file_id": file_id, "seq": seq, "total": total, "data": chunk_b64
    }, sender))


def file_ack_msg(file_id: str, seq: int) -> str:
    return pack(make_msg(MsgType.FILE_ACK, {"file_id": file_id, "seq": seq}))


def file_reject_msg(file_id: str) -> str:
    return pack(make_msg(MsgType.FILE_REJECT, {"file_id": file_id}))


def clip_msg(text: str, sender: str = None) -> str:
    return pack(make_msg(MsgType.CLIP, text, sender))


def ping_msg() -> str:
    return pack(make_msg(MsgType.PING, "", sender="system"))


def pong_msg() -> str:
    return pack(make_msg(MsgType.PONG, "", sender="system"))


def status_msg(status: str) -> str:
    return pack(make_msg(MsgType.STATUS, status, sender="system"))
