#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Goldvreneli — installer
# Usage: ./goldvreneli-install.sh [OPTIONS] [TARGET_DIR]
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_URL="https://github.com/Whichcraft/goldvreneli.git"
# Component paths are set after INSTALL_DIR is resolved (see bottom of script)
IBC_DIR=""
GATEWAY_DIR=""
IBC_RELEASES="https://github.com/IbcAlpha/IBC/releases/latest"
GATEWAY_URL="https://download2.interactivebrokers.com/installers/ibgateway/stable-standalone/ibgateway-stable-standalone-linux-x64.sh"

# Production files only — no dev files deployed
PROD_FILES=(
    goldvreneli.py
    core.py
    autotrader.py
    portfolio.py
    scanner.py
    replay.py
    gateway_manager.py
    version.py
    requirements.txt
    goldvreneli-install.sh
)

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

require_cmd() { command -v "$1" &>/dev/null || error "'$1' is required but not installed."; }
check_linux() { [[ "$(uname -s)" == "Linux" ]] || error "This installer supports Linux only."; }

# ── copy production files ──────────────────────────────────────────────────────
deploy_files() {
    local src="$1" dst="$2"
    [[ "$src" == "$dst" ]] && return   # already in place
    info "Deploying production files to $dst…"
    mkdir -p "$dst"
    for f in "${PROD_FILES[@]}"; do
        if [[ -f "$src/$f" ]]; then
            cp "$src/$f" "$dst/$f"
        else
            warn "Source file not found, skipping: $f"
        fi
    done
    chmod +x "$dst/goldvreneli-install.sh"
    success "Production files deployed (dev files excluded)."
}

# ── system deps ───────────────────────────────────────────────────────────────
install_system_deps() {
    info "Installing system dependencies (Xvfb, curl, unzip, git, python3-venv)…"
    if command -v apt-get &>/dev/null; then
        sudo apt-get update -qq
        sudo apt-get install -y xvfb curl unzip git python3-venv python3-pip
    elif command -v dnf &>/dev/null; then
        sudo dnf install -y xorg-x11-server-Xvfb curl unzip git python3 python3-pip
    elif command -v pacman &>/dev/null; then
        sudo pacman -Sy --noconfirm xorg-server-xvfb curl unzip git python python-pip
    else
        warn "Unknown package manager — install xvfb, curl, unzip, git, python3-venv manually."
    fi
    success "System dependencies installed."
}

# ── venv ──────────────────────────────────────────────────────────────────────
setup_venv() {
    info "Setting up Python virtual environment…"
    cd "$INSTALL_DIR"
    if [[ ! -d venv ]]; then
        python3 -m venv venv
    fi
    venv/bin/pip install --quiet --upgrade pip
    venv/bin/pip install --quiet -r requirements.txt
    success "Python venv ready."
}

# ── IB Gateway ────────────────────────────────────────────────────────────────
# Version is stored in $GATEWAY_DIR/.gw_version after each install so we can
# detect whether IBKR is serving a newer build before downloading again.

_gw_latest_version() {
    # Follow redirect to get the effective URL, then parse the version token.
    # e.g. …/ibgateway-10.19.2h-standalone-linux-x64.sh → "10.19.2h"
    local url
    url="$(curl -s -o /dev/null -w '%{url_effective}' -L "$GATEWAY_URL" 2>/dev/null)"
    basename "$url" | grep -oP '(?<=ibgateway-)[\w.]+(?=-standalone)' || true
}

_gw_version_gt() {
    # Returns 0 (true) if $1 is strictly greater than $2 using version sort.
    # Handles alphanumeric suffixes (e.g. 10.19.2h > 10.19.1e).
    [[ "$1" == "$2" ]] && return 1
    local highest
    highest="$(printf '%s\n%s\n' "$1" "$2" | sort -V | tail -1)"
    [[ "$highest" == "$1" ]]
}

