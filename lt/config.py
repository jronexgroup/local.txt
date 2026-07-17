import json
import os
import platform

CONFIG_DIR = os.path.expanduser("~/.config/lt")
CONFIG_FILE = os.path.join(CONFIG_DIR, "settings.json")
OFFLINE_DIR = os.path.join(CONFIG_DIR, "offline")

DEFAULTS = {
    "mode": "lan",
    "peer_ip": "",
    "port": 5050,
    "pair_password": "",
    "display_name": platform.node() or "MyDevice",
    "theme": "dark",
    "stun_server": "stun.l.google.com:19302",
    "auto_reconnect": True,
    "save_chat_log": False,
    "auto_accept_files": False,
    "download_dir": os.path.expanduser("~/Downloads/LT"),
    "notification_sound": True,
    "show_timestamps": True,
    "p2p_port": 0,
    "tor_enabled": False,
    "tor_socks_port": 9050,
    "tor_control_port": 9051,
}


def ensure_dirs():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(OFFLINE_DIR, exist_ok=True)


def load():
    ensure_dirs()
    if not os.path.exists(CONFIG_FILE):
        return dict(DEFAULTS)
    with open(CONFIG_FILE) as f:
        data = json.load(f)
    merged = dict(DEFAULTS)
    merged.update(data)
    return merged


def save(data):
    ensure_dirs()
    merged = dict(DEFAULTS)
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            existing = json.load(f)
        merged.update(existing)
    merged.update(data)
    with open(CONFIG_FILE, "w") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)


def get(key, default=None):
    return load().get(key, default)


def set_key(key, value):
    data = load()
    data[key] = value
    save(data)


def is_configured():
    cfg = load()
    if cfg["mode"] == "lan":
        return bool(cfg["peer_ip"])
    if cfg["mode"] == "p2p":
        return bool(cfg["pair_password"])
    if cfg["mode"] == "tor":
        return bool(cfg["pair_password"])
    return False
