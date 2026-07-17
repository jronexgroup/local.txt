# LT — Local Text

**Chat with friends over LAN or the internet. No server, no sign-up, no port forwarding.**

LT is a single-file Python CLI tool that uses UDP hole punching (with STUN) to create a direct encrypted connection between two devices. Works on Linux, macOS, Windows, and Android (Termux).

## Quick Start

```bash
bash setup.sh           # install dependencies + lt command
lt --setup              # enter your display name
lt                      # choose LAN or P2P → chat
```

## Features

- **LAN mode** — direct TCP connection on the same network
- **P2P mode** — UDP hole punching over the internet (no port forwarding)
- **Encryption** — AES-256-GCM with password-derived key (PBKDF2)
- **File transfer** — chunked with progress bar
- **Clipboard sharing** — send/paste clipboard contents
- **Friends history** — last 10 connections saved, auto-connect
- **Offline recovery** — auto-reconnect on disconnect
- **Command autocomplete** — type `/` to see available commands

## Commands

| Command | Description |
|---------|-------------|
| `/exit` | Quit |
| `/clear` | Clear screen |
| `/ping` | Check connection |
| `/time` | Show current time |
| `/clip` | Send clipboard contents |
| `/file <path>` | Send a file |
| `/setting` | Change settings |
| `/help` | Show all commands |

## Install

```bash
# One-line install:
bash setup.sh

# Manual:
pip3 install rich prompt_toolkit cryptography --break-system-packages
pip3 install pyperclip --break-system-packages   # optional (clipboard)
chmod +x lt.py
ln -s "$(pwd)/lt.py" ~/.local/bin/lt
```

## Usage

### 1. Setup (first time)

```bash
lt --setup
```

Enter your display name. That's it.

### 2. LAN mode (same network)

```bash
lt --lan
```

Choose **Create** (wait for friend) or **Connect** (enter friend's IP).

### 3. P2P mode (internet)

```bash
lt --p2p
```

- **Create** — share the yellow `IP:Port` with your friend
- **Join** — enter your friend's `IP:Port`
- Enter a password for encryption (both sides use the same password)

### 4. Just run `lt` (no flags)

Asks you to pick LAN or P2P, shows saved friends for auto-connect.

## How P2P works

1. Both sides get their public IP via STUN (Google, STUN Protocol, etc.)
2. The "Create" side binds a UDP socket and waits
3. The "Join" side sends UDP packets to Create's public address
4. NATs on both sides create temporary mappings
5. Packets flow directly between both devices — no relay server needed

## Files

| Path | Purpose |
|------|---------|
| `lt.py` | Main script |
| `setup.sh` | Installer |
| `~/.config/lt/settings.json` | Display name, port, download dir |
| `~/.config/lt/friends.json` | Saved connections |
| `~/Downloads/LT/` | Received files |

## License

MIT
