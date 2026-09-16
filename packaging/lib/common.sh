# Shared helpers for the POSIX packaging scripts. Sourced, never executed.
#
#   SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
#   source "$SCRIPT_DIR/../lib/common.sh"
#
# Sourcing this sets REPO_ROOT and changes to it, so every later path can be
# written relative to the repository rather than to the caller's cwd.

set -euo pipefail

APP_NAME="MCLauncher"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

say() { echo "[$APP_NAME] $*"; }
die() { echo "[$APP_NAME] $*" >&2; exit 1; }

# The package manager's name for a tool, and the command that installs it.
# Keyed by what `ID`/`ID_LIKE` in /etc/os-release reports.
install_hint() {
    local tool="$1" id="" like=""
    if [[ -r /etc/os-release ]]; then
        # shellcheck disable=SC1091
        id="$(. /etc/os-release && echo "${ID:-}")"
        like="$(. /etc/os-release && echo "${ID_LIKE:-}")"
    fi
    case "$id $like" in
        *arch*)             echo "sudo pacman -S --needed $tool" ;;
        *debian*|*ubuntu*)  echo "sudo apt install $tool" ;;
        *fedora*|*rhel*)    echo "sudo dnf install $tool" ;;
        *suse*)             echo "sudo zypper install $tool" ;;
        *)                  echo "install '$tool' with your package manager" ;;
    esac
}

require_tool() {
    local tool="$1" why="$2"
    command -v "$tool" >/dev/null 2>&1 && return 0
    say "'$tool' is not installed - $why"
    die "  $(install_hint "$tool")"
}

require_uv() {
    command -v uv >/dev/null 2>&1 && return 0
    say "uv is not installed or not on PATH."
    die "Install it from https://docs.astral.sh/uv/ then run this again."
}

sync_env() {
    say "syncing environment..."
    uv sync --quiet || die "uv sync failed."
}

ensure_icons() {
    if [[ ! -f src/mclauncher/assets/icon.ico || ! -f src/mclauncher/assets/icon.png ]]; then
        say "generating icons..."
        uv run --with pillow python tools/make_icon.py
    fi
}

# Newest release artifact matching a glob, or empty. Directories count too: the
# --standalone and macOS app-bundle layouts are folders, not single files.
# Written with bash's own `-nt` rather than `find -printf`, which is GNU-only
# and so absent on macOS.
newest_release() {
    local newest="" candidate
    for candidate in releases/$1; do
        [[ -e "$candidate" ]] || continue
        if [[ -z "$newest" || "$candidate" -nt "$newest" ]]; then
            newest="$candidate"
        fi
    done
    echo "$newest"
}
