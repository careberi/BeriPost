"""Compose an on-brand square image with Pillow.

Pipeline: pick a background (rotating through assets/backgrounds) -> crop to a
square -> darken for text readability -> draw the headline in the brand font ->
overlay the logo. Cost is zero because it uses your own backgrounds.

A clean hook is left for swapping in an AI image generator later: implement
`_ai_background()` and set images.generator: ai in config.yaml.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

from .config import Config

log = logging.getLogger(__name__)

_VALID_BG = {".jpg", ".jpeg", ".png", ".webp"}


def _hex(color: str, default: str) -> tuple[int, int, int]:
    color = (color or default).lstrip("#")
    return tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _list_backgrounds(config: Config) -> list[Path]:
    if not config.backgrounds_dir.exists():
        return []
    return sorted(
        p for p in config.backgrounds_dir.iterdir() if p.suffix.lower() in _VALID_BG
    )


def _pick_background(config: Config, size: tuple[int, int]) -> Image.Image:
    """Return a background image cropped to `size`, or a solid brand color."""
    backgrounds = _list_backgrounds(config)
    if backgrounds:
        # Rotate deterministically over time so the feed varies.
        idx = int(time.time() // 60) % len(backgrounds)
        try:
            bg = Image.open(backgrounds[idx]).convert("RGB")
            return _crop_to_fill(bg, size)
        except Exception:  # noqa: BLE001
            log.exception("Failed to open background %s; using solid color.", backgrounds[idx])
    primary = _hex(config.brand.get("colors", {}).get("primary", ""), "1F6F6F")
    return Image.new("RGB", size, primary)


def _crop_to_fill(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    target_w, target_h = size
    src_w, src_h = img.size
    scale = max(target_w / src_w, target_h / src_h)
    new = img.resize((int(src_w * scale), int(src_h * scale)))
    left = (new.width - target_w) // 2
    top = (new.height - target_h) // 2
    return new.crop((left, top, left + target_w, top + target_h))


# Well-known scalable fonts to try, in order, across operating systems.
_BOLD_CANDIDATES = [
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\segoeuib.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "DejaVuSans-Bold.ttf",
    "Arial Bold.ttf",
]
_REGULAR_CANDIDATES = [
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\segoeui.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "DejaVuSans.ttf",
    "Arial.ttf",
]


def _load_font(config: Config, bold: bool, size: int) -> ImageFont.ImageFont:
    # 1. A brand font the user dropped in assets/fonts.
    custom = config.fonts_dir / ("headline.ttf" if bold else "body.ttf")
    candidates = [str(custom)] if custom.exists() else []
    # 2. Common system fonts.
    candidates += _BOLD_CANDIDATES if bold else _REGULAR_CANDIDATES
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:  # noqa: BLE001 - try the next candidate
            continue
    # 3. Pillow's built-in default. Newer Pillow scales it with `size`.
    try:
        return ImageFont.load_default(size=size)  # Pillow >= 10.1
    except TypeError:
        return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
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


def _add_logo(config: Config, canvas: Image.Image) -> None:
    if not config.logo_path.exists():
        return
    try:
        logo = Image.open(config.logo_path).convert("RGBA")
        target_w = canvas.width // 4
        scale = target_w / logo.width
        logo = logo.resize((target_w, int(logo.height * scale)))
        margin = canvas.width // 25
        pos = (canvas.width - logo.width - margin, canvas.height - logo.height - margin)
        canvas.paste(logo, pos, logo)
    except Exception:  # noqa: BLE001
        log.exception("Could not overlay logo; continuing without it.")


def _ai_background(config: Config, headline: str, size):
    """Hook for a future AI image-generation backend. Not used by default."""
    raise NotImplementedError(
        "AI image generation is not wired up. Set images.generator back to 'templated', "
        "or implement this function to call an image API and return a PIL Image."
    )


def compose(config: Config, headline: str, out_path: Path | None = None) -> Path:
    """Build the post image and save it. Returns the saved path."""
    width = int(config.images.get("width", 1080))
    height = int(config.images.get("height", 1080))
    size = (width, height)

    if config.images.get("generator") == "ai":
        canvas = _ai_background(config, headline, size)
    else:
        canvas = _pick_background(config, size)

    # Darken for readability.
    canvas = ImageEnhance.Brightness(canvas).enhance(0.55)

    draw = ImageDraw.Draw(canvas)
    text_color = _hex(config.brand.get("colors", {}).get("text_on_image", ""), "FFFFFF")

    headline = (headline or config.brand.get("name", "Careberi")).strip()
    max_chars = int(config.images.get("headline_max_chars", 120))
    if len(headline) > max_chars:
        headline = headline[: max_chars - 1].rstrip() + "…"

    # Fit the headline: shrink font until it fits comfortably.
    margin = width // 10
    box_w = width - 2 * margin
    font_size = width // 9
    while font_size > 24:
        font = _load_font(config, bold=True, size=font_size)
        lines = _wrap(draw, headline, font, box_w)
        line_h = font_size + font_size // 4
        total_h = line_h * len(lines)
        if total_h <= height * 0.6 and len(lines) <= 6:
            break
        font_size -= 4

    font = _load_font(config, bold=True, size=font_size)
    lines = _wrap(draw, headline, font, box_w)
    line_h = font_size + font_size // 4
    total_h = line_h * len(lines)
    y = (height - total_h) // 2

    for line in lines:
        w = draw.textlength(line, font=font)
        x = (width - w) // 2
        # subtle shadow for contrast
        draw.text((x + 2, y + 2), line, font=font, fill=(0, 0, 0))
        draw.text((x, y), line, font=font, fill=text_color)
        y += line_h

    # Accent bar at the bottom in the brand secondary color.
    accent = _hex(config.brand.get("colors", {}).get("secondary", ""), "F4A259")
    draw.rectangle([0, height - height // 40, width, height], fill=accent)

    _add_logo(config, canvas)

    if out_path is None:
        out_path = config.images_dir / f"post_{int(time.time())}.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, "PNG")
    log.info("Composed image saved to %s", out_path)
    return out_path