install_ib_gateway() {
    local GW_VERSION_FILE="$GATEWAY_DIR/.gw_version"
    local installed_ver="" latest_ver=""

    if ls "$GATEWAY_DIR"/*/ibgateway &>/dev/null 2>&1; then
        # Already installed — check whether a strictly newer build is available
        [[ -f "$GW_VERSION_FILE" ]] && installed_ver="$(cat "$GW_VERSION_FILE")"
        info "IB Gateway installed${installed_ver:+ (${installed_ver})} — checking for updates…"
        latest_ver="$(_gw_latest_version)"

        if [[ -z "$latest_ver" ]]; then
            # Cannot determine latest version from URL — skip conservatively
            success "IB Gateway already installed — skipping download (cannot determine latest version)."
            return
        fi
        if [[ -z "$installed_ver" ]]; then
            # No version stamp on disk — skip conservatively; user can --update explicitly
            success "IB Gateway already installed (version unknown) — skipping download."
            return
        fi
        if ! _gw_version_gt "$latest_ver" "$installed_ver"; then
            success "IB Gateway is up to date (${installed_ver}) — skipping download."
            return
        fi
        info "Newer version available: ${latest_ver} (installed: ${installed_ver}) — updating…"
    else
        info "IB Gateway not found — downloading…"
        latest_ver="$(_gw_latest_version)"
    fi

    TMP_INSTALLER="$(mktemp /tmp/ibgateway-XXXXXX.sh)"
    curl -L --progress-bar "$GATEWAY_URL" -o "$TMP_INSTALLER"
    chmod +x "$TMP_INSTALLER"
    info "Running IB Gateway installer (silent)…"
    "$TMP_INSTALLER" -q -dir "$GATEWAY_DIR" || true
    rm -f "$TMP_INSTALLER"

    if ls "$GATEWAY_DIR"/*/ibgateway &>/dev/null 2>&1; then
        [[ -n "$latest_ver" ]] && echo "$latest_ver" > "$GW_VERSION_FILE"
        success "IB Gateway ${latest_ver:-installed} at $GATEWAY_DIR."
    else
        warn "IB Gateway binary not found after install. Set GATEWAY_PATH in .env manually."
        warn "Download from: https://www.interactivebrokers.com/en/trading/ibgateway-stable.php"
    fi
}

# ── IBC ───────────────────────────────────────────────────────────────────────
install_ibc() {
    if [[ -f "$IBC_DIR/gatewaystart.sh" ]]; then
        success "IBC already installed at $IBC_DIR — skipping."
        return
    fi
    info "Fetching latest IBC release…"
    require_cmd curl
    IBC_ZIP_URL="$(curl -sI "$IBC_RELEASES" | grep -i location | tr -d '\r' | awk '{print $2}')"
    IBC_VERSION="$(basename "$IBC_ZIP_URL")"
    IBC_DOWNLOAD="https://github.com/IbcAlpha/IBC/releases/download/${IBC_VERSION}/IBCLinux-${IBC_VERSION}.zip"
    TMP_ZIP="$(mktemp /tmp/ibc-XXXXXX.zip)"
    info "Downloading IBC ${IBC_VERSION}…"
    curl -L --progress-bar "$IBC_DOWNLOAD" -o "$TMP_ZIP" || {
        warn "Auto-download failed. Download manually from: https://github.com/IbcAlpha/IBC/releases"
        warn "Unzip to $IBC_DIR and run: chmod +x $IBC_DIR/*.sh $IBC_DIR/scripts/*.sh"
        rm -f "$TMP_ZIP"; return
    }
    mkdir -p "$IBC_DIR"
    unzip -q "$TMP_ZIP" -d "$IBC_DIR"
    chmod +x "$IBC_DIR"/*.sh "$IBC_DIR"/scripts/*.sh 2>/dev/null || true
    rm -f "$TMP_ZIP"
    success "IBC installed at $IBC_DIR."
}

# ── patch stale .env paths ────────────────────────────────────────────────────
patch_env_paths() {
    local ENV_FILE="$INSTALL_DIR/.env"
    [[ -f "$ENV_FILE" ]] || return
    local changed=false
    # Replace any IBC_PATH that doesn't already point inside INSTALL_DIR
    if grep -q "^IBC_PATH=" "$ENV_FILE"; then
        local cur_ibc
        cur_ibc="$(grep "^IBC_PATH=" "$ENV_FILE" | cut -d= -f2- | tr -d '"' | sed "s|~|$HOME|g")"
        if [[ "$cur_ibc" != "$IBC_DIR" ]]; then
            sed -i "s|^IBC_PATH=.*|IBC_PATH=${IBC_DIR}|" "$ENV_FILE"
            changed=true
        fi
    fi
    # Replace any GATEWAY_PATH that doesn't already point inside INSTALL_DIR
    if grep -q "^GATEWAY_PATH=" "$ENV_FILE"; then
        local cur_gw
        cur_gw="$(grep "^GATEWAY_PATH=" "$ENV_FILE" | cut -d= -f2- | tr -d '"' | sed "s|~|$HOME|g")"
        if [[ "$cur_gw" != "$GATEWAY_DIR"* ]]; then
            local gw_versioned
            gw_versioned="$(ls -d "$GATEWAY_DIR"/*/ 2>/dev/null | head -1)"
            sed -i "s|^GATEWAY_PATH=.*|GATEWAY_PATH=${gw_versioned:-$GATEWAY_DIR}|" "$ENV_FILE"
            changed=true
        fi
    fi
    $changed && success ".env paths updated to install directory ($INSTALL_DIR)." || true
}

