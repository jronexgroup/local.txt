# LT — Local Text Guide

**Chat with friends over LAN or Internet.** No server needed. No accounts. Just you and your friend.

---

## Quick Start

```bash
pip3 install textual pystun3 stem pyperclip --break-system-packages
lt --setup    # First time — follow the wizard
lt            # Connect and chat
```

---

## Ways to Connect

| Mode | Works | Speed | Setup |
|------|-------|-------|-------|
| **LAN** | Same WiFi | 🔥 Fast | Enter friend's IP |
| **P2P** | Anywhere on Internet | ⚡ Fast | Share a password |
| **Tor** | Anywhere, behind any firewall | 🐢 Slower | Install Tor + password |

---

## First Run (Onboarding)

When you run `lt` for the first time, you'll see the setup wizard:

1. **Choose mode** — LAN, P2P, or Tor
2. **Enter display name** — How you appear to your friend
3. **Enter details** — IP for LAN, password for P2P/Tor

After setup, just run `lt` to connect.

---

## The Chat Screen (TUI)

```
┌──────────────────────────────────────────────────────────┐
│  LT — Local Text                         ⭘      07:15   │
├──────────────────────────────────────────────────────────┤
│ ┌────────────────────────────────────────────────────────┐ │
│ │ 14:00 Kali: Hey! This UI is sick!                     │ │
│ │ 14:01 You: Right? P2P is so fast                      │ │
│ │ 📁 Kali sent: photo.jpg (2.4 MB)                      │ │
│ │                                                        │ │
│ │                                                        │ │
│ ├────────────────────────────────────────────────────────┤ │
│ │ Type message...                          [Send] [📎]  │ │
├──────────────────────────────────────────────────────────┤ │
│ Mode: P2P | Ctrl+Q:Quit /cmd Ctrl+F:File Ctrl+S:Settings │
└──────────────────────────────────────────────────────────┘
```

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+Q` | Quit |
| `Ctrl+F` | Send file |
| `Ctrl+V` | Send clipboard |
| `Ctrl+S` | Open settings |
| `Ctrl+L` | Clear chat |
| `Ctrl+N` | Connect to new peer |
| `/cmd` | Type any command below |

---

## Commands

Type any of these in the chat input and press Enter:

| Command | What it does |
|---------|-------------|
| `/exit` | Quit the chat |
| `/clear` | Clear screen |
| `/ping` | Check connection |
| `/time` | Show current time |
| `/clip` | Send your clipboard to friend |
| `/file photo.jpg` | Send a file |
| `/setting` | Open settings panel |
| `/connect` | Connect to a new peer |
| `/help` | Show all commands |

---

## File Transfer

```
You:                    Friend:
  /file photo.jpg         📁 Incoming file:
                          Kali wants to send:
                          photo.jpg (2.4 MB)

                          [Accept]  [Reject]

  [████████░░] 55%        → Accepted
  1.2 MB/s                [████████████████] 100%
                          ✓ Saved to ~/Downloads/LT/
```

- Files are sent in chunks with progress bar
- Saved to `~/Downloads/LT/` by default
- Change download folder in Settings

## Clipboard

```
You type /clip:
  → Your clipboard content is sent to friend
  → Friend sees: 📋 Kali sent clipboard
  → Auto-copied to their clipboard
  → Friend presses Ctrl+V anywhere
```

---

## Offline Messages

If your friend is offline when you send a message:

```
📨 Pending (2 messages)
  → Saved for later delivery
```

When friend reconnects:

```
✅ Kali-PC connected
📨 Delivering 2 pending messages... [████████████████] 100%
─── 2 messages delivered ───
You (14:00): Hey! How are you?
You (14:01): sent photo.jpg (2.4 MB)
```

---

## Settings (Ctrl+S or /setting)

```
╭─ Settings ─────────────────────────────────────────────╮
│                                                        │
│  Display Name:    [Kali                      ]         │
│  Theme:           ● Dark  ○ Light                     │
│  Show Timestamps: [✓]                                   │
│  Auto-Reconnect:  [✓]                                   │
│  Auto-Accept Files: [ ]                                 │
│  Download Dir:    [~/Downloads/LT          ]           │
│                                                        │
│  [Save]  [Reset]  [Cancel]                              │
╰────────────────────────────────────────────────────────╯
```

---

## P2P Mode (Internet — Direct)

**Fastest way to chat over Internet.** Uses STUN to discover your public IP and UDP hole punching for a direct connection.

```
lt --setup          → Choose P2P → enter password
lt --p2p            → Connect

Your public address: 203.0.113.5:54321
Share this with your friend.

Enter friend's address: 203.0.113.10:54321
→ Connected! 🔒 Encrypted
```

### Why P2P is fast

```
P2P:     You ────────────────────────── Friend    1 hop → 10-50ms
Tor:     You ─► Guard ─► Middle ─► Exit ─► Friend  3 hops → 200ms-2s
```

---

## Tor Mode (Internet — Any Firewall)

**Works everywhere.** Even behind strict firewalls or corporate networks. Requires Tor installed.

```bash
sudo apt install tor       # Install Tor
lt --setup                 → Choose Tor → enter password
lt --tor                   → Connect

Your .onion: abcdef123456.onion:5050
Share this with your friend.
```

---

## LAN Mode (Same WiFi)

No setup needed after the first time.

```bash
lt --setup  → Choose LAN → enter friend's IP
lt          → Connect
```

Both devices must be on the same network.

---

## Encryption

All messages are **encrypted end-to-end** with AES-256-GCM.

- Your pairing password is used to derive the encryption key
- Messages are encrypted before sending
- The Tor/relay/peer cannot read your messages
- 🔒 Lock icon shows encryption is active

---

## File Structure

```
~/.local/bin/lt              → Command (symlink)
~/.config/lt/settings.json   → Your settings
~/.config/lt/offline/        → Pending messages
~/Downloads/LT/              → Received files
```

---

## Troubleshooting

**App doesn't start**
```bash
pip3 install textual pystun3 stem pyperclip --break-system-packages
```

**Can't connect over P2P**
- Make sure both have the same pairing password
- Check that STUN server is accessible (default: `stun.l.google.com:19302`)
- Some NAT types (Symmetric) don't support hole punching → try Tor mode

**Can't connect over Tor**
- Run `sudo apt install tor` and make sure Tor is running
- Check Tor SOCKS port (default: 9050)
- Check Tor Control port (default: 9051)

**Can't connect over LAN**
- Both devices must be on the same WiFi/LAN
- Check that you entered the correct IP
- Try disabling firewall or allowing port 5050

**Messages not showing**
- Wait for auto-reconnect
- Type `/ping` to check connection
- Run `lt` again

---

## Coming in Future

| Feature | Status |
|---------|--------|
| ~~Phase 1 (LAN Chat)~~ | ✅ Done |
| ~~TUI (Graphical Terminal)~~ | ✅ Done |
| ~~P2P over Internet~~ | ✅ Done |
| ~~Tor Mode~~ | ✅ Done |
| ~~File Transfer~~ | ✅ Done |
| ~~Clipboard Share~~ | ✅ Done |
| ~~Offline Messages~~ | ✅ Done |
| ~~Settings Panel~~ | ✅ Done |
| Auto Discovery (no IP needed) | 🔜 Coming |
| Multiple Devices | 🔜 Coming |
| Broadcast Message | 🔜 Coming |
| Notification Sound | 🔜 Coming |
| Drag & Drop Files | 🔜 Coming |
