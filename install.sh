#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Goldvreneli — installer
# Sets up: Python venv, IB Gateway, IBC, Xvfb, .env template
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IBC_DIR="$HOME/ibc"
GATEWAY_DIR="$HOME/Jts/ibgateway"
IBC_RELEASES="https://github.com/IbcAlpha/IBC/releases/latest"
GATEWAY_URL="https://download2.interactivebrokers.com/installers/ibgateway/stable-standalone/ibgateway-stable-standalone-linux-x64.sh"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }
ask()     { echo -e "${YELLOW}[INPUT]${NC} $*"; }

# ── helpers ───────────────────────────────────────────────────────────────────
require_cmd() {
    command -v "$1" &>/dev/null || error "'$1' is required but not found. Install it and re-run."
}

check_linux() {
    [[ "$(uname -s)" == "Linux" ]] || error "This installer supports Linux only."
}

# ── steps ─────────────────────────────────────────────────────────────────────
install_system_deps() {
    info "Installing system dependencies (Xvfb, curl, unzip, python3-venv)…"
    if command -v apt-get &>/dev/null; then
        sudo apt-get update -qq
        sudo apt-get install -y xvfb curl unzip python3-venv python3-pip
    elif command -v dnf &>/dev/null; then
        sudo dnf install -y xorg-x11-server-Xvfb curl unzip python3 python3-pip
    elif command -v pacman &>/dev/null; then
        sudo pacman -Sy --noconfirm xorg-server-xvfb curl unzip python python-pip
    else
        warn "Unknown package manager — install xvfb, curl, unzip, python3-venv manually."
    fi
    success "System dependencies installed."
}

setup_venv() {
    info "Setting up Python virtual environment…"
    cd "$SCRIPT_DIR"
    if [[ ! -d venv ]]; then
        python3 -m venv venv
    fi
    venv/bin/pip install --quiet --upgrade pip
    venv/bin/pip install --quiet -r requirements.txt
    success "Python venv ready (venv/)."
}

install_ib_gateway() {
    if [[ -d "$GATEWAY_DIR" ]] && ls "$GATEWAY_DIR"/*/ibgateway &>/dev/null 2>&1; then
        success "IB Gateway already installed at $GATEWAY_DIR — skipping."
        return
    fi

    info "Downloading IB Gateway stable offline installer…"
    TMP_INSTALLER="$(mktemp /tmp/ibgateway-XXXXXX.sh)"
    curl -L --progress-bar "$GATEWAY_URL" -o "$TMP_INSTALLER"
    chmod +x "$TMP_INSTALLER"

    info "Running IB Gateway installer (silent)…"
    # -q = quiet, -dir = install location
    "$TMP_INSTALLER" -q -dir "$GATEWAY_DIR" || true
    rm -f "$TMP_INSTALLER"

    if ls "$GATEWAY_DIR"/*/ibgateway &>/dev/null 2>&1; then
        success "IB Gateway installed at $GATEWAY_DIR."
    else
        warn "IB Gateway installer finished but binary not found at $GATEWAY_DIR."
        warn "You may need to install it manually from:"
        warn "  https://www.interactivebrokers.com/en/trading/ibgateway-stable.php"
        warn "Then set GATEWAY_PATH in your .env file."
    fi
}

