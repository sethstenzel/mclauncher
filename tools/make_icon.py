"""Generate the launcher's grass-block icon.

Drawn here rather than downloaded so the shipped icon is our own generic
pixel art instead of a copyrighted Mojang asset. Run with:

    uv run --with pillow python tools/make_icon.py
"""

from __future__ import annotations

import random
from pathlib import Path

from PIL import Image

OUT = Path(__file__).resolve().parent.parent / "src" / "mclauncher" / "assets" / "icon.ico"

GRASS = [(0x5B, 0x9B, 0x36), (0x6A, 0xB0, 0x3E), (0x54, 0x8E, 0x30), (0x7A, 0xC0, 0x4A)]
DIRT = [(0x86, 0x60, 0x43), (0x76, 0x54, 0x3A), (0x95, 0x6B, 0x4B), (0x6B, 0x4C, 0x34)]
GRASS_ROWS = 5


def build_tile(size: int = 16) -> Image.Image:
    rng = random.Random(20250912)
    img = Image.new("RGBA", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            if y < GRASS_ROWS - 1:
                px[x, y] = (*rng.choice(GRASS), 255)
            elif y == GRASS_ROWS - 1:
                # ragged boundary between the grass cap and the dirt below
                px[x, y] = (*rng.choice(GRASS if rng.random() < 0.55 else DIRT), 255)
            else:
                px[x, y] = (*rng.choice(DIRT), 255)
    # simple bevel: lighten the top/left edge, darken the bottom/right
    for i in range(size):
        for coord, factor in (((i, 0), 1.18), ((0, i), 1.10), ((i, size - 1), 0.78), ((size - 1, i), 0.85)):
            r, g, b, a = px[coord]
            px[coord] = (min(255, int(r * factor)), min(255, int(g * factor)), min(255, int(b * factor)), a)
    return img


def main() -> None:
    tile = build_tile()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    frames = [tile.resize((s, s), Image.NEAREST) for s in sizes]
    frames[-1].save(OUT, format="ICO", sizes=[(s, s) for s in sizes])
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
