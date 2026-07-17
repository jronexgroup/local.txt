#!/usr/bin/env bash
set -e

echo "╔══════════════════════════════════╗"
echo "║   LT — Local Text Installer     ║"
echo "╚══════════════════════════════════╝"
echo ""

PY=$(command -v python3 || command -v python)
if [ -z "$PY" ]; then
    echo "❌ Python not found. Install Python 3 first."
    exit 1
fi

echo "✓ Python: $($PY --version)"
echo ""

# Install dependencies
echo "Installing dependencies..."
$PY -m pip install rich prompt_toolkit cryptography --break-system-packages 2>&1 | tail -3

echo ""
echo "Install clipboard support? (y/n)"
read -p "> " clip
if [ "$clip" = "y" ] || [ "$clip" = "Y" ]; then
    $PY -m pip install pyperclip --break-system-packages 2>&1 | tail -3
fi

# Install lt command
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo ""
echo "Installing lt command..."
chmod +x "$SCRIPT_DIR/lt.py"

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
