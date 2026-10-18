"""Draws the add-in's icons into resources/. Run from the repository root:

    python tools/make_icons.py

The command icon is a real gear outline from gearcore, filled with anti-aliasing.
The icons of the start, direction, extent type and measurement choices (UI-11) are
side views like Extrude's: the sketch plane as a dark line, the body extruding to
the right, objects in grey, dimensions in blue. Pure Python, no image library needed.
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
    write_png(path, [[FILL + (round(255 * a),) for a in line] for line in alpha])


def write_png(path: str, rgba):
    size = len(rgba)
    raw = b''.join(b'\x00' + b''.join(bytes(px) for px in line) for line in rgba)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (struct.pack('>I', len(data)) + kind + data
                + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff))

    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0))
                + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


BODY = (150, 170, 190)     # the extruded body, seen from the side
PLANE = (90, 90, 90)       # the sketch or start plane
OBJECT = (120, 120, 120)   # a start or extent object
ARROW = FILL               # dimensions and directions

BODY_TOP, BODY_BOTTOM = 0.22, 0.55   # the body's height in the icon
ARROW_Y = 0.76                       # where dimensions run, below the body


def body(x0, x1):
    return BODY, lambda x, y: x0 <= x <= x1 and BODY_TOP <= y <= BODY_BOTTOM


def plane(x):
    return PLANE, lambda x_, y: abs(x_ - x) <= 0.045 and 0.08 <= y <= 0.92


def obj(x):
    """A start or extent object: a thick grey bar the height of the icon."""
    return OBJECT, lambda x_, y: abs(x_ - x) <= 0.07 and 0.12 <= y <= 0.66


def arrow(x0, x1, left=True, right=True, ticks=False):
    """A dimension from x0 to x1 below the body, with arrow heads, and with ticks
    at the ends that have none."""
    def inside(x, y):
        dy = abs(y - ARROW_Y)
        shaft = x0 <= x <= x1 and dy <= 0.04
        head_r = right and x1 - 0.16 <= x <= x1 and dy <= (x1 - x) * 0.9
        head_l = left and x0 <= x <= x0 + 0.16 and dy <= (x - x0) * 0.9
        ends = [x0] * (not left) + [x1] * (not right)   # ticks where there is no head
        tick = ticks and any(abs(x - e) <= 0.035 for e in ends) and 0.64 <= y <= 0.88
        return shaft or head_r or head_l or tick
    return ARROW, inside


#: The side views, by resource folder: shapes drawn in order, later over earlier.
SIDE_VIEWS = {
    # Measurement (IN-27): the body centered on the start plane.
    'measurement/half_length': [body(0.12, 0.88), plane(0.5), arrow(0.5, 0.92, left=False, ticks=True)],
    'measurement/whole_length': [body(0.12, 0.88), plane(0.5), arrow(0.08, 0.92)],
    # Start (IN-18): where the body begins, relative to the sketch plane.
    'start/profile_plane': [body(0.3, 0.88), plane(0.3)],
    'start/offset': [body(0.56, 0.92), plane(0.1), arrow(0.1, 0.56)],
    'start/object': [body(0.55, 0.9), plane(0.16), obj(0.5)],
    # Direction (IN-21): which way the body goes from the start.
    'direction/one_side': [body(0.3, 0.88), plane(0.3), arrow(0.3, 0.92, left=False)],
    'direction/two_sides': [body(0.1, 0.9), plane(0.3), arrow(0.06, 0.3, right=False),
                            arrow(0.3, 0.94, left=False)],
    'direction/symmetric': [body(0.12, 0.88), plane(0.5), arrow(0.06, 0.5, right=False),
                            arrow(0.5, 0.94, left=False)],
    # Extent type (IN-22, IN-25): how far it goes.
    'extent/distance': [body(0.16, 0.8), plane(0.16), arrow(0.16, 0.8, ticks=True)],
    'extent/to_object': [body(0.16, 0.74), plane(0.16), obj(0.81), arrow(0.16, 0.74, left=False)],
}


def side_view(size: int, shapes):
    """An icon drawn from shapes in a unit square, y down, with SAMPLES x SAMPLES
    samples per pixel."""
    rows = []
    for row in range(size):
        line = []
        for col in range(size):
            totals, hits = [0.0, 0.0, 0.0], 0
            for sy in range(SAMPLES):
                for sx in range(SAMPLES):
                    x = (col + (sx + 0.5) / SAMPLES) / size
                    y = (row + (sy + 0.5) / SAMPLES) / size
                    color = None
                    for shape_color, inside in shapes:
                        if inside(x, y):
                            color = shape_color
                    if color:
                        hits += 1
                        totals = [t + c for t, c in zip(totals, color)]
            if hits:
                line.append(tuple(round(t / hits) for t in totals) + (round(255 * hits / SAMPLES ** 2),))
            else:
                line.append((0, 0, 0, 0))
        rows.append(line)
    return rows


def main():
    out = os.path.join(ROOT, 'resources')
    os.makedirs(out, exist_ok=True)
    for name, size in FILES:
        # Fewer, larger teeth at small sizes so that they stay recognizable.
        teeth = 8 if size <= 16 else 12
        png(os.path.join(out, name), coverage(gear_loops(teeth), size))
        print(name, size, 'px,', teeth, 'teeth')
    for folder, shapes in SIDE_VIEWS.items():
        path = os.path.join(out, *folder.split('/'))
        os.makedirs(path, exist_ok=True)
        for name, size in FILES:
            write_png(os.path.join(path, name), side_view(size, shapes))
        print(folder)


if __name__ == '__main__':
    main()
