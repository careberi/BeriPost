"""Compose an on-brand "card" graphic with Pillow, in the Careberi brand.

Every part (title, tips, colors, logo, call-to-action) is drawn by code, so the
text is always correct and on-brand. Layout: a light brand wash, the logo and
wordmark up top, a navy title, an ocean card holding either bullet tips or a
short supporting line, and a berry call-to-action chip.

Fonts: Poppins (from assets/fonts). Falls back to a system font if missing.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .config import Config

log = logging.getLogger(__name__)

# Brand palette defaults (overridable via config.yaml brand.colors).
_DEFAULTS = {
    "navy": "16265C", "ocean": "2A5D9F", "azure": "2F80C2",
    "sky": "5AA9DE", "ice": "93CDEC", "berry": "D25680",
    "cloud": "F4F8FC", "muted": "6B7280",
}

_FONT_FILES = {
    "bold": "Poppins-Bold.ttf",
    "semibold": "Poppins-SemiBold.ttf",
    "medium": "Poppins-Medium.ttf",
    "regular": "Poppins-Regular.ttf",
}
_FALLBACK = {
    "bold": r"C:\Windows\Fonts\arialbd.ttf",
    "semibold": r"C:\Windows\Fonts\arialbd.ttf",
    "medium": r"C:\Windows\Fonts\arial.ttf",
    "regular": r"C:\Windows\Fonts\arial.ttf",
}


def _hex(value: str, default_key: str) -> tuple[int, int, int]:
    value = (value or _DEFAULTS[default_key]).lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _colors(config: Config) -> dict:
    c = config.brand.get("colors", {})
    return {
        "navy": _hex(c.get("primary", ""), "navy"),
        "ocean": _hex(c.get("gradient_to", ""), "ocean"),
        "azure": _hex("", "azure"),
        "sky": _hex("", "sky"),
        "ice": _hex("", "ice"),
        "berry": _hex(c.get("secondary", ""), "berry"),
        "cloud": _hex("", "cloud"),
        "muted": _hex("", "muted"),
    }


def _font(config: Config, weight: str, size: int) -> ImageFont.ImageFont:
    for path in (str(config.fonts_dir / _FONT_FILES[weight]), _FALLBACK[weight]):
        try:
            return ImageFont.truetype(path, size)
        except Exception:  # noqa: BLE001
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    lines, current = [], ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _wash(size: tuple[int, int], top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    w, h = size
    strip = Image.new("RGB", (1, h))
    for y in range(h):
        t = min((y / max(h - 1, 1)) * 1.4, 1.0)
        strip.putpixel((0, y), tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))  # type: ignore[arg-type]
    return strip.resize(size)


def _header(config: Config, img: Image.Image, draw: ImageDraw.ImageDraw, col: dict, margin: int) -> int:
    """Draw the logo + wordmark + tagline. Returns the y below the header."""
    x = margin
    top = 64
    logo_bottom = top
    if config.logo_path.exists():
        try:
            logo = Image.open(config.logo_path).convert("RGBA")
            lh = 96
            lw = int(logo.width * lh / logo.height)
            logo = logo.resize((lw, lh))
            img.paste(logo, (x, top), logo)
            x += lw + 22
            logo_bottom = top + lh
        except Exception:  # noqa: BLE001
            log.exception("Could not place logo on image.")
    name_font = _font(config, "bold", 52)
    draw.text((x, top + 6), "care", font=name_font, fill=col["navy"])
    care_w = draw.textlength("care", font=name_font)
    draw.text((x + care_w, top + 6), "beri", font=name_font, fill=col["azure"])
    tag = config.brand.get("tagline", "Home Health & Home Care").upper()
    draw.text((x + 2, top + 70), tag, font=_font(config, "medium", 17), fill=col["muted"])
    return max(logo_bottom, top + 96) + 40


def compose(
    config: Config,
    title: str,
    subtitle: str | None = None,
    bullets: list[str] | None = None,
    out_path: Path | None = None,
) -> Path:
    """Build the branded card image and save it. Returns the saved path."""
    width = int(config.images.get("width", 1080))
    height = int(config.images.get("height", 1080))
    col = _colors(config)
    margin = width // 13

    img = _wash((width, height), col["ice"], col["cloud"])
    draw = ImageDraw.Draw(img)

    title = (title or config.brand.get("name", "Careberi")).strip()
    bullets = [b.strip() for b in (bullets or []) if b.strip()]

    y = _header(config, img, draw, col, margin)

    # Title (auto-shrink to fit a few lines).
    box_w = width - 2 * margin
    size = 62
    while size > 34:
        tf = _font(config, "bold", size)
        tlines = _wrap(draw, title, tf, box_w)
        if len(tlines) <= 3:
            break
        size -= 4
    tf = _font(config, "bold", size)
    tlines = _wrap(draw, title, tf, box_w)
    line_h = int(size * 1.2)
    for ln in tlines:
        draw.text((margin, y), ln, font=tf, fill=col["navy"])
        y += line_h
    y += 24

    # Card. Measure the content first so the card hugs it.
    cx0, cx1 = margin, width - margin
    cy0 = y
    pad = 48
    tx = cx0 + pad
    inner = cx1 - cx0 - 2 * pad
    white = (255, 255, 255)
    faint = (232, 240, 250)

    items: list[dict] = []
    if bullets:
        if subtitle:
            hf = _font(config, "semibold", 38)
            items.append({"kind": "head", "font": hf, "lines": _wrap(draw, subtitle, hf, inner),
                          "lh": 48, "gap": 16, "fill": white})
        bf = _font(config, "regular", 32)
        for tip in bullets:
            items.append({"kind": "bullet", "font": bf, "lines": _wrap(draw, tip, bf, inner - 40),
                          "lh": 42, "gap": 14, "fill": faint})
    elif subtitle:
        bf = _font(config, "regular", 34)
        items.append({"kind": "para", "font": bf, "lines": _wrap(draw, subtitle, bf, inner),
                      "lh": 46, "gap": 0, "fill": faint})

    content_h = sum(len(it["lines"]) * it["lh"] + it["gap"] for it in items)
    card_h = content_h + 2 * pad
    max_bottom = height - 168
    cy1 = cy0 + min(max(card_h, 200), max_bottom - cy0)
    draw.rounded_rectangle([cx0, cy0, cx1, cy1], radius=34, fill=col["ocean"])

    ty = cy0 + pad
    for it in items:
        for i, ln in enumerate(it["lines"]):
            if it["kind"] == "bullet" and i == 0:
                draw.ellipse([tx, ty + 11, tx + 16, ty + 27], fill=col["ice"])
            x = tx + 40 if it["kind"] == "bullet" else tx
            draw.text((x, ty), ln, font=it["font"], fill=it["fill"])
            ty += it["lh"]
        ty += it["gap"]

    # Berry call-to-action chip.
    phone = config.brand.get("phone", "")
    chip = f"Call us at {phone}" if phone else "Follow for more caregiving tips"
    cf = _font(config, "bold", 30)
    cw = draw.textlength(chip, font=cf)
    chy0 = height - 120
    draw.rounded_rectangle([margin, chy0, margin + cw + 56, chy0 + 62], radius=31, fill=col["berry"])
    draw.text((margin + 28, chy0 + 14), chip, font=cf, fill=white)

    if out_path is None:
        out_path = config.images_dir / f"post_{int(time.time())}.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG")
    log.info("Composed card image saved to %s", out_path)
    return out_path
