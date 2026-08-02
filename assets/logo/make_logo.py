"""Regenerate the careberi logo mark (logo.png) from the brand style guide.

The mark is a cluster of blue circles with two leaves on top, taken exactly
from the vectors in careberi-style-guide.html. Run this only if you want to
recreate logo.png:  python assets/logo/make_logo.py

If you have an official logo file, you can just replace logo.png with it.
"""
from pathlib import Path

from PIL import Image, ImageDraw

# Brand palette (from the style guide)
NAVY = "#16265C"
AZURE = "#2F80C2"
SKY = "#5AA9DE"
ICE = "#93CDEC"

SS = 6  # supersample factor for smooth edges
VW, VH = 240, 300

# Circles: (cx, cy, fill).  radius is 24 for all.
CIRCLES = [
    (117, 120, ICE), (165, 120, SKY),
    (93, 158, AZURE), (141, 158, ICE), (189, 158, SKY),
    (93, 196, SKY), (141, 196, AZURE), (189, 196, ICE),
    (117, 234, ICE), (165, 234, SKY),
    (141, 272, AZURE),
]
R = 24

# Leaves: (P0, control1, P1, control2, P2, fill) - two quadratic beziers each.
LEAVES = [
    ((138, 104), (96, 98), (68, 42), (118, 62), (138, 104), SKY),   # left
    ((142, 104), (184, 98), (212, 42), (162, 62), (142, 104), ICE),  # right
]


def quad(p0, c, p1, n=40):
    pts = []
    for i in range(n + 1):
        t = i / n
        x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * c[0] + t ** 2 * p1[0]
        y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * c[1] + t ** 2 * p1[1]
        pts.append((x, y))
    return pts


def main():
    canvas = Image.new("RGBA", (VW * SS, VH * SS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    stroke = round(2.6 * SS)

    # Leaves first (behind the circles).
    for p0, c1, p1, c2, p2, fill in LEAVES:
        poly = quad(p0, c1, p1) + quad(p1, c2, p2)
        poly = [(x * SS, y * SS) for x, y in poly]
        draw.polygon(poly, fill=fill, outline=NAVY)
        # Thicker, smoother outline via line overlay.
        draw.line(poly + [poly[0]], fill=NAVY, width=stroke, joint="curve")

    # Circles.
    for cx, cy, fill in CIRCLES:
        box = [(cx - R) * SS, (cy - R) * SS, (cx + R) * SS, (cy + R) * SS]
        draw.ellipse(box, fill=fill, outline=NAVY, width=stroke)

    # Downscale for antialiasing.
    out = canvas.resize((600, 750), Image.LANCZOS)
    dest = Path(__file__).with_name("logo.png")
    out.save(dest, "PNG")
    print("Saved", dest)


if __name__ == "__main__":
    main()
