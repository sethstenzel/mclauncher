# MCLauncher

A small Minecraft: Java Edition launcher for playing on **your own personal
server** (a home server, a LAN box, a server you run for friends and family).
Type a name, pick a version, hit **PLAY**. It downloads the client, libraries,
assets and even a matching Java runtime by itself.

> [!WARNING]
> **This launcher is for personal, offline-mode Minecraft servers only.**
>
> - There is **no Microsoft/Mojang sign-in** and **no real user security**.
>   Your server must run with `online-mode=false`, and an offline-mode server
>   lets **anyone** join with **any name** they type — from this launcher or
>   from any other one.
> - The optional **launcher passwords** below only lock a name *inside this
>   launcher on this computer*. They are a convenience to stop people who share
>   a PC from casually playing as each other. They do **not** protect your
>   account, your server, or your name on the server, and anyone with access to
>   the computer can delete the password file.
> - If you need real identity checks, use the official launcher with an
>   online-mode server, or a server-side auth plugin.
>
> Please own a legitimate copy of Minecraft. This project is not affiliated with
> Mojang or Microsoft.

## Download

Grab `MCLauncher-<version>-windows-amd64.exe` from the
[latest release](https://github.com/sethstenzel/mclauncher/releases/latest) and
run it. It is a single portable executable — no installer, Python or Java
needed. Windows SmartScreen may warn about an unsigned app the first time;
choose *More info → Run anyway*.

## Server setup

In your server's `server.properties`:

```properties
online-mode=false
```

Restart the server, then point the launcher's **Options → Server to join on
launch** at it (for example `192.168.1.10:25565`), or join from the in-game
multiplayer menu.

Your player UUID is derived from your name exactly the way a vanilla
offline-mode server computes it, so the same name always gets the same
inventory, position and permissions. Skins and Realms don't work without a
Mojang session; singleplayer and your own server do.

## Using it

| | |
|---|---|
| **Player** | dropdown of names you've launched before, most recent first. Type a new one and it sticks whether you press Enter or just click away |
| **Lock icon** | set, change or remove a launcher password for the selected name (see below). Green = locked |
| **Person icon** | forgets the selected name from the dropdown |
| **Version to play** | every version Mojang publishes; flip *Snapshots* for snapshots, betas and alphas. Anything missing is downloaded on launch |
| **Fullscreen** | starts Minecraft fullscreen |
| **Close on play** | quits the launcher once the game starts, instead of waiting in the tray. The game keeps running |
| **Options** | server to auto-join, game folder, Java path, memory, extra JVM args |
| **PLAY** | prepares and launches; the launcher then hides in the system tray |
| **Console** | collapsed by default; download progress and the game's log. Opens by itself if a launch fails |

Unless *Close on play* is ticked, the launcher sits in the tray while the game
runs (click the icon to bring it back, right-click for *Stop game* / *Quit*).
When Minecraft exits, the window comes back on its own.

### Launcher passwords (optional)

Useful when several people share one computer and you'd rather your little
brother didn't play as you. Remember: this is a lock on the launcher, **not**
on the server (see the warning at the top).

1. Pick or type a player name and click the **lock icon** next to it.
2. Enter a password twice and click **Save**. Tick **Remember on this
   computer** if you don't want to be asked every time.
3. From then on, choosing that name shows a **Launcher password** box; PLAY
   won't start the game until the right password is entered. Tick
   **Remember** there to stop being asked for that name on this computer.

- To change the password, stop remembering it, or remove it, click the (green)
  lock icon again and enter the current password.
- Names are matched case-insensitively, so `Steve` and `steve` share one lock.
- Forgetting a name from the dropdown also forgets "remember", but keeps the
  password — typing that name again will ask for it.
- Only a salted PBKDF2 hash is stored, in `passwords.json`. "Remember" never
  saves the password itself; it just skips the prompt.
- Forgot a password? Delete that name's entry from `passwords.json` (or the
  whole file).

### Several players on one machine

Each launcher window takes its own free port, so you can run several at once
— one per player. Give each one its own **Game folder** under Options,
otherwise the sessions share `options.txt` and fight over `logs/latest.log`
(harmless, but noisy).

### Normal console noise

`Failed to fetch user properties (401)` and `Could not authorize you against
Realms` are expected — the game noticing there is no Mojang session. A
SkinsRestorer server may warn about "cracked" launchers on join; that goes to
every offline-mode player (dismiss it with
`/skin notification ignore-cracked-client`).

## Where things go

| Path | What |
|---|---|
| `%APPDATA%\.minecraft` | default game folder (shared with the official launcher, so worlds and options carry over) — changeable in Options |
| `%APPDATA%\MCLauncher\settings.json` | player names, last version, memory, paths, checkbox states |
| `%APPDATA%\MCLauncher\passwords.json` | launcher password hashes and "remember" flags |
| `%APPDATA%\MCLauncher\runtime\` | Java runtimes downloaded from Mojang |
| `%APPDATA%\MCLauncher\version_manifest_v2.json` | cached version list, so the launcher still opens offline |
| `%APPDATA%\MCLauncher\crash.log` / `launcher.log` | only written if the launcher itself fails |
| `%LOCALAPPDATA%\MCLauncher\<version>\` | the .exe unpacks itself here once per version (~170 MB). Safe to delete for versions you no longer run |

Java: an installed JDK/JRE is used when its major version fits what the
Minecraft version needs (`JAVA_HOME`, `PATH`, common vendor folders, the
official launcher's runtimes). Otherwise Mojang's own runtime is downloaded
once.

## Running from source

Requires [uv](https://docs.astral.sh/uv/); everything else is installed by uv.

```sh
launcher.bat                             # uv sync, then start the app
uv run python -m mclauncher              # native desktop window
uv run python -m mclauncher --web        # in a browser tab instead (localhost only)
uv run python -m mclauncher --port 8713  # pin the local server port (default: a free one)
```

The window is a fixed 600x775 and not resizable; the layout is built for it.

## Building a release

```sh
build_release.bat              # patch bump 1.2.0 -> 1.2.1, then build
build_release.bat minor        # 1.2.0 -> 1.3.0
build_release.bat major        # 1.2.0 -> 2.0.0
build_release.bat --set 2.0.0  # exact version
build_release.bat --no-bump    # rebuild the current version
build_release.bat --dry-run    # show the plan, change nothing
build_release.bat patch --tag  # also create a git tag
```

`src/mclauncher/__init__.py` holds the version; `pyproject.toml` and `uv.lock`
are kept in step with it. After building, the script checks that the filename,
the exe's embedded Windows file version and the source files all agree. If the
build fails, the version numbers are rolled back.

To build without touching the version:

```sh
uv run python build.py                  # onefile exe  -> releases/
uv run python build.py --standalone     # folder build -> releases/ (starts fastest)
uv run python build.py --clean          # wipe build/ first
uv run python build.py --clean-releases # also empty releases/
uv run python build.py --console        # keep a console window, for debugging startup
```

Nuitka compiles it; the first build takes a while and may download a C
compiler. Only one build can run at a time. The result needs no Python or uv on
the machine that runs it.
