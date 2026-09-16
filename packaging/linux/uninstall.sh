#!/usr/bin/env bash
# Remove what packaging/linux/install.sh installed. Settings and game files are
# left alone. Set PREFIX to match the one used at install time.
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../lib/common.sh"
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/paths.sh"

removed=0
for path in "$BIN" "$ICON" "$DESKTOP"; do
    if [[ -e "$path" ]]; then
        rm -f "$path"
        say "removed $path"
        removed=1
    fi
done
(( removed )) || say "nothing to remove under $PREFIX"

refresh_desktop_caches

say "your settings and game files were left alone:"
say "  ${XDG_CONFIG_HOME:-$HOME/.config}/$APP_NAME  and  ~/.minecraft"
say "the unpacked copy of the binary lives in ${XDG_CACHE_HOME:-$HOME/.cache}/$APP_NAME"
