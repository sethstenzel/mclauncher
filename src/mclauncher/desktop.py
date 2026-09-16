"""How the launcher window gets put on screen.

Windows and macOS have a webview the operating system already ships, so
pywebview draws a real native window there and nothing else is needed.

Linux has no such thing: pywebview's GTK backend needs PyGObject *and*
WebKitGTK from the system, neither of which survives being frozen into a
self-contained binary. So on Linux the UI is opened as a Chromium "app"
window instead - a plain browser window with no tabs or address bar, in its
own profile so that it is a process of its own. Owning that process is what
lets the launcher notice the user closing the window and shut itself down.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Chromium ignores --class for --app windows and builds its own name out of the
# URL and the profile directory, so the profile is named after us to keep that
# derived name recognisable: chrome-127.0.0.1__-MCLauncher.
PROFILE_NAME = "MCLauncher"

# --class still applies to anything that is not an app window, and to the
# handful of forks that honour it.
WM_CLASS = "MCLauncher"

# The `chrome` in `chrome-...`: each fork stamps its own product name there.
BROWSER_CLASS_PREFIX = {
    "brave": "brave",
    "brave-browser": "brave",
    "microsoft-edge": "msedge",
    "microsoft-edge-stable": "msedge",
    "vivaldi": "vivaldi",
    "vivaldi-stable": "vivaldi",
}

# Chromium forks, in the order we would rather have them. Anything here
# understands --app, which is the whole reason for the list.
APP_BROWSERS = (
    "chromium",
    "chromium-browser",
    "google-chrome-stable",
    "google-chrome",
    "brave",
    "brave-browser",
    "microsoft-edge-stable",
    "microsoft-edge",
    "vivaldi-stable",
    "vivaldi",
    "thorium-browser",
)


def _gtk_webview_available() -> bool:
    """True when pywebview's GTK backend has everything it needs.

    `require_version` only consults the installed typelibs, so this answers the
    question without pulling GTK into the process.
    """
    try:
        import gi
    except ImportError:
        return False
    try:
        gi.require_version("Gtk", "3.0")
    except (ValueError, AttributeError):
        return False
    for api in ("4.1", "4.0"):
        try:
            gi.require_version("WebKit2", api)
            return True
        except (ValueError, AttributeError):
            continue
    return False


def _qt_webview_available() -> bool:
    if importlib.util.find_spec("qtpy") is None:
        return False
    for module in ("PyQt6.QtWebEngineWidgets", "PySide6.QtWebEngineWidgets"):
        try:
            if importlib.util.find_spec(module) is not None:
                return True
        except (ImportError, ValueError):
            continue
    return False


def native_webview_available() -> bool:
    """Can pywebview draw a native window in *this* process?"""
    if importlib.util.find_spec("webview") is None:
        return False
    if sys.platform.startswith("win") or sys.platform == "darwin":
        return True
    return _gtk_webview_available() or _qt_webview_available()


def find_app_browser() -> str | None:
    """A Chromium-style browser to host the window, or None."""
    override = os.environ.get("MCLAUNCHER_BROWSER", "").strip()
    if override:
        return shutil.which(override) or (override if Path(override).is_file() else None)
    for name in APP_BROWSERS:
        found = shutil.which(name)
        if found:
            return found
    return None


def app_window_wm_class() -> str:
    """The WM_CLASS / app_id the window will actually carry.

    Worth having as a real answer rather than a guess: it is what a .desktop
    file's StartupWMClass and a Hyprland `windowrule` need in order to match.
    `python -m mclauncher --wm-class` prints it.
    """
    browser = find_app_browser()
    if browser is None:
        return WM_CLASS
    prefix = BROWSER_CLASS_PREFIX.get(Path(browser).name, "chrome")
    # Chromium's own recipe: host, then the path with its slashes turned into
    # underscores. The port is not part of it, which is why a random port does
    # not change the class.
    return f"{prefix}-127.0.0.1__-{PROFILE_NAME}"


def _profile_is_held(profile_dir: Path) -> bool:
    """True while a live browser still owns this profile.

    Chromium points `SingletonLock` at `<hostname>-<pid>` for as long as it is
    running and removes it on a clean exit, so a leftover lock naming a dead pid
    means the directory is abandoned.
    """
    try:
        target = os.readlink(profile_dir / "SingletonLock")
    except OSError:
        return False
    pid = target.rsplit("-", 1)[-1]
    if not pid.isdigit():
        return True  # unreadable lock: leave the directory alone
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True  # not ours to signal, so assume it is alive
    return True


def _sweep_profiles(root: Path, keep: Path) -> None:
    """Delete profiles left behind by launchers that are no longer running."""
    for child in root.iterdir():
        if child == keep or not child.is_dir():
            continue
        # A browser that started moments ago may not have written its lock yet.
        if time.time() - child.stat().st_mtime < 60:
            continue
        if not _profile_is_held(child):
            shutil.rmtree(child, ignore_errors=True)


def prepare_profile_root(root: Path, port: int) -> Path:
    """The profile directory for this instance, under `root`.

    One per port rather than one shared directory: a second `--app` launch
    against a profile another browser already owns is handed off to that
    browser and exits immediately, which would take the watcher - and with it
    the launcher - down with it. Ports are unique per instance, so profiles are
    too, and abandoned ones are swept up on the way past.
    """
    # Older versions used `root` itself as the profile. Its marker file is the
    # giveaway; clear it out rather than sweeping around its contents forever.
    if (root / "Local State").is_file():
        shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    profile_dir = root / str(port)
    try:
        _sweep_profiles(root, keep=profile_dir)
    except OSError:
        pass  # a tidy-up failure is never worth blocking a launch for
    profile_dir.mkdir(parents=True, exist_ok=True)
    return profile_dir


def open_app_window(
    url: str, size: tuple[int, int], profile_root: Path, port: int
) -> subprocess.Popen | None:
    """Open `url` as an app window. Returns the browser process, or None.

    The private profile directory is not optional: without it the command would
    hand the URL to whatever browser the user already has open and exit
    immediately, leaving nothing to wait on.
    """
    browser = find_app_browser()
    if browser is None:
        return None
    profile_dir = prepare_profile_root(profile_root, port)
    width, height = size
    cmd = [
        browser,
        f"--app={url}",
        f"--user-data-dir={profile_dir}",
        f"--profile-directory={PROFILE_NAME}",
        f"--class={WM_CLASS}",
        f"--window-size={width},{height}",
        "--no-first-run",
        "--no-default-browser-check",
        "--no-service-autorun",
        "--disable-sync",
        "--disable-background-networking",
        "--disable-features=Translate,MediaRouter",
    ]
    if os.environ.get("XDG_SESSION_TYPE") == "wayland":
        # Without the hint it starts under XWayland and looks blurry on a
        # fractional-scaled monitor.
        cmd.append("--ozone-platform-hint=auto")
    return subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
