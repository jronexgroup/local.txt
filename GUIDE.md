# LT — Guide

## Install

```bash
bash setup.sh
```

Or manually:

```bash
pip3 install rich prompt_toolkit cryptography --break-system-packages
pip3 install pyperclip --break-system-packages   # optional (clipboard)
chmod +x lt.py
ln -s "$(pwd)/lt.py" ~/.local/bin/lt
```

## Setup (first time)

```bash
lt --setup
```

Enter your display name. That's all.

## Chat

```bash
lt              # choose mode interactively
lt --lan        # force LAN mode
lt --p2p        # force P2P mode
```

Type your message and press Enter to send.

### Commands

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

Type `/` to see command suggestions.

### Friends

When you connect to someone, they're saved to your friends list (last 10). Next time you run `lt`, select them for auto-connect.

## LAN Mode

Both devices on the same WiFi/network.

```bash
lt --lan
# Choose 1 (Create) or 2 (Connect)
```

- **Create** → Shows your IP, waits for incoming connection
- **Connect** → Enter friend's IP, connects to them

## P2P Mode

Devices on different networks.

```bash
lt --p2p
# Choose 1 (Create) or 2 (Join)
```

- **Create** → Shows your public IP:Port (via STUN). Share this with your friend.
- **Join** → Enter friend's IP:Port

Both sides must enter the same password. Messages are encrypted with AES-256-GCM.

### If STUN fails

If your public IP can't be detected, LT shows your local address and asks you to enter your public IP manually. You can find it by visiting [whatismyip.com](https://whatismyip.com).

## File Transfer

```bash
/file photo.jpg
```

Sender sees a progress bar. Receiver is prompted to accept. Files land in `~/Downloads/LT/`.

## Clipboard

```bash
/clip
```

Sends your current clipboard contents to the peer. Their clipboard is updated automatically (requires `pyperclip`).

## Encryption

P2P mode encrypts all messages with AES-256-GCM. The key is derived from your shared password using PBKDF2 (100,000 iterations).

LAN mode sends unencrypted (it's your local network).

## Settings

```bash
/setting
```

Change your display name, port, or download directory.

## Troubleshooting

**Connection fails in P2P mode:**
- Make sure both sides entered the same password
- Try swapping Create/Join roles (the machine with STUN working should Create)
- Some restrictive NATs (symmetric NAT) block hole punching — try LAN mode instead

**Connection fails in LAN mode:**
- Make sure both devices are on the same network
- Check the IP address is correct (`ip addr` on Linux, `ipconfig` on Windows)
- Check firewall settings (port 5050)

**STUN fails:**
- Try again (network may be temporary)
- Visit whatismyip.com and enter your public IP manually
- Some networks block STUN — use P2P on a different network or use LAN mode

## Files

| File | Purpose |
|------|---------|
| `lt.py` | Main script |
| `setup.sh` | Installer |
| `~/.config/lt/settings.json` | Config |
| `~/.config/lt/friends.json` | Friends list |
| `~/Downloads/LT/` | Received files |
