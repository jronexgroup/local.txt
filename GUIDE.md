# LT — Local Text Guide

## What is LT?

LT lets you chat between two devices on the same WiFi/LAN network. No internet required. No server needed. Just two devices and one command.

---

## Quick Start (Phase 1)

### 1. Install

```bash
pip3 install prompt_toolkit rich
chmod +x lt.py
ln -s $(pwd)/lt.py ~/.local/bin/lt
```

Make sure `~/.local/bin` is in your PATH. Run this if not:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### 2. Setup (both devices)

```bash
lt --setup
```

It will ask:

```
Peer IP: 192.168.1.105   ← enter the other device's IP
Port (Enter for 5050):     ← press Enter for default
```

Do this on **both** devices — each one enters the other's IP.

> **How to find your IP:**
> - Linux/macOS: run `ip addr` or `ifconfig`
> - Windows: run `ipconfig`
> - Look for something like `192.168.x.x`

### 3. Connect

```bash
lt
```

Run this on **both** devices. Within a few seconds you'll see:

```
Connected! Type /help for commands, /exit to quit

You:
```

Start typing. Messages appear instantly on both sides.

---

## Commands

| Command | What it does |
|---------|-------------|
| `/exit` | Leave the chat |
| `/clear` | Clear the screen |
| `/ping` | Check if connected |
| `/time` | Show current time |
| `/help` | Show all commands |

---

## What it looks like

```
Connecting to 192.168.1.105:5050...
Connected! Type /help for commands, /exit to quit

Peer (14:00): Hi there!
You (14:01): Hey! How's it going?
Peer (14:01): All good, testing LT!

You: █
```

---

## How it works (simple explanation)

1. When you run `lt`, it tries two things at once:
   - Connect to your peer's IP
   - Listen for your peer to connect to you
2. Whichever happens first wins — you're connected
3. Messages are sent as JSON over TCP
4. If WiFi drops, it automatically tries to reconnect

---

## Configuration

File: `~/.config/lt/config.json`

```json
{
  "peer_ip": "192.168.1.105",
  "port": 5050
}
```

You can edit this file directly instead of running `--setup`.

---

## Troubleshooting

**"Not configured. Run: lt --setup"**
→ Run `lt --setup` first to enter the peer's IP.

**Can't connect**
- Make sure both devices are on the **same WiFi/LAN network**
- Check that both have the **correct IP** in their config
- Disable firewalls or allow port 5050 (TCP)
- Try running `lt` on both devices at the same time

**"Port already in use"**
→ Another program is using port 5050. Use `--setup` to pick a different port (e.g. `6060`).

**Messages not showing**
→ The connection might be lost. Wait for auto-reconnect or run `lt` again.

---

## Phase 2 — Coming

- **Auto Discovery** — No need to enter IP. LT finds devices automatically.
- **Clipboard** — `/clip` to share clipboard
- **File Transfer** — `/send filename` to share files

## Phase 3 — Coming

- **Encryption** — AES-256 for secure chat
- **Password Pairing** — Pair with a code
- **Multiple Devices** — `lt list`, `lt all`

## Something special — `lt --daemon`

A future feature where LT runs in the background. When you type `lt`, the chat opens instantly — no waiting to connect.

---

## File Location

- Script: `/root/projects/localit/lt.py`
- Config: `~/.config/lt/config.json`
- Command: `lt` (symlink to the script)