# ── .env ──────────────────────────────────────────────────────────────────────
create_env_file() {
    ENV_FILE="$INSTALL_DIR/.env"
    if [[ -f "$ENV_FILE" ]]; then
        warn ".env already exists — keeping existing credentials."
        return
    fi

    info "Creating .env template…"
    GW_VERSION_PATH=""
    if ls "$GATEWAY_DIR"/*/ibgateway &>/dev/null 2>&1; then
        GW_VERSION_PATH="$(dirname "$(ls "$GATEWAY_DIR"/*/ibgateway | head -1)")"
    fi

    ALPACA_KEY="" ALPACA_SECRET="" ALPACA_LIVE_KEY="" ALPACA_LIVE_SECRET="" IBKR_USER="" IBKR_PASS=""

    # Ask for API keys
    echo ""
    read -rp "$(echo -e "${CYAN}[INPUT]${NC} Enter Alpaca Paper Trading keys now? [Y/n]: ")" want_alpaca
    if [[ ! "$want_alpaca" =~ ^[Nn]$ ]]; then
        read -rp "$(echo -e "${CYAN}[INPUT]${NC} Alpaca Paper API Key:    ")" ALPACA_KEY
        read -rsp "$(echo -e "${CYAN}[INPUT]${NC} Alpaca Paper Secret Key: ")" ALPACA_SECRET
        echo ""
    fi

    read -rp "$(echo -e "${CYAN}[INPUT]${NC} Enter Alpaca Live Trading keys now? [y/N]: ")" want_alpaca_live
    if [[ "$want_alpaca_live" =~ ^[Yy]$ ]]; then
        read -rp "$(echo -e "${CYAN}[INPUT]${NC} Alpaca Live API Key:    ")" ALPACA_LIVE_KEY
        read -rsp "$(echo -e "${CYAN}[INPUT]${NC} Alpaca Live Secret Key: ")" ALPACA_LIVE_SECRET
        echo ""
    fi

    read -rp "$(echo -e "${CYAN}[INPUT]${NC} Enter IBKR credentials now? [Y/n]: ")" want_ibkr
    if [[ ! "$want_ibkr" =~ ^[Nn]$ ]]; then
        read -rp "$(echo -e "${CYAN}[INPUT]${NC} IBKR Username: ")" IBKR_USER
        read -rsp "$(echo -e "${CYAN}[INPUT]${NC} IBKR Password: ")" IBKR_PASS
        echo ""
    fi

    cat > "$ENV_FILE" <<EOF
# ── Alpaca Paper Trading ──────────────────────────────────────────────────────
ALPACA_PAPER_API_KEY=${ALPACA_KEY}
ALPACA_PAPER_SECRET_KEY=${ALPACA_SECRET}

# ── Alpaca Live Trading (required only for live mode) ─────────────────────────
ALPACA_LIVE_API_KEY=${ALPACA_LIVE_KEY}
ALPACA_LIVE_SECRET_KEY=${ALPACA_LIVE_SECRET}

# ── IBKR Credentials ─────────────────────────────────────────────────────────
IBKR_USERNAME=${IBKR_USER}
IBKR_PASSWORD=${IBKR_PASS}
IBKR_MODE=paper

# ── IBC / Gateway paths ───────────────────────────────────────────────────────
IBC_PATH=${IBC_DIR}
GATEWAY_PATH=${GW_VERSION_PATH:-$GATEWAY_DIR}

# ── AutoTrader defaults ───────────────────────────────────────────────────────
AT_SYMBOL=
AT_THRESHOLD=0.5
AT_POLL=5
AT_DAILY_LOSS_LIMIT=0

