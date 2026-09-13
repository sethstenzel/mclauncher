"""System-tray icon shown while Minecraft is running.

The launcher window hides itself on launch so it is not sitting behind the game;
the tray icon is the way back to it, and it disappears when the game exits.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable


class Tray:
    """A tray icon with a tiny menu, safe to start/stop from any thread."""

    def __init__(self, icon_path: Path, title: str = "MCLauncher") -> None:
        self.icon_path = Path(icon_path)
        self.title = title
        self._icon = None
        self._thread: threading.Thread | None = None

    @property
    def active(self) -> bool:
        return self._icon is not None

    def start(
        self,
        on_show: Callable[[], None],
        on_stop_game: Callable[[], None] | None = None,
        on_quit: Callable[[], None] | None = None,
        tooltip: str = "",
    ) -> bool:
        if self._icon is not None:
            return True
        try:
            import pystray
            from PIL import Image
        except Exception:
            return False

        try:
            image = Image.open(self.icon_path)
            image.load()
        except Exception:
            image = None
        if image is None:
            return False

        def wrap(callback: Callable[[], None] | None, close: bool = False):
            def handler(icon, item):  # noqa: ARG001 - pystray signature
                if callback is not None:
                    callback()
                if close:
                    self.stop()

            return handler

        items = [pystray.MenuItem("Show launcher", wrap(on_show), default=True)]
        if on_stop_game is not None:
            items.append(pystray.MenuItem("Stop game", wrap(on_stop_game)))
        if on_quit is not None:
            items.append(pystray.MenuItem("Quit", wrap(on_quit, close=True)))

        self._icon = pystray.Icon(
            "mclauncher", image, tooltip or self.title, menu=pystray.Menu(*items)
        )
        self._thread = threading.Thread(target=self._icon.run, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        icon, self._icon = self._icon, None
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass
        self._thread = None
