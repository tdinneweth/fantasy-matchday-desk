#!/usr/bin/env python3
"""Draw the app icon: a floodlit pitch seen from above, ball on the centre spot.

Written straight to PNG bytes — this Mac has no image library, and the mark is
simple enough to describe in maths. Everything is supersampled 3x and averaged
down, which is where the smooth edges come from.

    ./icon.py            # writes the icons into icons/
"""

import os
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "icons")
SS = 3  # supersampling factor

# the dashboard's own ink and live-orange, so the icon belongs to the page
TURF_DARK = (17, 22, 33)
TURF_LIGHT = (25, 32, 46)
CHALK = (236, 240, 247)
BALL = (232, 80, 31)

STRIPES = 5
LINE_HALF = 0.011        # half-width of the halfway line
CIRCLE_R = 0.265         # centre circle radius
CIRCLE_HALF = 0.020      # half-thickness of its ring
BOX_W, BOX_H = 0.30, 0.085   # the two penalty boxes
BALL_R = 0.105
CORNER = 0.22            # rounded-corner radius, favicon only


def mix(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def sample(x, y):
    """Colour at a point in the unit square, plus coverage (0 outside the tile)."""
    # mown stripes
    band = int(y * STRIPES) % 2
    col = TURF_LIGHT if band else TURF_DARK

    dx, dy = x - 0.5, y - 0.5
    dist = (dx * dx + dy * dy) ** 0.5

    # halfway line and centre circle
    on_line = abs(dx) <= LINE_HALF
    on_circle = abs(dist - CIRCLE_R) <= CIRCLE_HALF
    # a penalty box at each end, drawn as an outline
    in_box_x = abs(dx) <= BOX_W / 2
    near_top = y <= BOX_H
    near_bottom = y >= 1 - BOX_H
    box_edge = (
        (in_box_x and (abs(y - BOX_H) <= LINE_HALF or abs(y - (1 - BOX_H)) <= LINE_HALF))
        or ((near_top or near_bottom) and abs(abs(dx) - BOX_W / 2) <= LINE_HALF)
    )

    if on_line or on_circle or box_edge:
        col = mix(col, CHALK, 0.9)

    if dist <= BALL_R:
        col = BALL

    return col


def rounded_alpha(x, y):
    """Coverage for a rounded square, so the favicon is not a hard block."""
    r = CORNER
    cx = min(max(x, r), 1 - r)
    cy = min(max(y, r), 1 - r)
    dx, dy = x - cx, y - cy
    return 0.0 if (dx * dx + dy * dy) ** 0.5 > r else 1.0


def render(size, rounded):
    big = size * SS
    rows = []
    for py in range(size):
        row = bytearray()
        for px in range(size):
            r = g = b = a = 0
            for sy in range(SS):
                for sx in range(SS):
                    x = (px * SS + sx + 0.5) / big
                    y = (py * SS + sy + 0.5) / big
                    cov = rounded_alpha(x, y) if rounded else 1.0
                    if cov:
                        c = sample(x, y)
                        r += c[0]
                        g += c[1]
                        b += c[2]
                        a += 255
            n = SS * SS
            row += bytes((r // n, g // n, b // n, a // n))
        rows.append(bytes(row))
    return rows


def write_png(path, size, rows):
    raw = b"".join(b"\x00" + row for row in rows)

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9))
    png += chunk(b"IEND", b"")
    with open(path, "wb") as fh:
        fh.write(png)
    return len(png)


def main():
    os.makedirs(OUT, exist_ok=True)
    # iOS masks the home-screen icon itself, so that one stays a full square
    wanted = [
        ("apple-touch-icon.png", 180, False),
        ("icon-192.png", 192, False),
        ("icon-512.png", 512, False),
        ("favicon-32.png", 32, True),
        ("favicon-180.png", 180, True),
    ]
    for name, size, rounded in wanted:
        n = write_png(os.path.join(OUT, name), size, render(size, rounded))
        print(f"{name:<22} {size}x{size}  {n / 1024:.1f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
