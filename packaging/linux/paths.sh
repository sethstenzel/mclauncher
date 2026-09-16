# Where a Linux install puts its files. Sourced by install.sh and uninstall.sh
# so the two can never disagree about a path.

PREFIX="${PREFIX:-$HOME/.local}"
ICON_NAME="mclauncher"

BIN_DIR="$PREFIX/bin"
ICON_DIR="$PREFIX/share/icons/hicolor/256x256/apps"
DESKTOP_DIR="$PREFIX/share/applications"

BIN="$BIN_DIR/$ICON_NAME"
ICON="$ICON_DIR/$ICON_NAME.png"
DESKTOP="$DESKTOP_DIR/$ICON_NAME.desktop"
ICON_SOURCE="$REPO_ROOT/src/mclauncher/assets/icon.png"

# Best-effort: a desktop without these still picks the entry up, just later.
refresh_desktop_caches() {
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
    fi
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -qtf "$PREFIX/share/icons/hicolor" >/dev/null 2>&1 || true
    fi
}
