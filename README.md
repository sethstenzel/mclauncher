# MCLauncher

A small Minecraft launcher for playing on your own server. Type a name, pick a
version, hit PLAY. It downloads the client jar, libraries, natives, assets and
even a matching Java runtime by itself.

There is no Microsoft/Mojang sign-in: your player UUID is derived from the name
you type, exactly the way a vanilla server computes UUIDs for offline players.
That means your server needs `online-mode=false` in `server.properties`, and
skins/Realms won't work. Normal singleplayer and your own server do.

## Running it

Double-click **`launcher.bat`** (it runs `uv sync` and then starts the app), or:

```sh
uv run python -m mclauncher              # native desktop window
uv run python -m mclauncher --web        # open it in a browser tab instead
uv run python -m mclauncher --port 8713  # pin the server port (default: a free one)
```

Requires [uv](https://docs.astral.sh/uv/). Everything else is installed by uv.
The window is a fixed 600x775 and is not resizable; the layout is built for it.

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
| **PLAY** | prepares and launches; the launcher then hides into the system tray |
| **Console** | collapsed by default; holds download progress and the game's own log. Opens by itself if a launch fails |

Unless *Close on play* is ticked, the launcher sits in the tray while the game
runs (click the icon to bring it back, right-click for *Stop game* / *Quit*).
When Minecraft exits, the window comes back on its own.

Errors like `Failed to fetch user properties (401)` and `Could not authorize you
against Realms` in the console are normal — they're the game noticing there is
no Mojang session. The game still runs. A SkinsRestorer server may also warn
about "cracked" launchers on join; that warning goes to every offline-mode
player and is not about this launcher (dismiss it with
`/skin notification ignore-cracked-client`).

## Where things go

| Path | What |
|---|---|
| `%APPDATA%\.minecraft` | game folder by default (shared with the official launcher, so your worlds and options carry over) — changeable in Options |
| `%APPDATA%\MCLauncher\settings.json` | usernames, last version, memory, paths, checkbox states |
| `%APPDATA%\MCLauncher\runtime\` | Java runtimes downloaded from Mojang |
| `%APPDATA%\MCLauncher\version_manifest_v2.json` | cached version list, so the launcher still opens offline |
| `%APPDATA%\MCLauncher\crash.log` / `launcher.log` | only written if the launcher itself fails (a windowed build has no console) |
| `%LOCALAPPDATA%\MCLauncher\<version>\` | the .exe unpacks itself here once per version (~170 MB). Safe to delete for versions you no longer run |

Java: an existing install is used when its major version matches what the
version needs (`JAVA_HOME`, `PATH`, common vendor folders, the official
launcher's runtimes). Otherwise Mojang's own runtime is downloaded once.

## Building a release

```sh
build_release.bat              # patch bump 1.1.3 -> 1.1.4, then build
build_release.bat minor        # 1.1.3 -> 1.2.0
build_release.bat major        # 1.1.3 -> 2.0.0
build_release.bat --set 2.0.0  # exact version
build_release.bat --no-bump    # rebuild the current version
build_release.bat --dry-run    # show the plan, change nothing
build_release.bat patch --tag  # also create a git tag
```

`src/mclauncher/__init__.py` holds the version; `pyproject.toml` is kept in step
with it. After building, the script checks that the filename, the exe's embedded
Windows file version and both source files all agree, and fails the release if
they don't. If the build fails, the version numbers are rolled back.

To build without touching the version:

```sh
uv run python build.py                 # onefile exe  -> releases/
uv run python build.py --standalone    # folder build -> releases/ (starts fastest)
uv run python build.py --clean         # wipe build/ first
uv run python build.py --clean-releases # also empty releases/
uv run python build.py --console       # keep a console window, for debugging startup
```

Nuitka compiles it; the first build takes a while and may download a C compiler.
Only one build can run at a time — a second one exits with a message instead of
corrupting the build tree. The result needs no Python or uv on the machine that
runs it.

## Layout

```
launcher.bat            start it via uv
build_release.bat       bump the version and build -> releases/
build.py                the Nuitka build itself
tools/release.py        version bumping + post-build version checks
tools/make_icon.py      regenerates the grass-block icon
src/mclauncher/
  core.py               manifest, downloads, Java, launch command
  ui.py                 NiceGUI window
  tray.py               tray icon shown while playing
  assets/icon.ico
```

The icon is generic pixel art generated by `tools/make_icon.py`, not a Mojang
asset — drop your own `icon.ico` in `src/mclauncher/assets/` to change it.
