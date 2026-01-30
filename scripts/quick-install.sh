#!/bin/bash
# Quick install script for D&D Initiative Tracker
# This script clones the repository, installs dependencies, and sets up the application

set -euo pipefail

INSTALL_DIR="$HOME/.local/share/dnd-initiative-tracker"
REPO_URL="https://github.com/jeeves-jeevesenson/dnd-initiative-tracker.git"

echo "=========================================="
echo "D&D Initiative Tracker - Quick Install"
echo "=========================================="
echo ""

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed. Please install Python 3.9 or higher."
    exit 1
fi

# Check Python version
PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
REQUIRED_VERSION="3.9"

if ! python3 -c "import sys; exit(0 if sys.version_info >= (3, 9) else 1)"; then
    echo "Error: Python $PYTHON_VERSION found, but Python $REQUIRED_VERSION or higher is required."
    exit 1
fi

echo "✓ Python $PYTHON_VERSION found"

# Check if git is installed
if ! command -v git &> /dev/null; then
    echo "Error: git is not installed. Please install git first."
    exit 1
fi

echo "✓ Git found"

# Create install directory if it doesn't exist
mkdir -p "$INSTALL_DIR"

# Clone or update the repository
if [ -d "$INSTALL_DIR/.git" ]; then
    echo ""
    echo "Updating existing installation..."
    cd "$INSTALL_DIR"
    git pull
else
    echo ""
    echo "Cloning repository to $INSTALL_DIR..."
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

echo ""
echo "Creating virtual environment..."
python3 -m venv .venv

echo "Activating virtual environment..."
source .venv/bin/activate

echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "Creating launcher script..."
LAUNCHER="$HOME/.local/bin/dnd-initiative-tracker"
mkdir -p "$HOME/.local/bin"

cat > "$LAUNCHER" << EOF
#!/bin/bash
cd "$INSTALL_DIR"
source .venv/bin/activate
python dnd_initative_tracker.py "\$@"
EOF

chmod +x "$LAUNCHER"

# Check if ~/.local/bin is in PATH
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo ""
    echo "⚠️  Note: $HOME/.local/bin is not in your PATH"
    echo "   Add this line to your ~/.bashrc or ~/.zshrc:"
    echo "   export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo ""
fi

echo ""
echo "=========================================="
echo "✓ Installation complete!"
echo "=========================================="
echo ""
echo "To run the D&D Initiative Tracker:"
echo "  1. Run: dnd-initiative-tracker"
echo "  2. Or: $LAUNCHER"
echo "  3. Or navigate to $INSTALL_DIR and run:"
echo "     source .venv/bin/activate && python dnd_initative_tracker.py"
echo ""
