"""Draws the add-in's icons into resources/. Run from the repository root:

    python tools/make_icons.py

The icon is a real gear outline from gearcore, filled with anti-aliasing. Pure
Python, no image library needed.
"""

import math
import os
import struct
import sys
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import gearcore  # noqa: E402

FILL = (58, 110, 165)      # steel blue, readable on light and dark toolbars
SAMPLES = 8                # sub-pixels per pixel and axis
#: File name and size in pixels. The @2x files are used on high-resolution displays.
FILES = (('16x16.png', 16), ('32x32.png', 32), ('64x64.png', 64),
         ('16x16@2x.png', 32), ('32x32@2x.png', 64))


def gear_loops(teeth: int):
    """Outer outline and bore of the icon gear as closed point lists, in mm."""
    # Stubby teeth with a positive profile shift: no undercut and wide tips, which
    # read better at icon size than standard proportions. A tooth count divisible
    # by 4 puts teeth on both axes, so the icon is symmetric.
    params = gearcore.GearParams(
        diameter=float(teeth), addendum=0.7, dedendum=1.0, fillet=0.3,
        profile_shift=0.4 if teeth < 12 else 0.3, bore=0.36 * teeth, tolerance=0.002)
    outline = gearcore.gear_outline(params)
    return [outline.sample(12)] + [hole.sample(12) for hole in outline.holes]


def coverage(loops, size: int):
    """Share of each pixel covered by the shape (even-odd rule), row by row."""
    extent = max(math.hypot(x, y) for x, y in loops[0])
    scale = (size / 2 - size / 32) / extent    # a small margin
    n = size * SAMPLES
    edges = []
    for loop in loops:
        pts = [((x * scale + size / 2) * SAMPLES, (size / 2 - y * scale) * SAMPLES) for x, y in loop]
        edges += [(a, b) for a, b in zip(pts, pts[1:] + pts[:1]) if a[1] != b[1]]
    counts = [[0] * size for _ in range(size)]
    for row in range(n):
        y = row + 0.5
        xs = sorted(a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
                    for a, b in edges if (a[1] <= y) != (b[1] <= y))
        for x0, x1 in zip(xs[0::2], xs[1::2]):
            for col in range(max(0, math.ceil(x0 - 0.5)), min(n, math.floor(x1 - 0.5) + 1)):
                counts[row // SAMPLES][col // SAMPLES] += 1
    return [[c / SAMPLES ** 2 for c in line] for line in counts]


def png(path: str, alpha):
    size = len(alpha)
    raw = b''.join(b'\x00' + b''.join(bytes(FILL + (round(255 * a),)) for a in line) for line in alpha)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (struct.pack('>I', len(data)) + kind + data
                + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff))

    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0))
                + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def main():
    out = os.path.join(ROOT, 'resources')
    os.makedirs(out, exist_ok=True)
    for name, size in FILES:
        # Fewer, larger teeth at small sizes so that they stay recognizable.
        teeth = 8 if size <= 16 else 12
        png(os.path.join(out, name), coverage(gear_loops(teeth), size))
        print(name, size, 'px,', teeth, 'teeth')


if __name__ == '__main__':
    main()
