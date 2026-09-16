#!/usr/bin/env bash
# Build a release .app bundle for this Mac into ./releases.
#
#   packaging/macos/build-release.sh              patch bump (1.1.3 -> 1.1.4)
#   packaging/macos/build-release.sh minor        1.1.3 -> 1.2.0
#   packaging/macos/build-release.sh --set 2.0.0  exact version
#   packaging/macos/build-release.sh --no-bump    rebuild the current version
#   packaging/macos/build-release.sh --dry-run    show the plan only
#
# The result is releases/MCLauncher-<version>-darwin-<arch>/MCLauncher.app.
# Nuitka builds an app bundle rather than a single file on macOS, so
# tools/release.py is always run in --standalone mode here.
#
# STATUS: untested. Written from Nuitka's documented macOS behaviour; nobody
# has run it on a Mac yet. Expect to adjust it, and please update this note
# once it works.
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../lib/common.sh"

[[ "$(uname -s)" == "Darwin" ]] || die "this script only runs on macOS; use packaging/linux or packaging/windows."

require_uv
# Nuitka needs a compiler; on macOS that means the Command Line Tools.
if ! xcode-select -p >/dev/null 2>&1; then
    say "the Xcode Command Line Tools are not installed - Nuitka needs their compiler."
    die "  xcode-select --install"
fi

sync_env
ensure_icons

say "starting release build (this takes several minutes)..."
if ! uv run python tools/release.py --standalone "$@"; then
    echo
    die "release FAILED - version numbers were rolled back."
fi

echo
say "done. Install it with packaging/macos/install.sh"
