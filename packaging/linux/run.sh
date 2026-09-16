#!/usr/bin/env bash
# Run MCLauncher from source, for development.
#
#   packaging/linux/run.sh            open the launcher window
#   packaging/linux/run.sh --web      open it in your normal browser instead
#   packaging/linux/run.sh --port N   pin the server port
#   packaging/linux/run.sh --wm-class print the window class and exit
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../lib/common.sh"

require_uv
sync_env

say "starting..."
exec uv run --quiet python -m mclauncher "$@"
