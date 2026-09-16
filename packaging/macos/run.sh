#!/usr/bin/env bash
# Run MCLauncher from source, for development.
#
#   packaging/macos/run.sh            open the launcher window
#   packaging/macos/run.sh --web      open it in your normal browser instead
#   packaging/macos/run.sh --port N   pin the server port
#
# macOS uses pywebview against the WKWebView that ships with the OS, so the
# window is native and the tray icon works - the same as on Windows.
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../lib/common.sh"

require_uv
sync_env

say "starting..."
exec uv run --quiet python -m mclauncher "$@"
