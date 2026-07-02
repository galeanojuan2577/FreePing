#!/usr/bin/env bash
# FreePing Installer — One-command setup
# Usage: curl -fsSL https://raw.githubusercontent.com/youruser/freeping/main/install.sh | bash
# Or:    bash install.sh

set -euo pipefail

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC} $1"; }
ok()    { echo -e "${GREEN}[OK]${NC}   $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
fail()  { echo -e "${RED}[FAIL]${NC} $1"; exit 1; }

echo ""
echo -e "${GREEN}╔══════════════════════════════╗${NC}"
echo -e "${GREEN}║     FreePing Installer       ║${NC}"
echo -e "${GREEN}║  Your free gaming VPN        ║${NC}"
echo -e "${GREEN}╚══════════════════════════════╝${NC}"
echo ""

# --- Detect OS ---
OS="$(uname -s)"
case "$OS" in
    Linux)   OS="linux" ;;
    Darwin)  OS="macos" ;;
    *)       fail "Unsupported OS: $OS. FreePing requires Linux or macOS." ;;
esac
info "Detected OS: $OS"

# --- Check Python ---
PYTHON=""
for cmd in python3.12 python3.13 python3; do
    if command -v "$cmd" &>/dev/null; then
        PY_VER=$("$cmd" --version 2>&1 | grep -oP '\d+\.\d+')
        MAJOR=$(echo "$PY_VER" | cut -d. -f1)
        MINOR=$(echo "$PY_VER" | cut -d. -f2)
        if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 12 ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    fail "Python 3.12+ is required but not found.
Install it:
  Linux:  sudo apt install python3.12 python3.12-venv  (or use your package manager)
  macOS:  brew install python@3.12
  Or:     https://www.python.org/downloads/"
fi

PY_VER=$("$PYTHON" --version)
ok "Found $PY_VER at $(command -v "$PYTHON")"

# --- Detect package manager ---
INSTALL_CMD=""
if command -v apt &>/dev/null; then
    INSTALL_CMD="sudo apt install -y"
elif command -v dnf &>/dev/null; then
    INSTALL_CMD="sudo dnf install -y"
elif command -v pacman &>/dev/null; then
    INSTALL_CMD="sudo pacman -S --noconfirm"
elif command -v brew &>/dev/null; then
    INSTALL_CMD="brew install"
fi

# --- Check/setup venv ---
if [ "$OS" = "linux" ] && ! "$PYTHON" -c "import venv" 2>/dev/null; then
    warn "Python venv module not found. Installing..."
    if [ -n "$INSTALL_CMD" ]; then
        $INSTALL_CMD python3-venv python3-pip 2>/dev/null || true
    fi
fi

# --- Determine install directory ---
INSTALL_DIR="${FREEPING_HOME:-$HOME/.freeping}"
if [ -d "$INSTALL_DIR" ]; then
    info "FreePing already installed at $INSTALL_DIR. Updating..."
else
    info "Installing to $INSTALL_DIR"
fi

mkdir -p "$INSTALL_DIR"

# --- Find FreePing source ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -f "$SCRIPT_DIR/pyproject.toml" ]; then
    INSTALL_SOURCE="$SCRIPT_DIR"
elif command -v git &>/dev/null; then
    REPO_DIR="$INSTALL_DIR/repo"
    if [ ! -d "$REPO_DIR" ]; then
        info "Cloning FreePing from GitHub..."
        git clone --depth 1 https://github.com/diegogaleano/freeping.git "$REPO_DIR"
    fi
    INSTALL_SOURCE="$REPO_DIR"
else
    fail "Cannot find FreePing source. Clone the repo or run install.sh from the project root."
fi

# --- Create virtual environment ---
VENV_DIR="$INSTALL_DIR/venv"
if [ ! -d "$VENV_DIR" ]; then
    info "Creating virtual environment..."
    "$PYTHON" -m venv "$VENV_DIR"
fi

ok "Virtual environment ready"

# --- Install dependencies ---
info "Installing FreePing and dependencies..."
if [ -f "$INSTALL_SOURCE/pyproject.toml" ]; then
    "$VENV_DIR/bin/pip" install -e "$INSTALL_SOURCE[gui]" --quiet 2>/dev/null || \
    "$VENV_DIR/bin/pip" install -e "$INSTALL_SOURCE" --quiet
else
    "$VENV_DIR/bin/pip" install freeping[gui] 2>/dev/null || \
    warn "pip install failed. You may need to install manually."
fi

ok "FreePing installed"

# --- Create launchers ---
BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"

# Main launcher: "Freeping" (capital F)
LAUNCHER="$BIN_DIR/Freeping"
cat > "$LAUNCHER" << 'LAUNCHER_EOF'
#!/usr/bin/env bash
export FREEPING_HOME="${FREEPING_HOME:-$HOME/.freeping}"
exec "$FREEPING_HOME/venv/bin/Freeping" "$@"
LAUNCHER_EOF
chmod +x "$LAUNCHER"

# Also "freeping" (lowercase) as symlink for compatibility
ln -sf "Freeping" "$BIN_DIR/freeping"

ok "Launcher created: Freeping (y freeping como alias)"

# Desktop entry for Linux
if [ "$OS" = "linux" ]; then
    DESKTOP_DIR="$HOME/.local/share/applications"
    mkdir -p "$DESKTOP_DIR"
    cat > "$DESKTOP_DIR/FreePing.desktop" << DESKTOP_EOF
[Desktop Entry]
Name=FreePing
Comment=Reducción de latencia para juegos via Oracle Cloud + WireGuard
Exec=$BIN_DIR/Freeping
Icon=network-server
Terminal=false
Type=Application
Categories=Network;Game;Utility;
StartupWMClass=FreePing
DESKTOP_EOF
    ok "Desktop entry created: FreePing"
fi

# --- Add ~/.local/bin to PATH if needed ---
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    SHELL_CONFIG=""
    case "$SHELL" in
        */zsh) SHELL_CONFIG="$HOME/.zshrc" ;;
        */bash) SHELL_CONFIG="$HOME/.bashrc" ;;
    esac
    if [ -n "$SHELL_CONFIG" ]; then
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$SHELL_CONFIG"
        ok "Added ~/.local/bin to PATH in $SHELL_CONFIG"
    fi
fi

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  FreePing installed successfully!       ║${NC}"
echo -e "${GREEN}║                                          ║${NC}"
echo -e "${GREEN}║  Run it:  Freeping                          ║${NC}"
echo -e "${GREEN}║  Or:     freeping                          ║${NC}"
echo -e "${GREEN}║                                          ║${NC}"
echo -e "${GREEN}║  First time? The setup wizard will       ║${NC}"
echo -e "${GREEN}║  guide you through creating your free    ║${NC}"
echo -e "${GREEN}║  Oracle Cloud VPS.                       ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
echo ""
