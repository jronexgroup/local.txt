# LT — Local Text Guide

**Chat with friends over LAN or Internet.** No server needed.

```
lt --setup     Configure (works any time)
lt             Connect and chat
lt --lan       Force LAN mode
lt --p2p       Force P2P mode
lt --help      Show help
```

---

## Install

```bash
# One command:
bash setup.sh

# Or manually:
pip3 install rich prompt_toolkit cryptography --break-system-packages
pip3 install pyperclip --break-system-packages   # optional (clipboard)
chmod +x lt.py
ln -s $(pwd)/lt.py ~/.local/bin/lt
```

---

## Setup

```bash
lt --setup
```

Follow the wizard. When done, just run `lt`.

---

## LAN Mode (Same WiFi)

```
lt --setup     → Choose LAN → enter friend's IP
lt             → Connect
```

Both must be on the same network. One side connects, the other listens.

---

## P2P Mode (Internet)

### Create (Friend waits for you)

```bash
lt --setup     → Choose P2P → set password
lt
  → Choose: 1. Create  2. Join
  → Pick: 1
  → Shows: Your session code: X7K3F9
  → Share code + your IP:Port with friend
  → Waiting for connection...
```

### Join (Connect to friend)

```bash
lt
  → Choose: 2. Join
  → Enter friend's IP: 203.0.113.5
  → Enter port: 5050
  → Connected!
```

---

## Commands

| Command | What it does |
|---------|-------------|
| `/exit` | Quit |
| `/clear` | Clear screen |
| `/ping` | Check connection |
| `/time` | Show time |
| `/clip` | Send clipboard |
| `/file <path>` | Send a file |
| `/setting` | Settings menu |
| `/help` | Show all commands |

---

## What You See

```
== LT ==
✓ Connected
--- Connected ---
 Kali (14:00): Hey! What's up?
 TestPC (14:01): Nothing much!

> █
```

- Green = Peer messages
- Blue = Your messages  
- ✓ Connected / ✗ Disconnected / ⟳ Reconnecting...

---

## File Transfer

```
> /file photo.jpg
  sending: photo.jpg (2.4 MB)
  [████████████░░] 60%
  sent: photo.jpg
```

Receiver:
```
  Incoming: photo.jpg (2.4 MB)
  Accept? (y/n): y
  received: photo.jpg -> ~/Downloads/LT/photo.jpg
```

---

## Clipboard

```
> /clip
  clip sent (245 chars)
```

---

## Files

| File | Purpose |
|------|---------|
| `lt.py` | Main script |
| `setup.sh` | Installer |
| `~/.config/lt/settings.json` | Config |
| `~/Downloads/LT/` | Received files |
