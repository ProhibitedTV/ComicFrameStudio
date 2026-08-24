#!/usr/bin/env python3
"""Deterministic graphic-print finishing effects for ComicFrame Studio.

These effects run after Stable Diffusion. They intentionally provide the print
language that diffusion is bad at keeping temporally stable: ink reinforcement,
posterization, halftone screens, CMYK-like channel misregistration, and print grain.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageOps


@dataclass
class GraphicFXSettings:
    enabled: bool = True
    intensity: float = 0.85
    ink: bool = True
    posterize: bool = True
    halftone: bool = True
    misregistration: bool = True
    grain: bool = True


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _shift_channel(channel: Image.Image, dx: int, dy: int) -> Image.Image:
    """Shift a grayscale channel without wraparound artifacts."""
    out = Image.new("L", channel.size, 0)
    src_left = max(0, -dx)
    src_top = max(0, -dy)
    src_right = min(channel.width, channel.width - dx) if dx >= 0 else channel.width
    src_bottom = min(channel.height, channel.height - dy) if dy >= 0 else channel.height
    if src_right <= src_left or src_bottom <= src_top:
        return channel.copy()
    crop = channel.crop((src_left, src_top, src_right, src_bottom))
    out.paste(crop, (max(0, dx), max(0, dy)))
    return out


def _posterize_and_grade(image: Image.Image, intensity: float) -> Image.Image:
    # At maximum intensity use ~4 bits/channel; at low intensity stay closer to source.
    bits = max(4, min(7, int(round(7 - intensity * 3))))
    image = ImageOps.posterize(image.convert("RGB"), bits)
    image = ImageEnhance.Contrast(image).enhance(1.0 + 0.38 * intensity)
    image = ImageEnhance.Color(image).enhance(1.0 + 0.30 * intensity)
    return image


def _ink_edges(image: Image.Image, intensity: float) -> Image.Image:
    gray = ImageOps.autocontrast(image.convert("L"))
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edges = ImageOps.autocontrast(edges)
    # Keep broad/meaningful edges while avoiding a full Sobel-noise carpet.
    cutoff = int(38 + (1.0 - intensity) * 45)
    alpha = edges.point(lambda p: int(max(0, p - cutoff) * (0.72 + intensity * 0.65)))
    alpha = alpha.filter(ImageFilter.GaussianBlur(radius=max(0.15, 0.55 - intensity * 0.25)))
    ink = Image.new("RGBA", image.size, (4, 5, 10, 0))
    ink.putalpha(alpha)
    return Image.alpha_composite(image.convert("RGBA"), ink).convert("RGB")


def _halftone(image: Image.Image, intensity: float, frame_number: int) -> Image.Image:
    """Shadow-weighted dot screen with a stable tiny phase cycle across frames."""
    step = max(6, int(round(10 - intensity * 4)))
    cols = max(1, (image.width + step - 1) // step)
    rows = max(1, (image.height + step - 1) // step)
    lum = image.convert("L").resize((cols, rows), Image.Resampling.BOX)
    px = lum.load()

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    # A two-frame phase cycle feels printed/animated but avoids random flicker.
    phase = frame_number % 2
    max_radius = step * (0.34 + 0.10 * intensity)
    alpha = int(55 + 75 * intensity)
    for gy in range(rows):
        cy = gy * step + step // 2
        for gx in range(cols):
            darkness = 1.0 - (px[gx, gy] / 255.0)
            # Keep dots mostly in mids/shadows so highlights stay clean.
            amount = max(0.0, (darkness - 0.18) / 0.82)
            if amount <= 0.06:
                continue
            radius = max_radius * amount * intensity
            cx = gx * step + step // 2 + ((gy + phase) % 2) * max(1, step // 5)
            draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=(4, 5, 10, alpha))
    return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")


def _misregister(image: Image.Image, intensity: float, frame_number: int) -> Image.Image:
    r, g, b = image.convert("RGB").split()
    shift = max(1, int(round(1 + intensity * 4)))
    # Controlled 3-frame print-registration cycle, not random jitter.
    cycle = frame_number % 3
    dy = (-1, 0, 1)[cycle]
    r2 = _shift_channel(r, shift, dy)
    b2 = _shift_channel(b, -shift, -dy)
    split = Image.merge("RGB", (r2, g, b2))
    return Image.blend(image.convert("RGB"), split, 0.28 + 0.28 * intensity)


def _print_grain(image: Image.Image, intensity: float) -> Image.Image:
    noise = Image.effect_noise(image.size, 18 + 22 * intensity).convert("L")
    noise = ImageEnhance.Contrast(noise).enhance(0.55)
    texture = Image.merge("RGB", (noise, noise, noise))
    return Image.blend(image.convert("RGB"), texture, 0.018 + 0.032 * intensity)


def apply_graphic_fx(path: Path, settings: GraphicFXSettings, frame_number: int) -> None:
    """Apply the configured deterministic finishing stack in place."""
    if not settings.enabled:
        return
    intensity = _clamp01(settings.intensity)
    with Image.open(path) as src:
        image = src.convert("RGB")

    if settings.posterize:
        image = _posterize_and_grade(image, intensity)
    if settings.ink:
        image = _ink_edges(image, intensity)
    if settings.halftone:
        image = _halftone(image, intensity, frame_number)
    if settings.misregistration:
        image = _misregister(image, intensity, frame_number)
    if settings.grain:
        image = _print_grain(image, intensity)

    image.save(path, format="PNG", optimize=False)
