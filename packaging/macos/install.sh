#!/usr/bin/env bash
# Install a built MCLauncher.app into /Applications (or ~/Applications).
#
#   packaging/macos/install.sh                 newest bundle in releases/
#   packaging/macos/install.sh path/to/MCLauncher.app
#   APPDIR=~/Applications packaging/macos/install.sh
#
# STATUS: untested, like the build script beside it.
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../lib/common.sh"

[[ "$(uname -s)" == "Darwin" ]] || die "this script only runs on macOS."

APPDIR="${APPDIR:-/Applications}"
TARGET="$APPDIR/$APP_NAME.app"

bundle="${1:-}"
if [[ -z "$bundle" ]]; then
    release="$(newest_release "$APP_NAME-*-darwin-*")"
    [[ -n "$release" ]] || die \
        "no build found. Run packaging/macos/build-release.sh first, or pass a path as an argument."
    # A folder build holds the bundle; --onefile would leave it at the top.
    bundle="$release/$APP_NAME.app"
    [[ -d "$bundle" ]] || bundle="$release"
fi
[[ -d "$bundle" ]] || die "not an app bundle: $bundle"

[[ -w "$APPDIR" ]] || die "$APPDIR is not writable. Re-run with sudo, or APPDIR=~/Applications."

rm -rf "$TARGET"
cp -R "$bundle" "$TARGET"
say "installed $TARGET"

# An unsigned bundle is quarantined on first open; clearing the flag here saves
# the user a right-click -> Open dance.
if command -v xattr >/dev/null 2>&1; then
    xattr -dr com.apple.quarantine "$TARGET" 2>/dev/null || true
fi

say "done - look for $APP_NAME in Launchpad."
