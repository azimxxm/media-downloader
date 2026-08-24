#!/usr/bin/env python3
"""Generate the macOS app icon (assets/icon.png + assets/icon.icns).

Follows Apple's macOS icon grid: a 1024x1024 canvas whose rounded-square art
occupies the centre 824x824, drawn as a superellipse rather than a circular
rounded rect so the corners match the system squircle.

Run:  python3 packaging/make_icon.py
"""

import math
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

CANVAS = 1024
ART = 824              # Apple's macOS app-icon art size inside a 1024 canvas
SUPERSAMPLE = 4        # draw big, downsample for clean anti-aliased edges
SQUIRCLE_N = 5.0       # superellipse exponent; ~5 matches the macOS shape

# Red -> pink -> purple: a nod to YouTube and Instagram without copying either.
GRADIENT = ((255, 61, 48), (228, 64, 95), (150, 47, 191))
GLYPH = (255, 255, 255, 255)


def superellipse(size, n=SQUIRCLE_N, steps=1024):
    """Points of a superellipse inscribed in a `size` square, centred on it."""
    radius = size / 2
    points = []
    for index in range(steps):
        theta = 2 * math.pi * index / steps
        cos_t, sin_t = math.cos(theta), math.sin(theta)
        x = radius * math.copysign(abs(cos_t) ** (2 / n), cos_t)
        y = radius * math.copysign(abs(sin_t) ** (2 / n), sin_t)
        points.append((radius + x, radius + y))
    return points


def vertical_gradient(size, stops):
    """A square gradient image blending the given colours top to bottom."""
    gradient = Image.new("RGB", (1, size))
    pixels = gradient.load()
    segments = len(stops) - 1

    for y in range(size):
        position = y / (size - 1) * segments
        index = min(int(position), segments - 1)
        blend = position - index
        start, end = stops[index], stops[index + 1]
        pixels[0, y] = tuple(
            round(start[channel] + (end[channel] - start[channel]) * blend)
            for channel in range(3)
        )

    return gradient.resize((size, size), Image.Resampling.BICUBIC)


def download_glyph(size):
    """White download mark: play-style arrowhead over a tray line."""
    layer = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(layer)

    centre = size / 2
    stem_width = size * 0.098
    stem_top = size * 0.262
    stem_bottom = size * 0.485

    # Stem
    draw.rounded_rectangle(
        [centre - stem_width / 2, stem_top, centre + stem_width / 2, stem_bottom],
        radius=stem_width / 2,
        fill=255,
    )

    # Arrowhead - a downward play triangle
    head_half = size * 0.172
    head_top = size * 0.425
    head_tip = size * 0.628
    draw.polygon(
        [(centre - head_half, head_top), (centre + head_half, head_top), (centre, head_tip)],
        fill=255,
    )

    # Tray
    tray_width = size * 0.435
    tray_height = size * 0.082
    tray_top = size * 0.702
    draw.rounded_rectangle(
        [centre - tray_width / 2, tray_top, centre + tray_width / 2, tray_top + tray_height],
        radius=tray_height / 2,
        fill=255,
    )

    return layer


def build_png():
    scale = SUPERSAMPLE
    canvas = CANVAS * scale
    art = ART * scale
    offset = (canvas - art) // 2

    image = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))

    # Squircle mask
    mask = Image.new("L", (art, art), 0)
    ImageDraw.Draw(mask).polygon(superellipse(art), fill=255)

    # Drop shadow, offset downward like every other macOS icon
    shadow = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 105), (offset, offset + int(14 * scale)), mask)
    shadow = shadow.filter(ImageFilter.GaussianBlur(int(11 * scale)))
    image = Image.alpha_composite(image, shadow)

    # Gradient body
    body = vertical_gradient(art, GRADIENT).convert("RGBA")

    # Soft top-light sheen. A linear alpha ramp, so there is no visible seam
    # where the highlight ends - an ellipse leaves a hard edge here.
    sheen = Image.new("RGBA", (art, art), (255, 255, 255, 0))
    ramp = Image.new("L", (1, art), 0)
    ramp_pixels = ramp.load()
    for y in range(art):
        fade = max(0.0, 1.0 - (y / art) / 0.55)
        ramp_pixels[0, y] = round(38 * fade ** 1.6)
    sheen.putalpha(ramp.resize((art, art), Image.Resampling.BILINEAR))
    body = Image.alpha_composite(body, sheen)

    # Glyph
    glyph_mask = download_glyph(art)
    glyph_layer = Image.new("RGBA", (art, art), GLYPH)
    glyph_layer.putalpha(glyph_mask)
    body = Image.alpha_composite(body, glyph_layer)

    body.putalpha(mask)
    image.alpha_composite(body, (offset, offset))

    return image.resize((CANVAS, CANVAS), Image.Resampling.LANCZOS)


def build_icns(png_path):
    """Turn the 1024px master into a multi-resolution .icns via iconutil."""
    iconset = ASSETS / "icon.iconset"
    iconset.mkdir(parents=True, exist_ok=True)

    master = Image.open(png_path)
    for size in (16, 32, 128, 256, 512):
        master.resize((size, size), Image.Resampling.LANCZOS).save(
            iconset / f"icon_{size}x{size}.png")
        master.resize((size * 2, size * 2), Image.Resampling.LANCZOS).save(
            iconset / f"icon_{size}x{size}@2x.png")

    icns = ASSETS / "icon.icns"
    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(icns)], check=True)

    for leftover in iconset.glob("*.png"):
        leftover.unlink()
    iconset.rmdir()
    return icns


def main():
    ASSETS.mkdir(parents=True, exist_ok=True)

    png_path = ASSETS / "icon.png"
    build_png().save(png_path)
    print(f"wrote {png_path.relative_to(ROOT)}")

    if sys.platform == "darwin":
        icns = build_icns(png_path)
        print(f"wrote {icns.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
