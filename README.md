# MCLauncher

A small Minecraft launcher for playing on your own server. Type a name, pick a
version, hit PLAY. It downloads the client jar, libraries, natives, assets and
even a matching Java runtime by itself.

There is no Microsoft/Mojang sign-in: your player UUID is derived from the name
you type, exactly the way a vanilla server computes UUIDs for offline players.
That means your server needs `online-mode=false` in `server.properties`, and
skins/Realms won't work. Normal singleplayer and your own server do.

## Running it

To run from source, use the script for your platform - each one syncs the
environment with `uv` and then starts the app:

| | |
|---|---|
| Windows | `packaging\windows\run.bat` (double-clickable) |
| Linux | `packaging/linux/run.sh` |
| macOS | `packaging/macos/run.sh` |

Or drive the module directly:

```sh
uv run python -m mclauncher              # launcher window
uv run python -m mclauncher --web        # open it in your browser instead
uv run python -m mclauncher --port 8713  # pin the server port (default: a free one)
uv run python -m mclauncher --wm-class   # print the window class (Linux window rules)
```

Requires [uv](https://docs.astral.sh/uv/). Everything else is installed by uv.
The window is 600x775; the layout is built for roughly that size.

The UI is a local web page on every platform, but how it gets a window differs:

| | Window | Tray while playing |
|---|---|---|
| **Windows / macOS** | pywebview, using the webview the OS already ships | yes |
| **Linux** | a Chromium "app" window - no tabs, no address bar, its own profile | no |

Linux gets no native webview because pywebview would need PyGObject and
WebKitGTK from the system, which cannot be frozen into a portable binary. It
also gets no tray icon: pystray only has an X11 backend, and Wayland
compositors have no XEmbed tray for it to use. So on Linux the launcher window
simply stays open while you play, with the *Stop game* button on it; closing
that window quits the launcher and leaves the game running.

Any Chromium fork will do (`chromium`, `google-chrome`, `brave`, `vivaldi`,
`microsoft-edge`), and `MCLAUNCHER_BROWSER` picks a specific one. With none of
them installed the page opens in your default browser instead.

**Several launchers can run at once.** Each instance takes its own free port, so
you can have one window per player and several Minecraft sessions going on the
same machine. If you do that, give each launcher its own **Game folder** under
Options — otherwise the sessions share `options.txt` and fight over
`logs/latest.log` (harmless, but noisy).

## What the window gives you

| | |
|---|---|
| **Player** | dropdown of names you've launched before, most recent first; type a new one and it sticks whether you press Enter or just click away, the person icon forgets the selected one |
| **Version to play** | every version Mojang publishes; flip *Snapshots* for snapshots, betas and alphas. Anything missing is downloaded on launch |
| **Fullscreen** | starts Minecraft fullscreen (passes `--fullscreen` to the client) |
| **Close on play** | quits the launcher once the game starts, instead of waiting in the tray. The game is launched detached, so it keeps running |
| **Options** | server to auto-join, game folder, Java path, memory, extra JVM args |
| **PLAY** | prepares and launches; on Windows/macOS the launcher then hides into the system tray, on Linux it stays put |
| **Console** | collapsed by default; holds download progress and the game's own log. Opens by itself if a launch fails |

On Windows and macOS, unless *Close on play* is ticked, the launcher sits in the
tray while the game runs (click the icon to bring it back, right-click for
*Stop game* / *Quit*); when Minecraft exits, the window comes back on its own.
On Linux there is no tray, so the window stays where it is instead.

Errors like `Failed to fetch user properties (401)` and `Could not authorize you
against Realms` in the console are normal — they're the game noticing there is
no Mojang session. The game still runs. A SkinsRestorer server may also warn
about "cracked" launchers on join; that warning goes to every offline-mode
player and is not about this launcher (dismiss it with
`/skin notification ignore-cracked-client`).

## Where things go

Windows keeps everything under `%APPDATA%`; Linux uses `~/.config` (or
`$XDG_CONFIG_HOME`).

| Windows | Linux | What |
|---|---|---|
| `%APPDATA%\.minecraft` | `~/.minecraft` | game folder by default (shared with the official launcher, so your worlds and options carry over) — changeable in Options |
| `%APPDATA%\MCLauncher\settings.json` | `~/.config/MCLauncher/settings.json` | usernames, last version, memory, paths, checkbox states |
| `%APPDATA%\MCLauncher\runtime\` | `~/.config/MCLauncher/runtime/` | Java runtimes downloaded from Mojang |
| `%APPDATA%\MCLauncher\version_manifest_v2.json` | `~/.config/MCLauncher/version_manifest_v2.json` | cached version list, so the launcher still opens offline |
| `%APPDATA%\MCLauncher\crash.log` / `launcher.log` | `~/.config/MCLauncher/crash.log` / `launcher.log` | only written if the launcher itself fails (a windowed build has no console) |
| — | `~/.config/MCLauncher/window/<port>/` | the Chromium profile each launcher window runs in - one per instance, swept when its launcher is gone. Safe to delete |
| `%LOCALAPPDATA%\MCLauncher\<version>\` | `~/.cache/MCLauncher/<version>/` | the binary unpacks itself here once per version (~170 MB). Safe to delete for versions you no longer run |

Java: an existing install is used when its major version matches what the
version needs — `JAVA_HOME`, `PATH`, and then the usual places (`/usr/lib/jvm`,
`/opt`, `~/.sdkman`, `~/.jdks` on Linux; vendor folders and the official
launcher's runtimes on Windows). Otherwise Mojang's own runtime is downloaded
once.

## Building a release

Each platform builds for itself; the scripts live in [`packaging/`](packaging/),
which has the full table of what is tested where.

```sh
packaging/linux/build-release.sh          # Linux    -> releases/MCLauncher-1.1.4-linux-x86_64
packaging/macos/build-release.sh          # macOS    -> releases/.../MCLauncher.app
packaging\windows\build-release.bat       # Windows  -> releases\MCLauncher-1.1.4-windows-amd64.exe
```

They all take the same arguments:

```sh
packaging/linux/build-release.sh              # patch bump 1.1.3 -> 1.1.4, then build
packaging/linux/build-release.sh minor        # 1.1.3 -> 1.2.0
packaging/linux/build-release.sh major        # 1.1.3 -> 2.0.0
packaging/linux/build-release.sh --set 2.0.0  # exact version
packaging/linux/build-release.sh --no-bump    # rebuild the current version
packaging/linux/build-release.sh --dry-run    # show the plan, change nothing
packaging/linux/build-release.sh patch --tag  # also create a git tag
```

Artifacts are named `MCLauncher-<version>-<os>-<arch>`, so builds of one
version for different machines sit side by side rather than overwriting each
other. The result needs no Python, uv or Java on the machine that runs it.

`src/mclauncher/__init__.py` holds the version; `pyproject.toml` is kept in step
with it. After building, the script checks that the filename, the exe's embedded
Windows file version (Windows only) and both source files all agree, and fails
the release if they don't. If the build fails, the version numbers are rolled
back.

To build without touching the version:

```sh
uv run python tools/build.py                  # onefile      -> releases/
uv run python tools/build.py --standalone     # folder build -> releases/ (starts fastest)
uv run python tools/build.py --clean          # wipe build/ first
uv run python tools/build.py --clean-releases # also empty releases/
uv run python tools/build.py --console        # keep a console window, for debugging startup
```

Nuitka compiles it, which takes roughly 20-25 minutes from cold. Only one build
can run at a time - a second one exits with a message instead of corrupting the
build tree.

## Installing

**Windows** needs no installer: the build is a single `.exe`, so copy it
wherever you want it.

**Linux** (tested on Omarchy / Arch):

```sh
packaging/linux/build-release.sh --no-bump
packaging/linux/install.sh
```

`install.sh` needs no root. It puts the binary in `~/.local/bin/mclauncher`, the
icon in `~/.local/share/icons/hicolor/256x256/apps/`, and a `.desktop` entry in
`~/.local/share/applications/`, then refreshes the desktop and icon caches - so
**MCLauncher** appears in the application launcher straight away.
`PREFIX=/usr/local sudo -E packaging/linux/install.sh` installs it system-wide,
and `packaging/linux/uninstall.sh` reverses either (your settings and
`~/.minecraft` are left alone).

Hyprland tiles the window by default. To float it at its intended size, add to
`~/.config/hypr/hyprland.conf`:

```
windowrule = float, class:^(chrome-127\.0\.0\.1__-MCLauncher)$
windowrule = size 600 775, class:^(chrome-127\.0\.0\.1__-MCLauncher)$
```

Run `mclauncher --wm-class` to confirm that class on your machine - it changes
if you use a non-Chromium-branded fork such as Brave.

**macOS** builds an `MCLauncher.app` that `packaging/macos/install.sh` copies
into `/Applications`. Untested so far - see [`packaging/README.md`](packaging/README.md).

## Layout

```
src/mclauncher/           the launcher itself
  core.py                 manifest, downloads, Java, launch command
  ui.py                   NiceGUI front-end
  desktop.py              picks between a native webview and a Chromium app window
  tray.py                 tray icon shown while playing (Windows/macOS)
  assets/icon.ico         Windows icon and tray image
  assets/icon.png         Linux/menu icon
tools/                    developer tooling, platform-neutral
  build.py                the Nuitka build
  release.py              version bumping + post-build version checks
  make_icon.py            regenerates the grass-block icon
packaging/                per-platform run, build and install scripts
  linux/  macos/  windows/  lib/
releases/                 build output (git-ignored)
build/                    Nuitka scratch space (git-ignored)
```

The icon is generic pixel art generated by `tools/make_icon.py`, not a Mojang
asset - drop your own `icon.ico` / `icon.png` in `src/mclauncher/assets/` to
change it.
