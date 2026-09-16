# packaging

Everything needed to turn the source tree into something you can install,
grouped by the operating system you are building **on**. There is no
cross-compilation: each script builds for the machine it runs on.

| | Build | Install | Result | Status |
|---|---|---|---|---|
| **Windows** | `windows\build-release.bat` | — copy the .exe anywhere | one `.exe` | works |
| **Linux** (Arch / Omarchy) | `linux/build-release.sh` | `linux/install.sh` | one binary + `.desktop` entry | works |
| **Linux** (Ubuntu / Debian, Fedora) | `linux/build-release.sh` | `linux/install.sh` | one binary + `.desktop` entry | should work, untested |
| **macOS** | `macos/build-release.sh` | `macos/install.sh` | `MCLauncher.app` | untested |

Verified builds so far: Windows 11 (x86_64) and Omarchy / Arch (x86_64,
Hyprland). The other rows are written from the documented behaviour of the
same tools and have not been run. If you are the first to run one, please
correct this table.

## Layout

```
lib/common.sh              helpers shared by every POSIX script
linux/
  run.sh                   run from source, for development
  build-release.sh         bump the version and build -> releases/
  install.sh               install into ~/.local (no root)
  uninstall.sh             reverse install.sh
  paths.sh                 where an install puts its files
  mclauncher.desktop.in    application-menu entry template
macos/
  run.sh                   run from source, for development
  build-release.sh         bump the version and build an .app -> releases/
  install.sh               copy the .app into /Applications
windows/
  run.bat                  run from source, for development
  build-release.bat        bump the version and build -> releases/
```

All of them can be run from anywhere: each resolves the repository root from
its own location rather than from your current directory.

## Build requirements

`uv` on every platform, plus a C compiler for Nuitka:

| | Compiler | Notes |
|---|---|---|
| Windows | MSVC, or MinGW64 which Nuitka offers to download | `build.py` prefers MSVC when `cl` is on PATH |
| Linux | `gcc` | plus `patchelf`, which is in the dev dependency group, so `uv sync` covers it |
| macOS | Xcode Command Line Tools | `xcode-select --install` |

Each `build-release` script checks for its compiler up front rather than
failing several minutes into a compile.

## What differs per platform

The launcher is one local web page everywhere. What changes is how that page
gets a window, which is decided at runtime in `src/mclauncher/desktop.py`:

- **Windows and macOS** have an OS webview, so pywebview draws a native window
  and the tray icon works.
- **Linux** has neither in a portable binary - pywebview would need PyGObject
  and WebKitGTK from the system, and pystray only has an X11 backend that no
  Wayland compositor serves - so the page opens in a Chromium `--app` window
  and there is no tray.

That is also why `pystray` and `pywebview` carry `sys_platform != 'linux'`
markers in `pyproject.toml`, and why the Linux build tells Nuitka not to follow
those imports.
