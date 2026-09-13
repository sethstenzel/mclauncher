"""NiceGUI front-end for the launcher."""

from __future__ import annotations

import ctypes
import queue
import socket
import subprocess
import sys
import threading
from pathlib import Path

from nicegui import app, ui

from . import __version__, core
from .tray import Tray

ICON_PATH = Path(__file__).resolve().parent / "assets" / "icon.ico"

GREEN = "#4caf50"
DARK = "#1a1a1f"
PANEL = "#24242b"


def total_ram_mb() -> int:
    """Physical RAM in MB, so the slider cannot be pushed past the machine."""
    if core.os_name() == "windows":
        class MemStatus(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemStatus()
        status.dwLength = ctypes.sizeof(MemStatus)
        try:
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
            return int(status.ullTotalPhys / (1024 * 1024))
        except Exception:
            return 16384
    try:
        import os

        return int(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / (1024 * 1024))
    except Exception:
        return 16384


class LauncherState:
    """Everything the background worker and the UI share."""

    def __init__(self) -> None:
        self.settings = core.Settings.load()
        self.versions: list[core.VersionEntry] = []
        self.events: queue.Queue[tuple] = queue.Queue()
        self.busy = False
        self.process: subprocess.Popen | None = None
        self.tray = Tray(ICON_PATH)

    # worker-thread side -------------------------------------------------- #
    def log(self, message: str) -> None:
        self.events.put(("log", message))

    def progress(self, done: int, total: int, label: str) -> None:
        self.events.put(("progress", done / max(total, 1), label))

    def status(self, text: str) -> None:
        self.events.put(("status", text))

    def finished(self, ok: bool, message: str) -> None:
        self.events.put(("finished", ok, message))


def version_options(state: LauncherState) -> list[str]:
    show_all = state.settings.show_snapshots
    return [v.id for v in state.versions if show_all or v.type == "release"]


@ui.page("/")
def main_page() -> None:  # noqa: C901 - one screen, kept together on purpose
    state = LauncherState()
    settings = state.settings
    max_ram = total_ram_mb()

    ui.query("body").style(f"background: {DARK}")
    ui.add_head_html(
        "<style>"
        ".mc-title{font-family:'Trebuchet MS',sans-serif;letter-spacing:.06em}"
        ".nicegui-log{font-family:Consolas,'Courier New',monospace;font-size:12px}"
        "</style>"
    )

    # 5% of the window height is left free below the content
    with ui.column().classes("w-full max-w-3xl mx-auto gap-4 p-4").style("padding-bottom: 5vh"):
        # -- header ------------------------------------------------------- #
        with ui.row().classes("w-full items-center gap-3 no-wrap"):
            ui.icon("sports_esports", size="36px").style(f"color:{GREEN}")
            with ui.column().classes("gap-0"):
                ui.label("MCLauncher").classes("mc-title text-2xl font-bold text-white")
                ui.label("offline-mode launcher for your home server").classes(
                    "text-xs text-gray-400"
                )
            ui.space()
            ui.label(f"v{__version__}").classes("text-xs text-gray-500 self-end")

        # -- login + version ---------------------------------------------- #
        with ui.card().classes("w-full").style(f"background:{PANEL}"):
            with ui.row().classes("w-full items-center gap-2 no-wrap"):
                username = (
                    ui.select(
                        options=list(settings.usernames),
                        value=settings.username or None,
                        label="Player",
                        with_input=True,
                        new_value_mode="add-unique",
                    )
                    .props('outlined dark dense fill-input hide-selected '
                           'hint="pick a saved name or type a new one"')
                    .classes("flex-1")
                )
                forget_btn = ui.button(icon="person_remove").props("flat dense round color=grey-5")
                forget_btn.tooltip("Forget the selected player name")
            with ui.row().classes("w-full items-center gap-2 no-wrap"):
                version = (
                    ui.select([], label="Version to play", with_input=True)
                    .props('outlined dark dense hint="downloads automatically if missing"')
                    .classes("flex-1")
                )
                refresh_btn = ui.button(icon="refresh").props("flat dense round color=grey-5")
                refresh_btn.tooltip("Re-fetch the version list from Mojang")
            with ui.row().classes("w-full items-center gap-4"):
                fullscreen = ui.checkbox("Fullscreen", value=settings.fullscreen)
                fullscreen.props("dense dark color=green")
                fullscreen.tooltip("Start Minecraft in fullscreen")
                close_after = ui.checkbox("Close on play", value=settings.close_on_launch)
                close_after.props("dense dark color=green")
                close_after.tooltip("Quit the launcher once Minecraft starts, instead of waiting in the tray")
                snapshots = ui.switch("Snapshots", value=settings.show_snapshots)
                snapshots.props("dense dark")
                snapshots.tooltip("Also list snapshots, betas and alphas")
            uuid_label = ui.label().classes("text-xs text-gray-500")

        # -- options ------------------------------------------------------ #
        with ui.expansion("Options", icon="tune").classes("w-full").style(
            f"background:{PANEL};border-radius:4px"
        ):
            with ui.column().classes("w-full gap-3 p-1"):
                server = (
                    ui.input(
                        "Server to join on launch (optional)",
                        value=settings.server,
                        placeholder="192.168.1.10:25565",
                    )
                    .props("outlined dark dense")
                    .classes("w-full")
                )
                game_dir = (
                    ui.input("Game folder", value=settings.game_dir)
                    .props("outlined dark dense")
                    .classes("w-full")
                )
                java_path = (
                    ui.input(
                        "Java executable (blank = auto-detect or download from Mojang)",
                        value=settings.java_path,
                    )
                    .props("outlined dark dense")
                    .classes("w-full")
                )
                jvm_args = (
                    ui.input("Extra JVM arguments", value=settings.jvm_args)
                    .props("outlined dark dense")
                    .classes("w-full")
                )
                ram_label = ui.label().classes("text-sm text-gray-300")
                ram = ui.slider(
                    min=1024,
                    max=max(2048, min(max_ram, 32768)),
                    step=512,
                    value=min(settings.ram_mb, max_ram),
                ).props("label-always color=green")
                ram_label.bind_text_from(ram, "value", lambda v: f"Memory: {int(v)} MB")

        # -- action ------------------------------------------------------- #
        with ui.row().classes("w-full items-center gap-3"):
            play = (
                ui.button("PLAY", icon="play_arrow")
                .props("unelevated size=lg color=green")
                .classes("flex-1 font-bold")
            )
            stop = ui.button("Stop game", icon="stop").props("outline color=red-5")
            stop.set_visibility(False)

        progress = ui.linear_progress(value=0, show_value=False).props("color=green").classes("w-full")
        status = ui.label("Starting up...").classes("text-sm text-gray-400")

        console_panel = (
            ui.expansion("Console", icon="terminal")
            .classes("w-full")
            .style(f"background:{PANEL};border-radius:4px")
        )
        with console_panel:
            console = ui.log(max_lines=600).classes("w-full h-[72px] rounded").style(
                "background:#101014;color:#c8c8d0;border:1px solid #33333d"
            )

        # -- helpers ------------------------------------------------------ #
        # Quasar throws away text typed into a select unless Enter is pressed,
        # so keep the keystrokes and commit them on blur / on launch.
        typed = {"text": ""}

        def remember_typed(event) -> None:
            typed["text"] = (event.args or "").strip() if isinstance(event.args, str) else ""

        def on_username_change(event) -> None:
            # Picking from the dropdown wins: drop any text typed before it, or the
            # blur handler below would write the old name back over the selection.
            value = getattr(event, "value", None)
            typed["text"] = value.strip() if isinstance(value, str) else ""
            refresh_uuid()

        def commit_typed() -> None:
            """Turn half-typed text into the selected player name."""
            text = typed["text"].strip()
            if not text or text == (username.value or ""):
                refresh_uuid()
                return
            if text not in username.options:
                username.options = list(username.options) + [text]
            username.value = text
            username.update()
            refresh_uuid()

        def refresh_uuid() -> None:
            name = (username.value or "").strip()
            if core.validate_username(name) is None:
                uuid_label.text = f"offline UUID: {core.offline_uuid(name)}"
            else:
                uuid_label.text = "username: 3-16 chars, letters/numbers/underscore"

        def apply_version_options(keep: str = "") -> None:
            options = version_options(state)
            version.options = options
            wanted = keep or version.value or settings.version
            version.value = wanted if wanted in options else (options[0] if options else None)
            version.update()

        def forget_player() -> None:
            name = (username.value or "").strip()
            if not name:
                return
            settings.forget_username(name)
            settings.save()
            username.options = list(settings.usernames)
            username.value = settings.username or None
            username.update()
            ui.notify(f"Forgot {name}", color="warning")

        def collect_settings() -> core.Settings:
            settings.remember_username((username.value or "").strip())
            settings.version = version.value or ""
            settings.game_dir = (game_dir.value or "").strip() or str(core.default_game_dir())
            settings.java_path = (java_path.value or "").strip()
            settings.jvm_args = (jvm_args.value or "").strip()
            settings.server = (server.value or "").strip()
            settings.ram_mb = int(ram.value)
            settings.show_snapshots = bool(snapshots.value)
            settings.fullscreen = bool(fullscreen.value)
            settings.close_on_launch = bool(close_after.value)
            settings.save()
            return settings

        # -- window <-> tray ----------------------------------------------- #
        # These are driven from the worker thread rather than the UI timer: a
        # hidden webview throttles client-side timers, so the window has to be
        # able to come back without the browser doing anything.
        def window():
            return getattr(app.native, "main_window", None)

        def show_window() -> None:
            win = window()
            if win is not None:
                win.show()
                win.restore()

        def stop_game() -> None:
            proc = state.process
            if proc and proc.poll() is None:
                state.log("--- stop requested ---")
                proc.terminate()

        def hide_to_tray() -> None:
            win = window()
            if win is None:  # running in a browser tab: nothing to hide
                return
            started = state.tray.start(
                on_show=show_window,
                on_stop_game=stop_game,
                on_quit=lambda: state.events.put(("quit",)),
                tooltip=f"MCLauncher - playing {settings.version}",
            )
            if started:
                win.hide()
            else:
                state.log("(tray icon unavailable - minimizing instead)")
                win.minimize()

        def restore_from_tray() -> None:
            state.tray.stop()
            show_window()

        # -- background work ---------------------------------------------- #
        def load_versions(force: bool = False) -> None:
            state.status("fetching version list...")
            try:
                state.versions = core.fetch_versions(max_age=0 if force else 900)
                state.events.put(("versions", None))
                state.status("ready")
            except Exception as exc:
                state.log(f"could not fetch version list: {exc}")
                state.status("offline - using already-installed versions")
                installed = Path(settings.game_dir) / "versions"
                if installed.is_dir():
                    state.versions = [
                        core.VersionEntry(p.name, "release", "", "")
                        for p in sorted(installed.iterdir())
                        if (p / f"{p.name}.json").is_file()
                    ]
                    state.events.put(("versions", None))

        def pump_game_output(proc: subprocess.Popen) -> None:
            assert proc.stdout is not None
            for line in proc.stdout:
                state.log(line.rstrip())
            code = proc.wait()
            state.process = None
            restore_from_tray()
            state.finished(code == 0, f"game exited with code {code}")

        def do_launch(cfg: core.Settings) -> None:
            try:
                installer = core.Installer(cfg.game_dir, log=state.log, progress=state.progress)
                plan = installer.prepare(
                    cfg.version,
                    cfg.username,
                    ram_mb=cfg.ram_mb,
                    extra_jvm=cfg.jvm_args,
                    java_path=cfg.java_path,
                )
                state.status("starting Minecraft...")
                proc = core.launch(
                    plan,
                    log=state.log,
                    server=cfg.server,
                    fullscreen=cfg.fullscreen,
                    capture_output=not cfg.close_on_launch,
                )
                state.process = proc
                state.events.put(("running", None))
                if cfg.close_on_launch:
                    # The game runs on its own from here; nothing left to watch.
                    state.events.put(("quit",))
                    return
                hide_to_tray()
                pump_game_output(proc)
            except core.Cancelled:
                state.finished(False, "cancelled")
            except Exception as exc:
                state.log(f"ERROR: {exc}")
                state.events.put(("show_console",))  # don't hide a failure in a closed panel
                state.finished(False, str(exc))

        def on_play() -> None:
            commit_typed()  # a name typed but never confirmed still counts
            cfg = collect_settings()
            problem = core.validate_username(cfg.username)
            if problem:
                ui.notify(f"Username: {problem}", color="negative")
                return
            if not cfg.version:
                ui.notify("Pick a version first", color="negative")
                return
            username.options = list(cfg.usernames)
            username.value = cfg.username
            username.update()
            state.busy = True
            play.disable()
            progress.value = 0
            status.text = "preparing..."
            console.push(f"--- launching {cfg.version} as {cfg.username} ---")
            threading.Thread(target=do_launch, args=(cfg,), daemon=True).start()

        def on_stop() -> None:
            stop_game()

        def on_refresh() -> None:
            status.text = "fetching version list..."
            threading.Thread(target=load_versions, args=(True,), daemon=True).start()

        # -- event pump (worker thread -> UI) ----------------------------- #
        def drain() -> None:
            while True:
                try:
                    event = state.events.get_nowait()
                except queue.Empty:
                    return
                kind = event[0]
                if kind == "log":
                    console.push(event[1])
                elif kind == "progress":
                    progress.value = event[1]
                    status.text = event[2]
                elif kind == "status":
                    status.text = event[1]
                elif kind == "versions":
                    apply_version_options()
                elif kind == "running":
                    status.text = "Minecraft is running - launcher hidden to the tray"
                    progress.value = 1
                    stop.set_visibility(True)
                elif kind == "finished":
                    state.busy = False
                    play.enable()
                    stop.set_visibility(False)
                    progress.value = 0
                    status.text = event[2]
                elif kind == "show_console":
                    console_panel.open()
                elif kind == "quit":
                    state.tray.stop()
                    app.shutdown()

        ui.timer(0.1, drain)
        app.on_shutdown(state.tray.stop)
        username.on_value_change(on_username_change)
        username.on("input-value", remember_typed)
        username.on("blur", lambda _: commit_typed())
        forget_btn.on_click(forget_player)
        snapshots.on_value_change(lambda _: apply_version_options())
        refresh_btn.on_click(on_refresh)
        play.on_click(on_play)
        stop.on_click(on_stop)

        refresh_uuid()
        state.versions = core.cached_versions()  # instant fill from the last run
        if state.versions:
            apply_version_options(settings.version)
        threading.Thread(target=load_versions, daemon=True).start()


WINDOW_SIZE = (600, 775)  # fixed: the layout is built for exactly this window


def free_port() -> int:
    """An unused port from the OS.

    Every launcher instance needs its own: a fixed port means the second copy
    cannot start while the first one is running.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def run(native: bool = True, port: int | None = None, reload: bool = False) -> None:
    if port is None:
        port = free_port()
    app.native.window_args["resizable"] = False
    app.native.window_args["min_size"] = WINDOW_SIZE
    ui.run(
        native=native,
        reload=reload,
        port=port,
        title="MCLauncher",
        favicon=str(ICON_PATH) if ICON_PATH.is_file() else "🎮",
        dark=True,
        window_size=WINDOW_SIZE,
        show=not native,
        storage_secret="mclauncher-local",
    )


def main() -> None:
    """`--web` opens a browser tab instead of a window; `--port N` pins the server port.

    Without `--port` each instance takes a free port of its own, so any number of
    launchers can run side by side.
    """
    native = "--web" not in sys.argv
    port = None
    if "--port" in sys.argv:
        index = sys.argv.index("--port")
        if index + 1 < len(sys.argv):
            try:
                port = int(sys.argv[index + 1])
            except ValueError:
                pass
    run(native=native, port=port)


if __name__ in {"__main__", "__mp_main__"}:
    main()
