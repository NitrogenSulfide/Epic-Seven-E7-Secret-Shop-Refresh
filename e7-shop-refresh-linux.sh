#!/bin/sh
# E7 Secret Shop Refresh on Linux (Epic Seven on Steam/Proton, Background mode).
#
#   ./e7-shop-refresh-linux.sh setup       check system packages, create .venv, build the input helper
#   ./e7-shop-refresh-linux.sh             start the GUI (same as "run")
#   ./e7-shop-refresh-linux.sh check       report what is missing; change nothing
#   ./e7-shop-refresh-linux.sh menu        add "E7 Secret Shop Refresh" to the desktop app menu
#   ./e7-shop-refresh-linux.sh menu-remove remove that menu entry
#
# Nothing here uses sudo. Missing system packages are printed as a command for
# you to run yourself.
set -eu

DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
VENV="$DIR/.venv"
PYTHON=${E7_PYTHON:-python3}
HELPER="$DIR/e7_wine_input.exe"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
DESKTOP_FILE="$APPS/e7-secret-shop-refresh.desktop"

say() { printf '%s\n' "$*"; }
die() { printf 'Error: %s\n' "$*" >&2; exit 1; }

# Package names per family: venv tkinter tesseract mingw
packages() {
    if command -v apt-get >/dev/null 2>&1; then
        say "apt: sudo apt install $*"
    elif command -v dnf >/dev/null 2>&1; then
        say "dnf: sudo dnf install $(printf '%s\n' "$@" | sed \
            -e 's/^python3-venv$//' -e 's/^python3-tk$/python3-tkinter/' \
            -e 's/^tesseract-ocr$/tesseract tesseract-langpack-eng/' \
            -e 's/^gcc-mingw-w64-x86-64$/mingw64-gcc/' | tr '\n' ' ')"
    elif command -v pacman >/dev/null 2>&1; then
        say "pacman: sudo pacman -S --needed $(printf '%s\n' "$@" | sed \
            -e 's/^python3-venv$//' -e 's/^python3-tk$/tk/' \
            -e 's/^tesseract-ocr$/tesseract tesseract-data-eng/' \
            -e 's/^gcc-mingw-w64-x86-64$/mingw-w64-gcc/' | tr '\n' ' ')"
    else
        say "Install these with your package manager (Debian names): $*"
    fi
}

# Prints missing Debian package names, one per line.
missing_packages() {
    command -v "$PYTHON" >/dev/null 2>&1 || { say python3; return; }
    "$PYTHON" -c 'import ensurepip, venv' 2>/dev/null || say python3-venv
    "$PYTHON" -c 'import tkinter' 2>/dev/null || say python3-tk
    command -v tesseract >/dev/null 2>&1 || say tesseract-ocr
    if [ ! -f "$HELPER" ] && ! command -v x86_64-w64-mingw32-gcc >/dev/null 2>&1; then
        say gcc-mingw-w64-x86-64
    fi
}

venv_ok() {
    [ -x "$VENV/bin/python" ] &&
        "$VENV/bin/python" -c 'import numpy, cv2, PIL, Xlib, tkinter' 2>/dev/null
}

session_warning() {
    if [ -z "${DISPLAY:-}" ]; then
        say "Warning: DISPLAY is not set. Background mode needs an X11 desktop session."
    elif [ -n "${WAYLAND_DISPLAY:-}" ] || [ "${XDG_SESSION_TYPE:-}" = wayland ]; then
        say "Warning: this is a Wayland session. Background mode needs X11: the global Stop key"
        say "         cannot work here, so sessions will refuse to start. Log in to an X11 session."
    fi
}

check() {
    status=0
    missing=$(missing_packages)
    if [ -n "$missing" ]; then
        say "Missing system packages:"
        # shellcheck disable=SC2086
        packages $missing
        status=1
    else
        say "System packages: OK"
    fi
    if venv_ok; then say "Python environment (.venv): OK"; else say "Python environment (.venv): not set up"; status=1; fi
    if [ -f "$HELPER" ]; then say "Input helper: OK"; else say "Input helper: not built"; status=1; fi
    if [ -f "$DESKTOP_FILE" ]; then say "Menu entry: $DESKTOP_FILE"; else say "Menu entry: not installed (optional)"; fi
    session_warning
    return $status
}

setup() {
    missing=$(missing_packages)
    if [ -n "$missing" ]; then
        say "These system packages are needed first. Run this, then run setup again:"
        # shellcheck disable=SC2086
        packages $missing
        exit 1
    fi
    if ! venv_ok; then
        say "Creating the Python environment in $VENV ..."
        "$PYTHON" -m venv "$VENV"
        "$VENV/bin/python" -m pip install --upgrade --disable-pip-version-check --quiet pip
        "$VENV/bin/python" -m pip install --disable-pip-version-check -r "$DIR/requirements-linux.txt"
        venv_ok || die "the Python environment was created but its packages do not import."
    else
        say "Python environment: already set up."
    fi
    if [ ! -f "$HELPER" ]; then
        sh "$DIR/build_wine_input.sh"
    else
        say "Input helper: already built."
    fi
    session_warning
    say "Setup complete. Start it with: $DIR/e7-shop-refresh-linux.sh"
    say "Optional menu entry:        $DIR/e7-shop-refresh-linux.sh menu"
}

run() {
    if ! venv_ok || [ ! -f "$HELPER" ]; then
        say "E7 Secret Shop Refresh is not set up yet. Run: $DIR/e7-shop-refresh-linux.sh setup" >&2
        exit 1
    fi
    session_warning >&2
    cd "$DIR"
    exec "$VENV/bin/python" "$DIR/e7_shop_refresh_gui.py" "$@"
}

desktop_escape() {
    # Quote for a .desktop Exec key (Desktop Entry spec): inside double quotes
    # " ` $ \ are backslash-escaped, then the string escape doubles every
    # backslash (so \ becomes four), and % is doubled.
    printf '"%s"' "$(printf '%s' "$1" | sed -e 's/\\/\\\\\\\\/g' -e 's/["`$]/\\\\&/g' -e 's/%/%%/g')"
}

menu() {
    case "$DIR" in *'
'*) die "the project folder name contains a newline." ;; esac
    mkdir -p "$APPS"
    tmp="$DESKTOP_FILE.tmp.$$"
    cat >"$tmp" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=E7 Secret Shop Refresh
Comment=Refresh the Epic Seven Secret Shop in the background (Steam on Linux)
Exec=$(desktop_escape "$DIR/e7-shop-refresh-linux.sh") run
Path=$DIR
Icon=$DIR/e7_gui_assets/shopkeeper.png
Terminal=false
Categories=Game;
StartupWMClass=E7_shop_refresh_gui
EOF
    mv "$tmp" "$DESKTOP_FILE"
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APPS" 2>/dev/null || true
    say "Added the menu entry: $DESKTOP_FILE"
    say "If you move this folder, run \"menu\" again."
}

menu_remove() {
    if [ -f "$DESKTOP_FILE" ]; then
        rm -f "$DESKTOP_FILE"
        command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APPS" 2>/dev/null || true
        say "Removed the menu entry."
    else
        say "No menu entry installed."
    fi
}

command=${1:-run}
[ $# -gt 0 ] && shift
case "$command" in
    run) run "$@" ;;
    setup) setup ;;
    check) check ;;
    menu) menu ;;
    menu-remove) menu_remove ;;
    -h|--help|help) sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//' ;;
    *) die "unknown command \"$command\". Use setup, run, check, menu or menu-remove." ;;
esac
