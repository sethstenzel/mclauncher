#!/usr/bin/env bash
# Install a built MCLauncher binary for the current user - no root required.
#
#   packaging/linux/install.sh                    newest binary in releases/
#   packaging/linux/install.sh releases/MCLauncher-1.1.3-linux-x86_64
#
# Everything lands under ~/.local, so the launcher appears in the application
# menu straight away. Set PREFIX to install elsewhere:
#
#   PREFIX=/usr/local sudo -E packaging/linux/install.sh
#
# packaging/linux/uninstall.sh reverses it.
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../lib/common.sh"
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/paths.sh"

binary="${1:-$(newest_release "$APP_NAME-*-linux-*")}"
[[ -n "$binary" && -f "$binary" ]] || die \
    "no binary found. Run packaging/linux/build-release.sh first, or pass a path as an argument."

install -Dm755 "$binary" "$BIN"
say "installed $BIN"

if [[ -f "$ICON_SOURCE" ]]; then
    install -Dm644 "$ICON_SOURCE" "$ICON"
    say "installed $ICON"
else
    say "note: $ICON_SOURCE is missing, so the menu entry will have no icon"
fi

# Ask the binary what class its window will carry rather than guessing - it
# depends on which browser is installed. A onefile build unpacks itself the
# first time it runs, so this doubles as a check that the binary works at all.
say "checking the binary (a onefile build unpacks itself the first time)..."
wm_class="$("$BIN" --wm-class 2>/dev/null | tail -1)"
if [[ -z "$wm_class" ]]; then
    wm_class="$APP_NAME"
    say "note: the binary did not report a window class; falling back to '$wm_class'"
fi

mkdir -p "$DESKTOP_DIR"
sed -e "s|@EXEC@|$BIN|" \
    -e "s|@ICON_NAME@|$ICON_NAME|" \
    -e "s|@WM_CLASS@|$wm_class|" \
    "$(dirname "${BASH_SOURCE[0]}")/mclauncher.desktop.in" > "$DESKTOP"
chmod 644 "$DESKTOP"
say "installed $DESKTOP"

refresh_desktop_caches

case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) say "note: $BIN_DIR is not on your PATH, so '$ICON_NAME' will not work from a"
       say "      terminal until you add it. The menu entry works either way." ;;
esac

say "done - look for $APP_NAME in your application launcher."
say "window class is '$wm_class' (for a Hyprland windowrule)."
