"""Build a standalone MCLauncher executable with Nuitka.

    uv run python tools/build.py              # onefile -> releases/
    uv run python tools/build.py --standalone # folder build (easier to debug)
    uv run python tools/build.py --clean      # wipe build caches first

It builds for whatever machine it runs on, and the finished artifact is copied
into ./releases. Normally you would not call this directly - the per-platform
wrappers in packaging/ bump the version and check the result afterwards.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "src" / "mclauncher"
ENTRY = PKG  # the package dir: Nuitka + `--python-flag=-m` runs its __main__
ICON = PKG / "assets" / "icon.ico"
ICON_PNG = PKG / "assets" / "icon.png"
BUILD_DIR = ROOT / "build"
RELEASES = ROOT / "releases"
APP_NAME = "MCLauncher"


def version() -> str:
    text = (PKG / "__init__.py").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("__version__"):
            return line.split("=", 1)[1].strip().strip("\"'")
    return "0.0.0"


def nuitka_command(onefile: bool, jobs: int | None, console: bool = False) -> list[str]:
    cmd = [
        sys.executable,
        "-m",
        "nuitka",
        "--standalone",
        "--assume-yes-for-downloads",
        "--python-flag=-m",  # the entry point is a package __main__
        f"--output-dir={BUILD_DIR}",
        f"--output-filename={APP_NAME}.exe" if is_windows() else f"--output-filename={APP_NAME}",
        # NiceGUI ships its web assets (vue, quasar, fonts) as package data.
        # webview is deliberately left to Nuitka's own pywebview plugin.
        "--include-package=mclauncher",
        "--include-package=nicegui",
        "--include-package-data=nicegui",
        "--include-package=uvicorn",
        "--include-package=PIL",
        "--include-data-files=" + str(ICON) + "=mclauncher/assets/icon.ico",
        "--include-data-files=" + str(ICON_PNG) + "=mclauncher/assets/icon.png",
        "--nofollow-import-to=nuitka",
        "--nofollow-import-to=tkinter",
        f"--product-name={APP_NAME}",
        f"--file-version={version()}",
        f"--product-version={version()}",
        "--file-description=Offline-mode Minecraft launcher",
        "--copyright=Local build",
    ]
    if not is_linux():
        # The tray is a Windows/macOS affair. On Linux pystray would only find
        # its X11 backend, which Wayland compositors have no tray for.
        cmd.append("--include-package=pystray")
    if onefile:
        cmd.append("--onefile")
        # Without this the 40 MB payload is unpacked to a fresh temp folder on
        # every single start - including the child process the native window
        # runs in, so it happens twice per launch. A stable per-version path
        # means it is unpacked once, then reused.
        cmd.append("--onefile-tempdir-spec={CACHE_DIR}/{PRODUCT}/{VERSION}")
    if is_windows():
        cmd += [
            f"--windows-icon-from-ico={ICON}",
            "--windows-console-mode=" + ("force" if console else "disable"),
            "--msvc=latest" if shutil.which("cl") else "--mingw64",
        ]
    elif is_mac():
        # An .app bundle is what macOS expects to be handed; it is also
        # mutually exclusive with --onefile, which main() accounts for.
        cmd += [f"--macos-app-icon={ICON}", "--macos-create-app-bundle"]
    else:
        # No --linux-icon: Nuitka only honours it for AppImage-style builds, and
        # on Linux the icon comes from the .desktop entry install.sh writes.
        # There is also no GTK/Qt webview to bundle - the UI opens in a Chromium
        # app window instead (see mclauncher/desktop.py) - and following these
        # imports would drag half the desktop into the binary.
        cmd += [
            "--nofollow-import-to=webview",
            "--nofollow-import-to=gi",
            "--nofollow-import-to=qtpy",
        ]
    if jobs:
        cmd.append(f"--jobs={jobs}")
    cmd.append(str(ENTRY))
    return cmd


def check_toolchain() -> None:
    """Fail early and usefully instead of several minutes into a compile."""
    if not is_linux():
        return
    # Nuitka shells out to patchelf to fix up RPATHs. It comes from the dev
    # dependency group rather than the system, so make sure Nuitka can see it
    # even when build.py was started without `uv run`.
    if not shutil.which("patchelf"):
        bundled = Path(sys.executable).parent / "patchelf"
        if bundled.is_file():
            os.environ["PATH"] = str(bundled.parent) + os.pathsep + os.environ.get("PATH", "")
    missing = [tool for tool in ("patchelf", "gcc") if not shutil.which(tool)]
    if missing:
        raise SystemExit(
            "missing build tools: " + ", ".join(missing) + "\n"
            "patchelf ships in the dev dependency group - `uv sync` then build with\n"
            "`./build_release.sh`. gcc has to come from the system; on Arch/Omarchy:\n"
            "    sudo pacman -S --needed gcc"
        )


def process_alive(pid: int) -> bool:
    if is_windows():
        import ctypes

        SYNCHRONIZE = 0x00100000
        handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)  # POSIX only: signal 0 just tests for existence
    except OSError:
        return False
    return True


@contextlib.contextmanager
def build_lock():
    """Two builds sharing build/ corrupt each other's generated C files."""
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    lock = BUILD_DIR / ".build.lock"
    if lock.is_file():
        try:
            owner = int(lock.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            owner = None
        if owner and owner != os.getpid() and process_alive(owner):
            raise SystemExit(
                f"another build is already running (pid {owner}).\n"
                "Wait for it to finish, or stop it, then run this again.\n"
                f"If you are sure nothing is running, delete {lock}"
            )
        lock.unlink(missing_ok=True)  # left behind by a crashed build
    try:
        handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise SystemExit(f"another build just started; try again in a moment ({lock})")
    try:
        os.write(handle, str(os.getpid()).encode("ascii"))
        os.close(handle)
        yield
    finally:
        lock.unlink(missing_ok=True)


def is_windows() -> bool:
    return sys.platform.startswith("win")


def is_mac() -> bool:
    return sys.platform == "darwin"


def is_linux() -> bool:
    return sys.platform.startswith("linux")


def find_artifact(onefile: bool) -> Path:
    """The thing Nuitka just built: one file, an .app bundle, or a dist folder."""
    exe = f"{APP_NAME}.exe" if is_windows() else APP_NAME
    if is_mac():
        bundle = next(BUILD_DIR.glob("*.app"), None)
        if bundle is not None:
            return bundle
    if onefile:
        candidate = BUILD_DIR / exe
        if candidate.is_file():
            return candidate
    dist = BUILD_DIR / "mclauncher.dist"
    if not dist.is_dir():
        dist = next(BUILD_DIR.glob("*.dist"), None)  # type: ignore[assignment]
    if dist and (dist / exe).is_file():
        return dist
    raise SystemExit(f"could not find the build output under {BUILD_DIR}")


def publish(artifact: Path) -> Path:
    """Copy the artifact into ./releases under a name that names the platform.

    One artifact per os/arch, so builds of the same version for different
    machines sit beside each other instead of overwriting one another.
    """
    RELEASES.mkdir(parents=True, exist_ok=True)
    tag = f"{APP_NAME}-{version()}-{platform.system().lower()}-{platform.machine().lower()}"
    if artifact.is_file():
        target = RELEASES / (tag + artifact.suffix)
        target.unlink(missing_ok=True)
        shutil.copy2(artifact, target)
        return target
    target = RELEASES / tag
    shutil.rmtree(target, ignore_errors=True)
    if artifact.suffix == ".app":
        # A bundle has to keep its .app name to stay a bundle, so it goes
        # inside the tagged folder rather than being renamed to it.
        target.mkdir(parents=True)
        shutil.copytree(artifact, target / artifact.name, symlinks=True)
    else:
        shutil.copytree(artifact, target, symlinks=True)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Build MCLauncher with Nuitka")
    parser.add_argument(
        "--standalone",
        action="store_true",
        help="produce a folder build instead of a single file",
    )
    parser.add_argument("--clean", action="store_true", help="remove build/ first")
    parser.add_argument(
        "--clean-releases", action="store_true", help="also empty releases/ (deletes old builds)"
    )
    parser.add_argument("--jobs", type=int, default=None, help="parallel compile jobs")
    parser.add_argument("--console", action="store_true", help="keep a console window (debugging)")
    args = parser.parse_args()

    if not ICON.is_file() or not ICON_PNG.is_file():
        raise SystemExit("missing icon: run `uv run --with pillow python tools/make_icon.py`")
    check_toolchain()
    if args.clean:
        shutil.rmtree(BUILD_DIR, ignore_errors=True)
    if args.clean_releases:
        shutil.rmtree(RELEASES, ignore_errors=True)

    with build_lock():
        onefile = not args.standalone
        if is_mac() and onefile:
            # Nuitka refuses --onefile together with an app bundle, and a bare
            # binary is not something macOS knows how to put in Launchpad.
            print("macOS: building an .app bundle (--onefile does not apply)", flush=True)
            onefile = False
        cmd = nuitka_command(onefile, args.jobs, args.console)
        print("$ " + " ".join(cmd), flush=True)
        started = time.time()
        result = subprocess.run(cmd, cwd=ROOT)
        if result.returncode != 0:
            raise SystemExit(
                f"nuitka failed with exit code {result.returncode}\n"
                "If the error names a generated .c file, the build tree is inconsistent: "
                "rerun with --clean"
            )

        target = publish(find_artifact(onefile))

    minutes = (time.time() - started) / 60
    size = (
        target.stat().st_size
        if target.is_file()
        else sum(p.stat().st_size for p in target.rglob("*") if p.is_file())
    )
    print(f"\nbuilt in {minutes:.1f} min -> {target} ({size / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()
