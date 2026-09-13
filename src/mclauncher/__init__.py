"""MCLauncher - a small offline-mode Minecraft launcher."""

import sys

__version__ = "1.1.3"


def ensure_streams() -> None:
    """Give a windowed build real stdout/stderr objects.

    A GUI-subsystem executable starts with both set to None, and uvicorn's
    logging config calls sys.stdout.isatty() while starting the server. Point
    them at a log file so the output is still recoverable.
    """
    if sys.stdout is not None and sys.stderr is not None:
        return
    stream = None
    try:
        from .core import launcher_data_dir

        path = launcher_data_dir() / "launcher.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_file() and path.stat().st_size > 1_000_000:
            path.unlink()
        stream = open(path, "a", encoding="utf-8", buffering=1)
    except Exception:
        import os

        stream = open(os.devnull, "w")
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream


def main() -> None:
    """Start the UI, leaving a crash log behind if it dies.

    A windowed build has no console, so an early failure would otherwise be
    completely silent.
    """
    ensure_streams()
    try:
        from .ui import main as run_ui

        run_ui()
    except BaseException:
        import datetime
        import traceback

        try:
            from .core import launcher_data_dir

            log = launcher_data_dir() / "crash.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            with open(log, "a", encoding="utf-8") as fh:
                fh.write(f"\n=== {datetime.datetime.now():%Y-%m-%d %H:%M:%S} ===\n")
                traceback.print_exc(file=fh)
        except Exception:
            pass
        raise
