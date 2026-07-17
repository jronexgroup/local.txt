#!/usr/bin/env bash
set -e

echo "╔══════════════════════════════════╗"
echo "║   LT — Local Text Installer     ║"
echo "╚══════════════════════════════════╝"
echo ""

# Detect Python
PY=$(command -v python3 || command -v python)
if [ -z "$PY" ]; then
    echo "❌ Python not found. Install Python 3 first."
    exit 1
fi

echo "✓ Python: $($PY --version)"

# Install dependencies
echo ""
echo "Installing dependencies..."
$PY -m pip install rich prompt_toolkit cryptography --break-system-packages 2>&1 | tail -3

# Optional dependencies
echo ""
echo "Optional: install extra features?"
read -p "Install STUN (P2P mode), Tor support, Clipboard? (y/n): " extra
if [ "$extra" = "y" ] || [ "$extra" = "Y" ]; then
    $PY -m pip install pystun3 stem pyperclip --break-system-packages 2>&1 | tail -3
fi

# Copy lt.py
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo ""
echo "Installing lt command..."
chmod +x "$SCRIPT_DIR/lt.py"

# Install to ~/.local/bin
mkdir -p ~/.local/bin
if [ -f ~/.local/bin/lt ]; then
    rm ~/.local/bin/lt
fi
ln -s "$SCRIPT_DIR/lt.py" ~/.local/bin/lt

# Check PATH
if echo ":$PATH:" | grep -qv ":$HOME/.local/bin:"; then
    echo ""
    echo "⚠️  ~/.local/bin is not in your PATH."
    echo "   Add this to ~/.bashrc or ~/.zshrc:"
    echo "   export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

echo ""
echo "╔══════════════════════════════════╗"
echo "║   ✅ LT installed!               ║"
echo "║                                  ║"
echo "║   Run:  lt --setup               ║"
echo "║   Then: lt                       ║"
echo "╚══════════════════════════════════╝"
