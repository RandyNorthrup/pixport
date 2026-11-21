#!/bin/sh
# Install Pixport for the current user: ~/.local/opt/pixport, launcher and icons.
# Run from the extracted release folder:  ./install.sh      Remove with: ./install.sh --uninstall
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
PREFIX="${XDG_DATA_HOME:-$HOME/.local/share}"
OPT="$HOME/.local/opt/pixport"
BIN="$HOME/.local/bin"

if [ "${1:-}" = "--uninstall" ]; then
    rm -rf "$OPT" "$BIN/pixport" "$PREFIX/applications/pixport.desktop"
    find "$PREFIX/icons/hicolor" -name 'pixport.*' -delete 2>/dev/null || true
    echo "Pixport removed."
    exit 0
fi

mkdir -p "$OPT" "$BIN" "$PREFIX/applications"
cp -R "$HERE/pixport/." "$OPT/"
ln -sf "$OPT/pixport" "$BIN/pixport"
cp -R "$HERE/hicolor" "$PREFIX/icons/" 2>/dev/null || { mkdir -p "$PREFIX/icons"; cp -R "$HERE/hicolor" "$PREFIX/icons/"; }
# Absolute Exec path, so the menu entry works even if ~/.local/bin is not on PATH.
sed "s|^Exec=pixport|Exec=$OPT/pixport|" "$HERE/pixport.desktop" > "$PREFIX/applications/pixport.desktop"
command -v update-desktop-database >/dev/null && update-desktop-database "$PREFIX/applications" || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q "$PREFIX/icons/hicolor" || true
echo "Pixport installed. Launch it from your app menu, or run: pixport"
