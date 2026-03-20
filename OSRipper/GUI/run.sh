#!/usr/bin/env bash
# OSRipper GUI — launcher
# Works on Linux, Termux (Android), proot-distro (Ubuntu/Debian in Termux), macOS.
# From inside proot: the script detects termux-open and launches your Android browser.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

HOST="${OSRIPPER_HOST:-127.0.0.1}"
PORT="${OSRIPPER_PORT:-7070}"

# ── Helpers ─────────────────────────────────────────────────────────────────────
info()  { printf "  \033[34m[*]\033[0m %s\n" "$*"; }
ok()    { printf "  \033[32m[+]\033[0m %s\n" "$*"; }
warn()  { printf "  \033[33m[!]\033[0m %s\n" "$*"; }
die()   { printf "  \033[31m[!]\033[0m %s\n" "$*" >&2; exit 1; }

# ── Detect environment ──────────────────────────────────────────────────────────
IN_PROOT=0
IN_TERMUX=0

# Termux sets TERMUX_VERSION or has its prefix in PATH
[[ -n "$TERMUX_VERSION" || "$PREFIX" == *"com.termux"* ]] && IN_TERMUX=1

# proot-distro sets a PRoot kernel string
if grep -q -i "proot" /proc/version 2>/dev/null; then
    IN_PROOT=1
fi

# ── Find termux-open ────────────────────────────────────────────────────────────
# Checks PATH first, then the canonical Termux usr/bin location (visible from proot).
TERMUX_OPEN=""
for candidate in \
    "$(command -v termux-open 2>/dev/null)" \
    "/data/data/com.termux/files/usr/bin/termux-open" \
    "/data/data/com.termux/files/usr/bin/termux-open-url"; do
    if [[ -x "$candidate" ]]; then
        TERMUX_OPEN="$candidate"
        break
    fi
done

# ── Check Python ─────────────────────────────────────────────────────────────────
PYTHON=""
for py in python3 python; do
    command -v "$py" &>/dev/null && { PYTHON="$py"; break; }
done
[[ -z "$PYTHON" ]] && die "Python 3 not found.\n  Termux:  pkg install python\n  Ubuntu:  apt install python3"

# ── Install Flask if missing ──────────────────────────────────────────────────────
if ! "$PYTHON" -c "import flask" &>/dev/null 2>&1; then
    info "Flask not found — installing..."
    "$PYTHON" -m pip install flask --quiet --break-system-packages 2>/dev/null \
        || "$PYTHON" -m pip install flask --quiet \
        || die "Could not install Flask. Run: pip3 install flask"
fi

# ── Check osripper-cli ─────────────────────────────────────────────────────────
if ! command -v osripper-cli &>/dev/null; then
    info "osripper-cli not found — installing OSRipper..."
    "$PYTHON" -m pip install -e "$SCRIPT_DIR/.." --quiet --break-system-packages 2>/dev/null \
        || "$PYTHON" -m pip install -e "$SCRIPT_DIR/.." --quiet \
        || die "Could not install osripper. Run: pip3 install -e $SCRIPT_DIR/.."
fi

# ── Open URL in browser ────────────────────────────────────────────────────────
open_browser() {
    local url="$1"
    # From proot or Termux: prefer termux-open (opens Android's default browser)
    if [[ -n "$TERMUX_OPEN" ]]; then
        ok "Opening browser via termux-open..."
        "$TERMUX_OPEN" "$url" &>/dev/null &
        return 0
    fi
    # Generic fallbacks (desktop Linux / macOS)
    for opener in xdg-open open sensible-browser; do
        if command -v "$opener" &>/dev/null; then
            "$opener" "$url" &>/dev/null &
            return 0
        fi
    done
    return 1
}

# ── Banner ─────────────────────────────────────────────────────────────────────
DISPLAY_HOST="$HOST"
[[ "$HOST" == "0.0.0.0" ]] && DISPLAY_HOST="0.0.0.0 (all interfaces)"
OPEN_URL="http://127.0.0.1:${PORT}"

echo ""
echo "  ╔══════════════════════════════════════════╗"
echo "  ║   🏴‍☠️  OSRipper GUI  v0.4.2               ║"
printf "  ║   URL:  %-35s║\n" "$OPEN_URL"
printf "  ║   Env:  %-35s║\n" "$([ $IN_PROOT -eq 1 ] && echo "proot ($(uname -r))" || echo "$(uname -s)")"
echo "  ║   Stop: Ctrl+C                           ║"
echo "  ╚══════════════════════════════════════════╝"
echo ""

if [ $IN_PROOT -eq 1 ] || [ $IN_TERMUX -eq 1 ]; then
    info "proot / Termux detected"
    if [[ -n "$TERMUX_OPEN" ]]; then
        info "termux-open: $TERMUX_OPEN"
    else
        warn "termux-open not found — open your browser manually at $OPEN_URL"
    fi
fi

# ── Start server in background, then open browser ──────────────────────────────
"$PYTHON" app.py --host "$HOST" --port "$PORT" &
SERVER_PID=$!

# Wait up to 4 s for Flask to bind
for i in 1 2 3 4; do
    sleep 1
    if "$PYTHON" -c "import urllib.request; urllib.request.urlopen('$OPEN_URL')" &>/dev/null 2>&1; then
        ok "Server is up at $OPEN_URL"
        break
    fi
    [[ $i -eq 4 ]] && warn "Server taking longer than expected — check for port conflicts"
done

# Open the browser
open_browser "$OPEN_URL" \
    && ok "Browser launched → $OPEN_URL" \
    || info "Open in your browser: $OPEN_URL"

# ── Keep running until Ctrl+C ─────────────────────────────────────────────────
cleanup() {
    echo ""
    info "Stopping OSRipper GUI server (PID $SERVER_PID)..."
    kill "$SERVER_PID" 2>/dev/null
    wait "$SERVER_PID" 2>/dev/null
    ok "Server stopped."
}
trap cleanup INT TERM

wait "$SERVER_PID"