# ── Portfolio Mode defaults ───────────────────────────────────────────────────
PM_TARGET_SLOTS=10
PM_SLOT_PCT=10.0

# ── Scanner defaults ──────────────────────────────────────────────────────────
SCAN_TOP_N=10
SCAN_MIN_PRICE=5.0
SCAN_MIN_ADV_M=5.0
SCAN_RSI_LO=35
SCAN_RSI_HI=72
SCAN_VOL_MULT=1.0
SCAN_SMA20_TOL=3.0
SCAN_MIN_RET5D=-1.0
SCAN_WATCHLIST=
EOF
    success ".env created."
}

# ── update ────────────────────────────────────────────────────────────────────
do_update() {
    info "Checking for updates from $REPO_URL…"
    require_cmd git
    require_cmd curl

    CUR_VERSION="$(grep -oP '(?<=__version__ = ")[^"]+' "$INSTALL_DIR/version.py" 2>/dev/null || echo "unknown")"

    # ── Fast path: deploy from local dev tree if it's newer ───────────────
    # When running the installer from a dev checkout (SCRIPT_DIR != INSTALL_DIR),
    # skip the GitHub clone if the local version is already ahead.
    if [[ "$SCRIPT_DIR" != "$INSTALL_DIR" ]]; then
        DEV_VERSION="$(grep -oP '(?<=__version__ = ")[^"]+' "$SCRIPT_DIR/version.py" 2>/dev/null || echo "unknown")"
        if [[ "$DEV_VERSION" != "unknown" && "$CUR_VERSION" != "unknown" ]] && \
           _gw_version_gt "$DEV_VERSION" "$CUR_VERSION"; then
            info "Local dev tree is v$DEV_VERSION (installed: v$CUR_VERSION) — deploying directly…"
            mapfile -t PROD_FILES < <(
                sed -n '/^PROD_FILES=(/,/^)/{/^PROD_FILES=(/d;/^)/d;s/[[:space:]]//g;/^$/d;p}' \
                    "$SCRIPT_DIR/goldvreneli-install.sh"
            )
            deploy_files "$SCRIPT_DIR" "$INSTALL_DIR"
            patch_env_paths
            info "Updating Python dependencies…"
            cd "$INSTALL_DIR"
            venv/bin/pip install --quiet --upgrade pip
            venv/bin/pip install --quiet -r requirements.txt
            echo ""
            echo -e "${GREEN}Update complete — now at v${DEV_VERSION}.${NC}"
            echo "  Restart the app: cd $INSTALL_DIR && source venv/bin/activate && streamlit run goldvreneli.py"
            echo ""
            return
        fi
    fi

    # ── Fast path: git pull if install dir is already a repo ──────────────
    if git -C "$INSTALL_DIR" rev-parse --is-inside-work-tree &>/dev/null; then
        info "Installation is a git repo — trying git pull…"
        if git -C "$INSTALL_DIR" pull --ff-only origin main 2>/dev/null; then
            NEW_VERSION="$(grep -oP '(?<=__version__ = ")[^"]+' "$INSTALL_DIR/version.py" 2>/dev/null || echo "unknown")"
            if [[ "$NEW_VERSION" == "$CUR_VERSION" ]]; then
                success "Already up to date (v$CUR_VERSION)."
            else
                success "Pulled v$CUR_VERSION → v$NEW_VERSION"
            fi
            # Skip the clone-and-deploy path
            patch_env_paths
            info "Updating Python dependencies…"
            cd "$INSTALL_DIR"
            venv/bin/pip install --quiet --upgrade pip
            venv/bin/pip install --quiet -r requirements.txt
            # Only update IB Gateway if it was previously installed here
            ls "$GATEWAY_DIR"/*/ibgateway &>/dev/null 2>&1 && { info "Checking for IB Gateway updates…"; install_ib_gateway; } || true
            echo ""
            echo -e "${GREEN}Update complete — now at v${NEW_VERSION}.${NC}"
            echo "  Restart the app: cd $INSTALL_DIR && source venv/bin/activate && streamlit run goldvreneli.py"
            echo ""
            return
        else
            warn "git pull failed (diverged or no remote) — falling back to fresh clone."
        fi
    fi

    # ── Fallback: clone main and deploy prod files ─────────────────────────
    TMP_REPO="$(mktemp -d /tmp/goldvreneli-update-XXXXXX)"
    trap "rm -rf $TMP_REPO" EXIT

    info "Fetching latest release…"
    git clone --depth 1 --branch main "$REPO_URL" "$TMP_REPO" 2>/dev/null || \
        git clone --depth 1 "$REPO_URL" "$TMP_REPO"

    NEW_VERSION="$(grep -oP '(?<=__version__ = ")[^"]+' "$TMP_REPO/version.py" 2>/dev/null || echo "unknown")"

    if [[ "$NEW_VERSION" == "$CUR_VERSION" ]]; then
        success "Already up to date (v$CUR_VERSION)."
        # Still update deps in case requirements changed
    elif [[ "$NEW_VERSION" != "unknown" && "$CUR_VERSION" != "unknown" ]] && \
         ! _gw_version_gt "$NEW_VERSION" "$CUR_VERSION"; then
        warn "Remote is v${NEW_VERSION}, installed is v${CUR_VERSION} — not downgrading."
        warn "Run 'git push' on dev and re-merge to main first."
        return
    else
        info "Updating v$CUR_VERSION → v$NEW_VERSION"
    fi

    # Reload PROD_FILES from the new version so renamed/added files are included
    mapfile -t PROD_FILES < <(
        sed -n '/^PROD_FILES=(/,/^)/{/^PROD_FILES=(/d;/^)/d;s/[[:space:]]//g;/^$/d;p}' \
            "$TMP_REPO/goldvreneli-install.sh"
    )

    info "Deploying updated production files…"
    deploy_files "$TMP_REPO" "$INSTALL_DIR"
    patch_env_paths

    # Only check IB Gateway if binary was already installed here
    if ls "$GATEWAY_DIR"/*/ibgateway &>/dev/null 2>&1; then
        info "Checking for IB Gateway updates…"
        install_ib_gateway
    fi

    info "Updating Python dependencies…"
    cd "$INSTALL_DIR"
    venv/bin/pip install --quiet --upgrade pip
    venv/bin/pip install --quiet -r requirements.txt

    echo ""
    echo -e "${GREEN}Update complete — now at v${NEW_VERSION}.${NC}"
    echo "  Restart the app: cd $INSTALL_DIR && source venv/bin/activate && streamlit run goldvreneli.py"
    echo ""
}