install_ibc() {
    if [[ -f "$IBC_DIR/gatewaystart.sh" ]]; then
        success "IBC already installed at $IBC_DIR — skipping."
        return
    fi

    info "Fetching latest IBC release URL…"
    require_cmd curl
    IBC_ZIP_URL="$(curl -sI "$IBC_RELEASES" | grep -i location | tr -d '\r' | awk '{print $2}')"
    # Build direct download URL for Linux zip
    IBC_VERSION="$(basename "$IBC_ZIP_URL")"
    IBC_DOWNLOAD="https://github.com/IbcAlpha/IBC/releases/download/${IBC_VERSION}/IBCLinux-${IBC_VERSION}.zip"

    TMP_ZIP="$(mktemp /tmp/ibc-XXXXXX.zip)"
    info "Downloading IBC ${IBC_VERSION}…"
    curl -L --progress-bar "$IBC_DOWNLOAD" -o "$TMP_ZIP" || {
        warn "Auto-download failed. Download the Linux zip manually from:"
        warn "  https://github.com/IbcAlpha/IBC/releases"
        warn "Then unzip it to $IBC_DIR and chmod +x $IBC_DIR/*.sh $IBC_DIR/scripts/*.sh"
        rm -f "$TMP_ZIP"
        return
    }

    mkdir -p "$IBC_DIR"
    unzip -q "$TMP_ZIP" -d "$IBC_DIR"
    chmod +x "$IBC_DIR"/*.sh "$IBC_DIR"/scripts/*.sh 2>/dev/null || true
    rm -f "$TMP_ZIP"
    success "IBC installed at $IBC_DIR."
}

create_env_file() {
    ENV_FILE="$SCRIPT_DIR/.env"
    if [[ -f "$ENV_FILE" ]]; then
        warn ".env already exists — skipping (edit it manually if needed)."
        return
    fi

    info "Creating .env template…"

    # Detect installed gateway version path
    GW_VERSION_PATH=""
    if ls "$GATEWAY_DIR"/*/ibgateway &>/dev/null 2>&1; then
        GW_VERSION_PATH="$(dirname "$(ls "$GATEWAY_DIR"/*/ibgateway | head -1)")"
    fi

    cat > "$ENV_FILE" <<EOF
# ── Alpaca Paper Trading ──────────────────────────────────────────────────────
ALPACA_PAPER_API_KEY=
ALPACA_PAPER_SECRET_KEY=

# ── IBKR Credentials ─────────────────────────────────────────────────────────
IBKR_USERNAME=
IBKR_PASSWORD=

# ── IBC / Gateway paths ───────────────────────────────────────────────────────
IBC_PATH=${IBC_DIR}
GATEWAY_PATH=${GW_VERSION_PATH:-$GATEWAY_DIR}
EOF
    success ".env template created — fill in your credentials."
}

print_summary() {
    echo ""
    echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  Installation complete!${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
    echo ""
    echo "  Next steps:"
    echo "  1. Fill in your credentials:"
    echo "       nano $SCRIPT_DIR/.env"
    echo ""
    echo "  2. Launch the dashboard:"
    echo "       cd $SCRIPT_DIR"
    echo "       source venv/bin/activate"
    echo "       streamlit run app.py"
    echo ""
    echo "  IBKR note: use port 4002 (paper) or 4001 (live)."
    echo "  The app will start IB Gateway automatically via IBC."
    echo ""
}

uninstall() {
    echo ""
    echo -e "${RED}╔══════════════════════════════════════════╗${NC}"
    echo -e "${RED}║   Goldvreneli Trading — Uninstaller      ║${NC}"
    echo -e "${RED}╚══════════════════════════════════════════╝${NC}"
    echo ""
    warn "This will remove:"
    echo "  - Python venv ($SCRIPT_DIR/venv/)"
    echo "  - IBC directory ($IBC_DIR/)  [if --with-ibc]"
    echo "  - IB Gateway ($GATEWAY_DIR/) [if --with-gateway]"
    echo "  - .env file ($SCRIPT_DIR/.env)"
    echo ""
    read -rp "Are you sure? [y/N] " confirm
    [[ "$confirm" =~ ^[Yy]$ ]] || { info "Aborted."; exit 0; }

    info "Removing Python venv…"
    rm -rf "$SCRIPT_DIR/venv"
    success "venv removed."

    info "Removing .env…"
    rm -f "$SCRIPT_DIR/.env"
    success ".env removed."

    if $UNINSTALL_IBC; then
        info "Removing IBC ($IBC_DIR)…"
        rm -rf "$IBC_DIR"
        success "IBC removed."
    fi

    if $UNINSTALL_GATEWAY; then
        info "Removing IB Gateway ($GATEWAY_DIR)…"
        rm -rf "$GATEWAY_DIR"
        success "IB Gateway removed."
    fi

    echo ""
    echo -e "${GREEN}Uninstall complete.${NC}"
}

# ── main ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}╔══════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║   Goldvreneli Trading — Installer        ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════╝${NC}"
echo ""

check_linux

# Parse flags
SKIP_GATEWAY=false
SKIP_IBC=false
UNINSTALL=false
UNINSTALL_IBC=false
UNINSTALL_GATEWAY=false

for arg in "$@"; do
    case $arg in
        --skip-gateway)    SKIP_GATEWAY=true ;;
        --skip-ibc)        SKIP_IBC=true ;;
        --uninstall)       UNINSTALL=true ;;
        --with-ibc)        UNINSTALL_IBC=true ;;
        --with-gateway)    UNINSTALL_GATEWAY=true ;;
        --help|-h)
            echo "Usage: ./install.sh [OPTIONS]"
            echo ""
            echo "Install options:"
            echo "  --skip-gateway     Skip IB Gateway download/install"
            echo "  --skip-ibc         Skip IBC download/install"
            echo ""
            echo "Uninstall options:"
            echo "  --uninstall        Remove venv and .env"
            echo "  --uninstall --with-ibc        Also remove IBC (~/$IBC_DIR)"
            echo "  --uninstall --with-gateway    Also remove IB Gateway (~/$GATEWAY_DIR)"
            exit 0
            ;;
    esac
done

if $UNINSTALL; then
    uninstall
    exit 0
fi

install_system_deps
setup_venv
$SKIP_GATEWAY || install_ib_gateway
$SKIP_IBC     || install_ibc
create_env_file
print_summary
