#!/bin/sh
# E7 Secret Shop Refresh on macOS (Epic Seven's iPad app on Apple silicon, Mac mode).
#
#   ./e7-shop-refresh-macos.sh setup   check Homebrew packages, create .venv
#   ./e7-shop-refresh-macos.sh         start the GUI (same as "run")
#   ./e7-shop-refresh-macos.sh check   report what is missing, including macOS permissions; change nothing
#
# Mac mode takes over your pointer: keep the game in front, in a 16:9 window,
# and leave the Mac alone while it runs. Nothing here uses sudo or installs
# Homebrew packages; missing ones are printed as a command for you to run.
set -eu

DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
VENV="$DIR/.venv"
PYTHON=${E7_PYTHON:-/opt/homebrew/bin/python3.13}

say() { printf '%s\n' "$*"; }
die() { printf 'Error: %s\n' "$*" >&2; exit 1; }

# Prints missing Homebrew formula names, one per line.
missing_packages() {
    if [ ! -x "$PYTHON" ]; then say python@3.13; say python-tk@3.13; return; fi
    "$PYTHON" -c 'import tkinter' 2>/dev/null || say python-tk@3.13
    command -v tesseract >/dev/null 2>&1 || say tesseract
}

venv_ok() {
    [ -x "$VENV/bin/python" ] &&
        "$VENV/bin/python" -c 'import numpy, cv2, PIL, tkinter, Quartz, ScreenCaptureKit, AppKit' 2>/dev/null
}

# Read-only: which macOS permissions the app running this script has.
permissions() {
    "$VENV/bin/python" - <<'EOF'
import Quartz
listen = getattr(Quartz, 'CGPreflightListenEventAccess', lambda: None)()
for name, ok in (('Screen Recording', Quartz.CGPreflightScreenCaptureAccess()),
                 ('Accessibility', Quartz.CGPreflightPostEventAccess()),
                 ('Input Monitoring (Stop key)', listen)):
    print(f'{name}: ' + ('allowed' if ok else 'unknown' if ok is None else 'NOT allowed'))
EOF
    say "Permissions belong to the app that starts this script (for example Terminal)."
    say "Change them in System Settings > Privacy & Security."
}

check() {
    status=0
    [ "$(uname -s)" = Darwin ] || die "this script is for macOS."
    [ "$(uname -m)" = arm64 ] || say "Warning: the iPad app runs only on Apple silicon Macs."
    missing=$(missing_packages)
    if [ -n "$missing" ]; then
        say "Missing Homebrew packages. Run:"
        say "  brew install $(printf '%s ' $missing)"
        status=1
    else
        say "Homebrew packages: OK"
    fi
    if venv_ok; then say "Python environment (.venv): OK"; permissions; else say "Python environment (.venv): not set up"; status=1; fi
    return $status
}

setup() {
    [ "$(uname -s)" = Darwin ] || die "this script is for macOS."
    missing=$(missing_packages)
    if [ -n "$missing" ]; then
        say "These Homebrew packages are needed first. Run this, then run setup again:"
        say "  brew install $(printf '%s ' $missing)"
        exit 1
    fi
    if ! venv_ok; then
        say "Creating the Python environment in $VENV ..."
        "$PYTHON" -m venv "$VENV"
        "$VENV/bin/python" -m pip install --upgrade --disable-pip-version-check --quiet pip
        "$VENV/bin/python" -m pip install --disable-pip-version-check -r "$DIR/requirements-macos.txt"
        venv_ok || die "the Python environment was created but its packages do not import."
    else
        say "Python environment: already set up."
    fi
    permissions
    say "Setup complete. Start it with: $DIR/e7-shop-refresh-macos.sh"
}

run() {
    if ! venv_ok; then
        say "E7 Secret Shop Refresh is not set up yet. Run: $DIR/e7-shop-refresh-macos.sh setup" >&2
        exit 1
    fi
    cd "$DIR"
    exec "$VENV/bin/python" "$DIR/e7_shop_refresh_gui.py" "$@"
}

command=${1:-run}
[ $# -gt 0 ] && shift
case "$command" in
    run) run "$@" ;;
    setup) setup ;;
    check) check ;;
    -h|--help|help) sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//' ;;
    *) die "unknown command \"$command\". Use setup, run or check." ;;
esac