# ── uninstall ─────────────────────────────────────────────────────────────────
do_uninstall() {
    echo ""
    echo -e "${RED}╔══════════════════════════════════════════╗${NC}"
    echo -e "${RED}║   Goldvreneli Trading — Uninstaller      ║${NC}"
    echo -e "${RED}╚══════════════════════════════════════════╝${NC}"
    echo ""
    warn "This will remove:"
    echo "  - Python venv    ($INSTALL_DIR/venv/)"
    echo "  - .env file      ($INSTALL_DIR/.env)"
    $UNINSTALL_IBC     && echo "  - IBC            ($IBC_DIR/)"
    $UNINSTALL_GATEWAY && echo "  - IB Gateway     ($GATEWAY_DIR/)"
    echo ""
    read -rp "Are you sure? [y/N] " confirm
    [[ "$confirm" =~ ^[Yy]$ ]] || { info "Aborted."; exit 0; }

    rm -rf "$INSTALL_DIR/venv" && success "venv removed."
    rm -f  "$INSTALL_DIR/.env" && success ".env removed."
    $UNINSTALL_IBC     && { rm -rf "$IBC_DIR";     success "IBC removed."; }
    $UNINSTALL_GATEWAY && { rm -rf "$GATEWAY_DIR"; success "IB Gateway removed."; }

    echo ""
    echo -e "${GREEN}Uninstall complete.${NC}"
}

# ── summary ───────────────────────────────────────────────────────────────────
print_summary() {
    echo ""
    echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  Installation complete!${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
    echo ""
    echo "  Installed to: $INSTALL_DIR"
    echo ""
    echo "  Next steps:"
    echo "  1. Add credentials via the Settings page in the app, or edit:"
    echo "       nano $INSTALL_DIR/.env"
    echo ""
    echo "  2. Launch the dashboard:"
    echo "       cd $INSTALL_DIR"
    echo "       source venv/bin/activate"
    echo "       streamlit run goldvreneli.py"
    echo ""
    echo "  3. To update later:"
    echo "       $INSTALL_DIR/goldvreneli-install.sh --update"
    echo ""
}

# ─────────────────────────────────────────────────────────────────────────────
# main
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}╔══════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║   Goldvreneli Trading — Installer        ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════╝${NC}"
echo ""

