# LT — Local Text Guide

**Chat with friends over LAN or Internet.** No server needed. No accounts.

```
lt --setup     First time setup (works any time)
lt             Connect and chat
lt --lan       Force LAN mode
lt --p2p       Force P2P (Internet) mode
lt --tor       Force Tor mode
lt --help      Show help
```

---

## Install

```bash
# One-command install:
bash setup.sh

# Or manually:
pip install rich prompt_toolkit cryptography --break-system-packages
pip install pystun3 stem pyperclip --break-system-packages   # optional
chmod +x lt.py
ln -s $(pwd)/lt.py ~/.local/bin/lt
```

---

## First Time

```bash
lt --setup
```

It will ask:
```
Connection mode:     lan / p2p / tor
Display name:        Your name
Peer IP:             192.168.1.105   (for LAN)
Pairing password:    secret          (for P2P/Tor)
Port:                5050
```

Then:
```bash
lt    # connect and chat
```

---

## What You See

```
╭──────────────────────────────────────────────────────────────╮
│ ✓ Connected • Mode: LAN • Type /help for commands, /exit    │
╰──────────────────────────────────────────────────────────────╯

 Kali (14:00): Hey! What's up?
 You (14:01): Nothing much, testing LT!

You: █
```

- **Green** = Peer's messages
- **Blue** = Your messages
- **Yellow** = System status
- ✓ / ✗ / ⟳ = Connection indicators

---

## Commands

| Command | What it does |
|---------|-------------|
| `/exit` | Quit |
| `/clear` | Clear screen |
| `/ping` | Check connection |
| `/time` | Show current time |
| `/clip` | Send clipboard to friend |
| `/file <path>` | Send a file |
| `/setting` | Open settings menu |
| `/connect` | Connect to a new peer |
| `/help` | Show all commands |

---

## 3 Connection Modes

### LAN — Same WiFi
```
Both run:    lt
No config needed after --setup.
Auto-connects by trying to connect + listen.
```

### P2P — Internet (Direct, Fastest)
```
1. lt --setup → choose p2p → enter password
2. lt --p2p
3. Shows: Your public address: 203.0.113.5:54321
4. Share that with your friend
5. Enter friend's address when prompted
6. Connected! Direct P2P encrypted chat.
```

### Tor — Internet (Any Firewall)
```
1. Install Tor: sudo apt install tor
2. lt --setup → choose tor → enter password
3. lt --tor
4. Shows: Your .onion: abcdef.onion:5050
5. Share with friend, enter theirs
6. Connected over Tor.
```

---

## File Transfer

```bash
You:   /file photo.jpg
       Sending: photo.jpg (2.4 MB)
       [████████████████░░░░] 80%

Friend:
       📁 Kali wants to send: photo.jpg (2.4 MB)
       Accept? (y/n): y
       ✓ Received: photo.jpg → ~/Downloads/LT/photo.jpg
```

## Clipboard

```bash
You:   /clip
       ✓ Clipboard sent (245 chars)

Friend:
       📋 Kali sent clipboard
       ✓ Copied to your clipboard
```

---

## Offline Messages

If friend is offline when you send:

```
📨 Saved for later (friend offline)
```

When friend reconnects:

```
📨 Delivered 2 pending message(s)
```

Messages are saved to `~/.config/lt/offline/` and auto-sent on reconnect.

---

## Encryption

Messages are **encrypted end-to-end** with AES-256-GCM when using P2P or Tor mode with a pairing password. The LAN mode is unencrypted (local network only).

---

## Files

| File | Purpose |
|------|---------|
| `lt.py` | The main script (~600 lines) |
| `setup.sh` | Installer script |
| `GUIDE.md` | This guide |
| `~/.config/lt/settings.json` | Config file |
| `~/.config/lt/offline/` | Pending messages |
| `~/Downloads/LT/` | Received files |

---

## Troubleshooting

**lt --setup doesn't run?**
→ It always runs. Just type `lt --setup` any time.

**Can't see your own messages?**
→ They appear right after you type: `You (HH:MM): message`

**No connection indicator?**
→ You'll see: ✓ Connected / ✗ Disconnected / ⟳ Reconnecting...

**Can't connect over P2P?**
→ Try Tor mode instead. Some NAT types don't support P2P hole punching.

**Can't connect over Tor?**
→ Run `sudo apt install tor && sudo systemctl start tor`
