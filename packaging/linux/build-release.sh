#!/usr/bin/env bash
# Build a release binary for this Linux machine into ./releases.
#
#   packaging/linux/build-release.sh              patch bump (1.1.3 -> 1.1.4)
#   packaging/linux/build-release.sh minor        1.1.3 -> 1.2.0
#   packaging/linux/build-release.sh major        1.1.3 -> 2.0.0
#   packaging/linux/build-release.sh --set 2.0.0  exact version
#   packaging/linux/build-release.sh --no-bump    rebuild the current version
#   packaging/linux/build-release.sh --dry-run    show the plan only
#   packaging/linux/build-release.sh patch --tag  also create a git tag
#
# The result is releases/MCLauncher-<version>-linux-<arch>, a single
# self-contained file. Install it with packaging/linux/install.sh.
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../lib/common.sh"

require_uv
# Nuitka compiles generated C, so a system compiler is the one dependency uv
# cannot provide. Its other Linux requirement, patchelf, is in the dev
# dependency group. Check now rather than several minutes into the build.
require_tool gcc "Nuitka needs a C compiler"

sync_env
ensure_icons

say "starting release build (this takes several minutes)..."
if ! uv run python tools/release.py "$@"; then
    echo
    die "release FAILED - version numbers were rolled back."
fi

echo
say "done. Install it with packaging/linux/install.sh"