check_linux

# ── parse args ────────────────────────────────────────────────────────────────
SKIP_GATEWAY=false
SKIP_IBC=false
DO_UPDATE=false
DO_UNINSTALL=false
UNINSTALL_IBC=false
UNINSTALL_GATEWAY=false
TARGET_DIR=""

for arg in "$@"; do
    case $arg in
        --skip-gateway)  SKIP_GATEWAY=true ;;
        --skip-ibc)      SKIP_IBC=true ;;
        --update)        DO_UPDATE=true ;;
        --uninstall)     DO_UNINSTALL=true ;;
        --with-ibc)      UNINSTALL_IBC=true ;;
        --with-gateway)  UNINSTALL_GATEWAY=true ;;
        --help|-h)
            echo "Usage: ./goldvreneli-install.sh [OPTIONS] [TARGET_DIR]"
            echo ""
            echo "  TARGET_DIR             Install to this directory (default: script location)"
            echo ""
            echo "Install options:"
            echo "  --skip-gateway         Skip IB Gateway download/install"
            echo "  --skip-ibc             Skip IBC download/install"
            echo ""
            echo "Update option:"
            echo "  --update               Pull latest release and update pip packages"
            echo ""
            echo "Uninstall options:"
            echo "  --uninstall            Remove venv and .env"
            echo "  --uninstall --with-ibc         Also remove IBC"
            echo "  --uninstall --with-gateway     Also remove IB Gateway"
            exit 0
            ;;
        --*) warn "Unknown option: $arg" ;;
        *)   TARGET_DIR="$arg" ;;
    esac
done

# Resolve install directory
if [[ -n "$TARGET_DIR" ]]; then
    INSTALL_DIR="$(realpath -m "$TARGET_DIR")"
elif [[ "$SCRIPT_DIR" == "$HOME/goldvreneli" ]]; then
    INSTALL_DIR="$SCRIPT_DIR"
elif $DO_UNINSTALL || $DO_UPDATE; then
    # Non-interactive modes: use default without prompting
    INSTALL_DIR="$HOME/goldvreneli"
else
    DEFAULT_DIR="$HOME/goldvreneli"
    read -rp "$(echo -e "${CYAN}[INPUT]${NC} Install to $DEFAULT_DIR? [Y/n]: ")" dir_confirm
    if [[ "$dir_confirm" =~ ^[Nn]$ ]]; then
        read -rp "$(echo -e "${CYAN}[INPUT]${NC} Enter install path: ")" custom_dir
        INSTALL_DIR="$(realpath -m "${custom_dir:-$DEFAULT_DIR}")"
    else
        INSTALL_DIR="$DEFAULT_DIR"
    fi
fi

# All components live under the install directory
IBC_DIR="$INSTALL_DIR/ibc"
GATEWAY_DIR="$INSTALL_DIR/Jts/ibgateway"

# ── dispatch ──────────────────────────────────────────────────────────────────
if $DO_UNINSTALL; then
    do_uninstall
    exit 0
fi

if $DO_UPDATE; then
    [[ -f "$INSTALL_DIR/version.py" ]] || error "No installation found at $INSTALL_DIR. Run install first."
    do_update
    exit 0
fi

# ── fresh install ─────────────────────────────────────────────────────────────
install_system_deps
deploy_files "$SCRIPT_DIR" "$INSTALL_DIR"
setup_venv
$SKIP_GATEWAY || install_ib_gateway
$SKIP_IBC     || install_ibc
create_env_file
print_summary

# Ask to launch
read -rp "$(echo -e "${CYAN}[INPUT]${NC} Launch Goldvreneli now and open browser? [Y/n]: ")" want_launch
if [[ ! "$want_launch" =~ ^[Nn]$ ]]; then
    info "Starting Goldvreneli…"
    cd "$INSTALL_DIR"
    # Open browser after a short delay to let Streamlit start
    (sleep 3 && xdg-open "http://localhost:8501" 2>/dev/null || true) &
    source venv/bin/activate
    streamlit run goldvreneli.py
fi
