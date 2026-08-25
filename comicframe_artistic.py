#!/usr/bin/env python3
"""Artistic expansion packs for ComicFrame Studio v1.8.

This module extends the v1.7 pipeline-aware style registry without forking the
renderer.  It adds grouped artistic/commercial presets, deterministic finishing
passes, and small library UI controls for browsing by family.
"""
from __future__ import annotations

from pathlib import Path

import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageOps

import comicframe_styles as styles
from comicframe_styles import StylePack


ART_NEGATIVE_BASE = (
    "extra limbs, extra fingers, missing fingers, duplicate person, warped face, changed identity, "
    "changed hairstyle, changed clothes, changed pose, cropped body, different camera angle, changed room layout, "
    "duplicated furniture, missing furniture, invented objects, melted geometry, malformed anatomy, random text, "
    "random lettering, logo artifacts"
)


def _neg(extra: str) -> str:
    return f"{ART_NEGATIVE_BASE}, {extra}" if extra else ART_NEGATIVE_BASE


ARTISTIC_STYLE_PACKS: dict[str, StylePack] = {
    # ---------- Fine art ----------
    "Watercolor Wash": StylePack(
        denoise=0.46, steps=27, cfg=5.3, fx=0.28,
        prompt=(
            "expressive watercolor animation frame, translucent layered pigment, visible cold-press paper character, "
            "soft wet-on-wet color blooms controlled by clean source contours, selective ink accents, luminous negative space, "
            "preserve exact identity, pose, hands, objects, architecture, camera position and action"
        ),
        negative=_neg("plastic 3d, hard digital cel blocks, neon glitch, heavy halftone, muddy face"),
        control_weight=0.94, guidance_end=0.91, temporal_strength=0.38,
        fx_ink=False, fx_posterize=False, fx_halftone=False, fx_misregister=False, fx_grain=False,
        finish="watercolor", description="Soft pigment-and-paper treatment with structure kept readable.",
    ),
    "Gouache Storybook": StylePack(
        denoise=0.47, steps=27, cfg=5.4, fx=0.34,
        prompt=(
            "hand-painted gouache storybook animation frame, opaque matte pigment, simplified confident shapes, dry-brush edges, "
            "warm illustrative color harmony, tactile paper surface, expressive but source-faithful faces, "
            "preserve pose, products, props, set geometry, lens perspective and complete composition"
        ),
        negative=_neg("photoreal gloss, neon cyberpunk, thin weak shapes, random background redesign"),
        control_weight=0.95, guidance_end=0.92, temporal_strength=0.40,
        fx_ink=False, fx_halftone=False, fx_misregister=False, finish="gouache",
        description="Opaque painterly shapes with warm storybook tactility.",
    ),
    "Oil Impasto": StylePack(
        denoise=0.53, steps=30, cfg=5.7, fx=0.24,
        prompt=(
            "cinematic oil painting animation frame, thick impasto brushwork, sculpted paint ridges, directional palette-knife marks, "
            "deep chiaroscuro, rich pigments, museum-canvas texture, source-faithful anatomy and spatial arrangement, "
            "preserve identity, pose, hands, furniture, objects and camera composition"
        ),
        negative=_neg("flat vector art, thin line art, anime screentone, random cubist anatomy, changed room"),
        control_weight=0.91, guidance_end=0.88, temporal_strength=0.31,
        fx_ink=False, fx_posterize=False, fx_halftone=False, fx_misregister=False, finish="impasto",
        description="Heavy painterly surface with embossed brush-energy simulation.",
    ),
    "Charcoal Study": StylePack(
        denoise=0.44, steps=26, cfg=5.2, fx=0.42,
        prompt=(
            "expressive charcoal figure-and-environment study, compressed black values, rubbed graphite-gray fields, broken dry charcoal contours, "
            "eraser-picked highlights, gestural but anatomically faithful drawing, preserve identity, pose, props and exact camera geometry"
        ),
        negative=_neg("full color, glossy rendering, clean vector line, watercolor color blooms, altered anatomy"),
        control_weight=0.97, guidance_end=0.94, temporal_strength=0.41,
        fx_posterize=False, fx_halftone=False, fx_misregister=False, finish="charcoal",
        description="Monochrome charcoal and rubbed-paper study with strong continuity.",
    ),
    "Pastel Dream": StylePack(
        denoise=0.48, steps=27, cfg=5.2, fx=0.20,
        prompt=(
            "soft chalk pastel animation frame, velvety pigment, luminous powdery color, gentle edge diffusion, subtle paper tooth, "
            "dreamlike color relationships while faces and body proportions remain recognizable, preserve action and source composition"
        ),
        negative=_neg("hard black cyberpunk ink, dirty glitch, crunchy sharpening, warped face, geometry redesign"),
        control_weight=0.93, guidance_end=0.90, temporal_strength=0.36,
        fx_ink=False, fx_posterize=False, fx_halftone=False, fx_misregister=False, finish="pastel",
        description="Soft chalk color and atmospheric edge diffusion.",
    ),
    "Ink Wash": StylePack(
        denoise=0.45, steps=26, cfg=5.3, fx=0.35,
        prompt=(
            "minimal ink-wash animation frame, expressive black sumi-e brush contours, diluted gray washes, broad empty paper space, "
            "economical marks, controlled tonal pooling, preserve exact subject identity, pose, hands, props, architecture and camera crop"
        ),
        negative=_neg("rainbow neon, glossy 3d, dense color rendering, random calligraphy, extra objects"),
        control_weight=0.97, guidance_end=0.94, temporal_strength=0.40,
        fx_posterize=False, fx_halftone=False, fx_misregister=False, finish="inkwash",
        description="Minimal monochrome brush-and-wash treatment.",
    ),

    # ---------- Cinema / genre ----------
    "Arthouse Melancholy": StylePack(
        denoise=0.43, steps=26, cfg=5.2, fx=0.32,
        prompt=(
            "arthouse illustrated film frame, restrained desaturated palette, soft winter light, deliberate negative space, subtle ink drawing, "
            "quiet melancholy, naturalistic body language, preserve exact actor identity, staging, set geometry and camera lens perspective"
        ),
        negative=_neg("hyper-saturated ad lighting, comic sound effects, exaggerated superhero pose, geometry drift"),
        control_weight=0.97, guidance_end=0.95, temporal_strength=0.43,
        fx_halftone=False, fx_misregister=False, finish="arthouse",
        description="Restrained desaturated cinematic illustration for reflective scenes.",
    ),
    "Grindhouse Damage": StylePack(
        denoise=0.50, steps=28, cfg=5.9, fx=0.72,
        prompt=(
            "grindhouse exploitation poster-film frame, rough inked illustration, hot dirty color, crushed blacks, distressed print stock, "
            "projector abuse and cheap theatrical energy, preserve identity, pose, props, vehicles, architecture and source framing"
        ),
        negative=_neg("clean luxury ad, pristine digital gradients, soft pastel calm, changed scene"),
        control_weight=0.92, guidance_end=0.89, temporal_strength=0.27,
        finish="grindhouse", description="Scratched, crushed, cheap-theater genre energy.",
    ),
    "VHS Horror": StylePack(
        denoise=0.49, steps=28, cfg=5.8, fx=0.64,
        prompt=(
            "illustrated VHS horror frame, oppressive analog darkness, smeared chroma, flashlight-level highlights, magnetic-tape ghosting, "
            "uneasy late-night home-video atmosphere, source-faithful person and room, preserve action, pose and camera composition"
        ),
        negative=_neg("clean studio commercial, bright cheerful palette, pristine vector art, scene replacement"),
        control_weight=0.93, guidance_end=0.90, temporal_strength=0.25,
        fx_halftone=False, finish="vhs", description="Horror illustration under deterministic VHS signal abuse.",
    ),
    "Dystopian Sci-Fi": StylePack(
        denoise=0.48, steps=28, cfg=5.8, fx=0.58,
        prompt=(
            "dystopian science-fiction graphic film frame, steel blue-gray atmosphere, industrial shadow geometry, sodium highlights, "
            "cold authoritarian architecture and technology without inventing new objects, preserve identity, pose, room and exact camera framing"
        ),
        negative=_neg("fantasy castle, random machinery, cheerful candy colors, transformed props, changed architecture"),
        control_weight=0.96, guidance_end=0.93, temporal_strength=0.37,
        fx_misregister=False, finish="dystopian",
        description="Cold industrial genre grade with restrained structural transformation.",
    ),
    "Dream-Pop Haze": StylePack(
        denoise=0.50, steps=28, cfg=5.4, fx=0.22,
        prompt=(
            "dream-pop illustrated music-video frame, luminous haze, soft bloom, pastel nocturnal colors, floating cinematic atmosphere, "
            "gentle graphic contours under diffused light, preserve recognizable identity, pose, objects, set and camera composition"
        ),
        negative=_neg("hard xerox blacks, ugly compression blocks, random geometry fracture, harsh product lighting"),
        control_weight=0.92, guidance_end=0.88, temporal_strength=0.32,
        fx_ink=False, fx_posterize=False, fx_halftone=False, fx_misregister=False, finish="dreampop",
        description="Soft luminous music-video haze with controlled identity retention.",
    ),
    "Surveillance State": StylePack(
        denoise=0.41, steps=25, cfg=5.3, fx=0.48,
        prompt=(
            "authoritarian surveillance illustration frame, severe monitoring-camera composition, monochrome phosphor atmosphere, "
            "hard documentary contours, clinical distance, compressed values, preserve exact people, objects, architecture and camera angle"
        ),
        negative=_neg("random HUD text, fake timestamps, logos, colorful fantasy light, camera-angle change"),
        control_weight=1.00, guidance_end=0.97, temporal_strength=0.44,
        fx_halftone=False, fx_misregister=False, finish="surveillance",
        description="Green-phosphor documentary/surveillance visual language without fake UI text.",
    ),

    # ---------- Print / poster ----------
    "Risograph Zine": StylePack(
        denoise=0.47, steps=27, cfg=5.7, fx=0.82,
        prompt=(
            "independent risograph zine frame, limited spot-color inks, rough paper tooth, visible plate overlap, bold editorial shapes, "
            "photocopied punk composition translated from the source, preserve identity, silhouette, objects and exact camera layout"
        ),
        negative=_neg("smooth photo gradients, luxury gloss, airbrush realism, warped product shape"),
        control_weight=0.94, guidance_end=0.91, temporal_strength=0.32,
        finish="riso", description="Limited-color risograph overlap with zine texture.",
    ),
    "Screenprint Poster": StylePack(
        denoise=0.45, steps=26, cfg=5.8, fx=0.78,
        prompt=(
            "hand-pulled screenprint poster frame, few bold ink colors, hard stencil-like shadow masses, thick confident contour shapes, "
            "flat graphic negative space, preserve exact subject silhouette, product geometry, environment and camera composition"
        ),
        negative=_neg("soft photographic gradients, muddy palette, thin weak lines, scene redesign"),
        control_weight=0.98, guidance_end=0.95, temporal_strength=0.40,
        fx_halftone=False, finish="screenprint", description="Hard limited-color posterization with strong structure.",
    ),
    "Pulp Cover": StylePack(
        denoise=0.51, steps=29, cfg=6.0, fx=0.76,
        prompt=(
            "painted pulp paperback cover frame, lurid dramatic lighting, sensational composition, bold hand-painted figures, "
            "aged cheap-paper color, high-stakes genre energy while preserving exact people, pose, objects and camera viewpoint"
        ),
        negative=_neg("minimal corporate catalog, weak contrast, random title text, altered identity"),
        control_weight=0.91, guidance_end=0.88, temporal_strength=0.27,
        finish="pulpcover", description="Lurid painted pulp-cover color and contrast without generated lettering.",
    ),
    "Album Art": StylePack(
        denoise=0.54, steps=30, cfg=6.0, fx=0.68,
        prompt=(
            "bold conceptual album-art frame, iconic silhouette, dramatic color blocking, expressive experimental illustration, "
            "strong focal hierarchy, striking negative space, preserve recognizable subject, core action, props and complete source framing"
        ),
        negative=_neg("random typography, fake band logo, bland stock-photo realism, duplicate subject"),
        control_weight=0.88, guidance_end=0.85, temporal_strength=0.24,
        finish="albumart", description="Higher-concept color and silhouette treatment for music visuals.",
    ),
    "Propaganda Poster": StylePack(
        denoise=0.45, steps=26, cfg=5.8, fx=0.70,
        prompt=(
            "monumental vintage propaganda poster illustration, simplified heroic shapes, limited red cream black palette, "
            "bold upward visual rhythm, hard graphic shadows, preserve exact subject, product, pose, hands and camera composition"
        ),
        negative=_neg("random slogans, generated text, illegible product, glossy photorealism, warped hands"),
        control_weight=0.98, guidance_end=0.96, temporal_strength=0.41,
        fx_halftone=False, fx_misregister=False, finish="posterprop",
        description="Vintage limited-palette heroic poster treatment distinct from the clean corporate preset.",
    ),
    "Underground Flyer": StylePack(
        denoise=0.50, steps=28, cfg=6.0, fx=0.88,
        prompt=(
            "underground punk xerox flyer frame, brutal photocopy contrast, torn-edge visual energy, marker-black contours, cheap toner texture, "
            "DIY collage pressure without adding text, preserve faces, pose, objects, room geometry and camera crop"
        ),
        negative=_neg("clean vector ad, soft watercolor, fake typography, random collage objects, changed identity"),
        control_weight=0.91, guidance_end=0.88, temporal_strength=0.25,
        fx_misregister=False, finish="flyer", description="Xerox-crushed DIY flyer aesthetic with no generated lettering.",
    ),

    # ---------- Experimental ----------
    "Glitch Collapse": StylePack(
        denoise=0.58, steps=31, cfg=6.2, fx=0.94,
        prompt=(
            "controlled digital-collapse art frame, recognizable subject trapped inside fractured signal geometry, offset image slices, "
            "compression-like planes, chromatic discontinuities, hostile media texture, preserve face, body, main action and source camera crop"
        ),
        negative=_neg("complete subject replacement, extra people, total scene rewrite, unreadable anatomy"),
        control_weight=0.82, guidance_end=0.79, temporal_strength=0.17, temporal_motion=0.05,
        finish="glitchcollapse", description="Aggressive horizontal signal fracture; intentionally low continuity pressure.",
    ),
    "Analog Decay": StylePack(
        denoise=0.52, steps=29, cfg=5.8, fx=0.80,
        prompt=(
            "decayed analog-memory illustration frame, faded color chemistry, damaged tape and print ghosts, unstable exposure, "
            "weathered personal-media atmosphere, preserve recognizable people, objects, environment and source composition"
        ),
        negative=_neg("pristine 8k commercial, clean white balance, random scene replacement, extra subjects"),
        control_weight=0.89, guidance_end=0.85, temporal_strength=0.22,
        finish="analogdecay", description="Faded, torn analog-memory look with deterministic signal wear.",
    ),
    "Liminal Haze": StylePack(
        denoise=0.52, steps=29, cfg=5.4, fx=0.18,
        prompt=(
            "liminal illustrated frame, empty-feeling fluorescent haze, washed institutional color, soft spatial unease, "
            "quiet uncanny atmosphere, retain exact architecture, object count, recognizable subject, pose and camera perspective"
        ),
        negative=_neg("busy cyberpunk detail, heavy black comic ink, random doors or hallways, geometry rewrite"),
        control_weight=0.95, guidance_end=0.91, temporal_strength=0.34,
        fx_ink=False, fx_posterize=False, fx_halftone=False, fx_misregister=False, finish="liminal",
        description="Soft uncanny institutional haze while preserving real spatial geometry.",
    ),
    "Relic Iconography": StylePack(
        denoise=0.54, steps=30, cfg=5.9, fx=0.54,
        prompt=(
            "aged devotional-icon inspired illustration frame, solemn frontal graphic presence, oxidized gold and earth pigments, "
            "cracked-panel atmosphere, symbolic stillness without adding religious text or new objects, preserve identity, pose and composition"
        ),
        negative=_neg("generated lettering, new symbols, extra halos on random objects, neon cyberpunk, changed face"),
        control_weight=0.90, guidance_end=0.87, temporal_strength=0.27,
        fx_misregister=False, finish="relic", description="Aged gold/earth icon-panel atmosphere for solemn experimental work.",
    ),
    "Brutalist Dreamstate": StylePack(
        denoise=0.55, steps=30, cfg=6.0, fx=0.74,
        prompt=(
            "brutalist dreamstate illustration frame, massive concrete-like tonal blocks, severe black white gray geometry, "
            "oppressive graphic scale, raw editorial composition, preserve subject silhouette, pose, actual architecture and camera frame"
        ),
        negative=_neg("cute pastel art, ornate fantasy architecture, extra structures, soft low contrast"),
        control_weight=0.90, guidance_end=0.86, temporal_strength=0.25,
        fx_misregister=False, finish="brutalist", description="Severe monochrome massing and concrete-like graphic weight.",
    ),
    "Signal Rupture": StylePack(
        denoise=0.57, steps=30, cfg=6.1, fx=0.92,
        prompt=(
            "signal-rupture experimental animation frame, violent RGB separation, displaced electronic bands, fractured broadcast geometry, "
            "sharp media-art discontinuity, recognizable subject remains anchored, preserve face, body, main action and source crop"
        ),
        negative=_neg("complete image replacement, extra bodies, illegible face, random text, smooth pristine signal"),
        control_weight=0.83, guidance_end=0.80, temporal_strength=0.16, temporal_motion=0.05,
        finish="rupture", description="Maximum electronic tearing while keeping the central subject legible.",
    ),

    # ---------- Commercial / product ----------
    "Luxury Ad": StylePack(
        denoise=0.39, steps=25, cfg=5.2, fx=0.20,
        prompt=(
            "luxury editorial product illustration frame, immaculate controlled highlights, elegant deep shadows, premium material rendering, "
            "minimal visual noise, refined composition, preserve exact product silhouette, branding-free surfaces, hands, face and camera angle"
        ),
        negative=_neg("grunge, cheap print damage, random logo, warped product, clutter, aggressive glitch"),
        control_weight=1.02, guidance_end=0.97, temporal_strength=0.45,
        fx_ink=False, fx_posterize=False, fx_halftone=False, fx_misregister=False, fx_grain=False,
        finish="luxury", description="Polished high-end product illustration with maximum shape fidelity.",
    ),
    "Minimal Catalog": StylePack(
        denoise=0.36, steps=24, cfg=5.0, fx=0.12,
        prompt=(
            "minimal catalog illustration frame, clean neutral light, restrained linework, simple background hierarchy, accurate material color, "
            "product-first composition, preserve exact product dimensions, person identity, hands, environment and camera framing"
        ),
        negative=_neg("dramatic grunge, neon shift, random props, warped product proportions, clutter"),
        control_weight=1.05, guidance_end=0.99, temporal_strength=0.48,
        fx_ink=False, fx_posterize=False, fx_halftone=False, fx_misregister=False, fx_grain=False,
        finish="catalog", description="Near-clean catalog redraw for product fidelity and low visual noise.",
    ),
    "Hype Drop": StylePack(
        denoise=0.47, steps=27, cfg=5.9, fx=0.60,
        prompt=(
            "high-energy limited-drop campaign illustration, bold saturated color, hard flash-like shadows, streetwear launch energy, "
            "clean product silhouette, punchy graphic framing, preserve identity, pose, hands, item geometry and camera composition"
        ),
        negative=_neg("muddy beige palette, weak contrast, random typography, distorted product, changed pose"),
        control_weight=0.97, guidance_end=0.94, temporal_strength=0.37,
        finish="hype", description="Saturated launch-campaign energy for products and merch.",
    ),
    "Infomercial Fever Dream": StylePack(
        denoise=0.52, steps=28, cfg=6.0, fx=0.76,
        prompt=(
            "surreal late-night infomercial illustration frame, aggressively cheerful studio lighting, oversaturated product-demo color, "
            "cheap broadcast energy drifting into absurdity, preserve product shape, presenter identity, hands, set and exact camera framing"
        ),
        negative=_neg("dark subtle arthouse palette, unreadable product, random prices or text, scene replacement"),
        control_weight=0.94, guidance_end=0.91, temporal_strength=0.29,
        finish="infomercial", description="Bright absurd product-demo broadcast treatment for comedic promos.",
    ),
    "Hero Tech Promo": StylePack(
        denoise=0.40, steps=25, cfg=5.4, fx=0.30,
        prompt=(
            "hero technology launch illustration frame, cool premium lighting, precise industrial contours, controlled blue-white highlights, "
            "confident keynote-ad energy, preserve exact device shape, ports, hands, face, set geometry and camera perspective"
        ),
        negative=_neg("random circuitry, invented ports, warped device, grunge overload, fake UI text"),
        control_weight=1.03, guidance_end=0.98, temporal_strength=0.45,
        fx_halftone=False, fx_misregister=False, fx_grain=False, finish="herotech",
        description="Precise cool-toned tech-launch treatment with strong geometry protection.",
    ),
    "Clean Ecommerce": StylePack(
        denoise=0.34, steps=23, cfg=4.9, fx=0.08,
        prompt=(
            "clean ecommerce illustration frame, neutral accurate color, soft even studio light, unobtrusive contour cleanup, "
            "faithful product and garment rendering, preserve exact dimensions, identity, pose, hands, background and camera crop"
        ),
        negative=_neg("dramatic stylization, color cast, random props, warped product, aggressive shadows, texture noise"),
        control_weight=1.08, guidance_end=1.0, temporal_strength=0.50,
        fx_ink=False, fx_posterize=False, fx_halftone=False, fx_misregister=False, fx_grain=False,
        finish="ecommerce", description="Maximum fidelity commercial redraw with minimal artistic interference.",
    ),
}


STYLE_CATEGORIES: dict[str, str] = {
    "Video Fidelity · RTX 3060": "Core",
    "Graphic Shock · maximum print": "Core",
    "Comic Punch · strong": "Core",
    "Clean Graphic Novel": "Core",
    "Neo-Noir": "Cinema & Genre",
    "Cyberpunk Print": "Print & Poster",
    "Pulp Horror": "Cinema & Genre",
    "Retro 70s Print": "Print & Poster",
    "Manga Motion": "Print & Poster",
    "Dream Collapse": "Experimental",
    "Corporate Propaganda": "Commercial",
    "Analog Broadcast": "Cinema & Genre",
    "Structure First · ControlNet test": "Diagnostic",
    "Diffusion Only · diagnostic": "Diagnostic",
}
STYLE_CATEGORIES.update({name: category for category, names in {
    "Fine Art": ["Watercolor Wash", "Gouache Storybook", "Oil Impasto", "Charcoal Study", "Pastel Dream", "Ink Wash"],
    "Cinema & Genre": ["Arthouse Melancholy", "Grindhouse Damage", "VHS Horror", "Dystopian Sci-Fi", "Dream-Pop Haze", "Surveillance State"],
    "Print & Poster": ["Risograph Zine", "Screenprint Poster", "Pulp Cover", "Album Art", "Propaganda Poster", "Underground Flyer"],
    "Experimental": ["Glitch Collapse", "Analog Decay", "Liminal Haze", "Relic Iconography", "Brutalist Dreamstate", "Signal Rupture"],
    "Commercial": ["Luxury Ad", "Minimal Catalog", "Hype Drop", "Infomercial Fever Dream", "Hero Tech Promo", "Clean Ecommerce"],
}.items() for name in names})


STYLE_STABILITY: dict[str, str] = {}
for _name in list(styles.STYLE_PACKS) + list(ARTISTIC_STYLE_PACKS):
    _category = STYLE_CATEGORIES.get(_name, "Core")
    if _category in {"Commercial", "Diagnostic"} or _name in {"Video Fidelity · RTX 3060", "Clean Graphic Novel"}:
        STYLE_STABILITY[_name] = "High"
    elif _category == "Experimental" or _name in {"Graphic Shock · maximum print", "Dream Collapse"}:
        STYLE_STABILITY[_name] = "Experimental"
    else:
        STYLE_STABILITY[_name] = "Medium"


_BASE_STYLE_FINISH = styles.apply_style_finish
_REGISTERED = False


def _translate(image: Image.Image, dx: int, dy: int) -> Image.Image:
    out = Image.new("RGB", image.size, (0, 0, 0))
    left = max(0, -dx)
    top = max(0, -dy)
    right = min(image.width, image.width - dx) if dx >= 0 else image.width
    bottom = min(image.height, image.height - dy) if dy >= 0 else image.height
    if right > left and bottom > top:
        out.paste(image.crop((left, top, right, bottom)), (max(0, dx), max(0, dy)))
    return out


def _scanlines(image: Image.Image, frame_number: int, spacing: int = 4, alpha: int = 20) -> Image.Image:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for y in range(frame_number % spacing, image.height, spacing):
        draw.line((0, y, image.width, y), fill=(0, 0, 0, alpha), width=1)
    return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")


def _scratches(image: Image.Image, frame_number: int, count: int = 7) -> Image.Image:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for i in range(count):
        x = (frame_number * 37 + i * 97) % max(1, image.width)
        shade = 210 if i % 3 else 20
        draw.line((x, 0, x + (i % 2), image.height), fill=(shade, shade, shade, 28 + (i % 3) * 8), width=1)
    return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")


def _band_shift(image: Image.Image, frame_number: int, magnitude: int = 8, bands: int = 4) -> Image.Image:
    out = image.copy()
    h = max(1, image.height // bands)
    for i in range(bands):
        y0 = i * h
        y1 = image.height if i == bands - 1 else min(image.height, y0 + h)
        phase = ((frame_number + i * 3) % 5) - 2
        dx = phase * magnitude // 2
        band = image.crop((0, y0, image.width, y1))
        shifted = _translate(band, dx, 0)
        out.paste(shifted, (0, y0))
    return out


def _mono_tint(image: Image.Image, black: tuple[int, int, int], white: tuple[int, int, int], contrast: float = 1.0) -> Image.Image:
    gray = ImageOps.autocontrast(image.convert("L"), cutoff=1)
    gray = ImageEnhance.Contrast(gray).enhance(contrast)
    return ImageOps.colorize(gray, black=black, white=white).convert("RGB")


def _rgb_split(image: Image.Image, shift: int) -> Image.Image:
    r, g, b = image.convert("RGB").split()
    r = _translate(Image.merge("RGB", (r, r, r)), shift, 0).split()[0]
    b = _translate(Image.merge("RGB", (b, b, b)), -shift, 0).split()[0]
    return Image.merge("RGB", (r, g, b))


def _apply_artistic_finish(path: Path, style_name: str, frame_number: int) -> None:
    pack = ARTISTIC_STYLE_PACKS.get(style_name)
    if not pack:
        _BASE_STYLE_FINISH(path, style_name, frame_number)
        return

    with Image.open(path) as src:
        image = src.convert("RGB")

    finish = pack.finish
    if finish == "watercolor":
        softened = image.filter(ImageFilter.SMOOTH_MORE).filter(ImageFilter.GaussianBlur(0.65))
        paper = Image.new("RGB", image.size, (246, 242, 230))
        image = Image.blend(softened, paper, 0.06)
        image = ImageEnhance.Color(image).enhance(1.08)
    elif finish == "gouache":
        image = ImageOps.posterize(image, 5)
        image = image.filter(ImageFilter.SMOOTH_MORE)
        image = ImageEnhance.Color(image).enhance(1.12)
        image = ImageEnhance.Contrast(image).enhance(1.04)
    elif finish == "impasto":
        relief = image.convert("L").filter(ImageFilter.EMBOSS)
        relief = ImageEnhance.Contrast(relief).enhance(1.8)
        relief_rgb = Image.merge("RGB", (relief, relief, relief))
        image = Image.blend(image, ImageChops.screen(image, relief_rgb), 0.16)
        image = ImageEnhance.Color(image).enhance(1.10)
    elif finish == "charcoal":
        gray = ImageOps.autocontrast(image.convert("L"), cutoff=1)
        edges = ImageOps.invert(gray.filter(ImageFilter.FIND_EDGES))
        gray = ImageChops.multiply(gray, edges)
        gray = ImageEnhance.Contrast(gray).enhance(1.32)
        image = Image.merge("RGB", (gray, gray, gray))
    elif finish == "pastel":
        image = image.filter(ImageFilter.GaussianBlur(0.55))
        image = ImageEnhance.Brightness(image).enhance(1.06)
        image = ImageEnhance.Color(image).enhance(1.16)
        chalk = Image.new("RGB", image.size, (246, 232, 238))
        image = Image.blend(image, chalk, 0.055)
    elif finish == "inkwash":
        gray = ImageOps.autocontrast(image.convert("L"), cutoff=1)
        gray = ImageOps.posterize(gray, 5)
        paper = Image.new("L", image.size, 242)
        gray = Image.blend(gray, paper, 0.08)
        image = Image.merge("RGB", (gray, gray, gray))

    elif finish == "arthouse":
        image = ImageEnhance.Color(image).enhance(0.56)
        image = ImageEnhance.Contrast(image).enhance(0.94)
        cool = Image.new("RGB", image.size, (120, 138, 152))
        image = Image.blend(image, cool, 0.055)
    elif finish == "grindhouse":
        image = ImageEnhance.Contrast(image).enhance(1.24)
        image = ImageEnhance.Color(image).enhance(1.12)
        warm = Image.new("RGB", image.size, (112, 52, 26))
        image = Image.blend(image, warm, 0.07)
        image = _scratches(image, frame_number, 9)
    elif finish == "vhs":
        ghost = _translate(image, 3 + frame_number % 3, 0)
        image = Image.blend(image, ghost, 0.10)
        image = _band_shift(image, frame_number, 5, 6)
        image = _scanlines(image, frame_number, 3, 24)
        image = ImageEnhance.Color(image).enhance(0.82)
    elif finish == "dystopian":
        image = ImageEnhance.Color(image).enhance(0.52)
        image = ImageEnhance.Contrast(image).enhance(1.14)
        steel = Image.new("RGB", image.size, (56, 82, 96))
        image = Image.blend(image, steel, 0.10)
    elif finish == "dreampop":
        glow = image.filter(ImageFilter.GaussianBlur(2.2))
        image = ImageChops.screen(image, glow)
        image = Image.blend(image, glow, 0.26)
        tint = Image.new("RGB", image.size, (176, 144, 205))
        image = Image.blend(image, tint, 0.06)
    elif finish == "surveillance":
        image = _mono_tint(image, (0, 8, 2), (154, 244, 171), 1.20)
        image = _scanlines(image, frame_number, 4, 22)

    elif finish == "riso":
        image = ImageOps.posterize(image, 4)
        split = _rgb_split(image, 2 + frame_number % 2)
        image = Image.blend(image, split, 0.34)
        paper = Image.new("RGB", image.size, (239, 229, 211))
        image = Image.blend(image, paper, 0.07)
    elif finish == "screenprint":
        image = ImageOps.posterize(image, 3)
        image = ImageEnhance.Contrast(image).enhance(1.26)
        image = ImageEnhance.Color(image).enhance(1.10)
    elif finish == "pulpcover":
        image = ImageEnhance.Contrast(image).enhance(1.22)
        image = ImageEnhance.Color(image).enhance(1.20)
        warm = Image.new("RGB", image.size, (152, 78, 38))
        image = Image.blend(image, warm, 0.06)
    elif finish == "albumart":
        image = ImageEnhance.Contrast(image).enhance(1.18)
        image = ImageEnhance.Color(image).enhance(1.34)
        image = ImageEnhance.Sharpness(image).enhance(1.12)
    elif finish == "posterprop":
        image = ImageOps.posterize(image, 3)
        image = ImageEnhance.Contrast(image).enhance(1.28)
        warm = Image.new("RGB", image.size, (188, 70, 46))
        image = Image.blend(image, warm, 0.08)
    elif finish == "flyer":
        gray = ImageOps.autocontrast(image.convert("L"), cutoff=1)
        gray = ImageOps.posterize(gray, 2)
        gray = ImageEnhance.Contrast(gray).enhance(1.55)
        image = Image.merge("RGB", (gray, gray, gray))
        image = _band_shift(image, frame_number, 2, 7)

    elif finish == "glitchcollapse":
        image = _band_shift(image, frame_number, 12, 7)
        split = _rgb_split(image, 4 + frame_number % 3)
        image = Image.blend(image, split, 0.45)
    elif finish == "analogdecay":
        image = ImageEnhance.Color(image).enhance(0.62)
        image = ImageEnhance.Contrast(image).enhance(0.92)
        image = _band_shift(image, frame_number, 4, 8)
        faded = Image.new("RGB", image.size, (184, 161, 128))
        image = Image.blend(image, faded, 0.08)
        image = _scratches(image, frame_number, 5)
    elif finish == "liminal":
        image = ImageEnhance.Color(image).enhance(0.50)
        image = ImageEnhance.Brightness(image).enhance(1.08)
        image = image.filter(ImageFilter.GaussianBlur(0.9))
        fluorescent = Image.new("RGB", image.size, (198, 205, 176))
        image = Image.blend(image, fluorescent, 0.06)
    elif finish == "relic":
        image = _mono_tint(image, (48, 28, 19), (226, 194, 118), 1.08)
        image = ImageEnhance.Contrast(image).enhance(1.08)
    elif finish == "brutalist":
        gray = ImageOps.autocontrast(image.convert("L"), cutoff=1)
        gray = ImageOps.posterize(gray, 2)
        gray = ImageEnhance.Contrast(gray).enhance(1.48)
        image = Image.merge("RGB", (gray, gray, gray))
    elif finish == "rupture":
        image = _band_shift(image, frame_number, 16, 8)
        image = _rgb_split(image, 6 + frame_number % 4)
        image = ImageEnhance.Contrast(image).enhance(1.12)

    elif finish == "luxury":
        image = ImageEnhance.Contrast(image).enhance(1.08)
        image = ImageEnhance.Sharpness(image).enhance(1.20)
        image = ImageEnhance.Color(image).enhance(0.94)
    elif finish == "catalog":
        image = ImageEnhance.Brightness(image).enhance(1.035)
        image = ImageEnhance.Contrast(image).enhance(0.98)
        image = ImageEnhance.Sharpness(image).enhance(1.08)
    elif finish == "hype":
        image = ImageEnhance.Color(image).enhance(1.38)
        image = ImageEnhance.Contrast(image).enhance(1.16)
        image = ImageEnhance.Sharpness(image).enhance(1.12)
    elif finish == "infomercial":
        image = ImageEnhance.Brightness(image).enhance(1.10)
        image = ImageEnhance.Color(image).enhance(1.28)
        image = ImageEnhance.Contrast(image).enhance(1.08)
        image = _scanlines(image, frame_number, 5, 12)
    elif finish == "herotech":
        image = ImageEnhance.Contrast(image).enhance(1.10)
        image = ImageEnhance.Sharpness(image).enhance(1.24)
        cool = Image.new("RGB", image.size, (110, 146, 176))
        image = Image.blend(image, cool, 0.045)
    elif finish == "ecommerce":
        image = ImageEnhance.Brightness(image).enhance(1.04)
        image = ImageEnhance.Color(image).enhance(0.98)
        image = ImageEnhance.Sharpness(image).enhance(1.08)

    image.save(path, format="PNG", optimize=False)


def register_artistic_expansion() -> None:
    global _REGISTERED
    styles.STYLE_PACKS.update(ARTISTIC_STYLE_PACKS)
    styles.PUBLIC_STYLE_PRESETS.update({name: pack.public_preset() for name, pack in ARTISTIC_STYLE_PACKS.items()})
    if not _REGISTERED:
        styles.apply_style_finish = _apply_artistic_finish
        _REGISTERED = True


class ArtisticExpansionMixin:
    """Register v1.8 styles and expose a category-oriented library browser."""

    def _build_ui(self):
        register_artistic_expansion()
        self.art_family_var = tk.StringVar(value="All styles")
        self.art_style_var = tk.StringVar(value="Watercolor Wash")
        self.art_style_info_var = tk.StringVar(value="")
        super()._build_ui()

    def _build_style_card(self):
        super()._build_style_card()
        card = self._panel(self.left, "3B · Artistic library · v1.8")
        card.pack(fill="x", pady=(0, 8))

        row = ttk.Frame(card, style="Panel.TFrame")
        row.pack(fill="x")
        ttk.Label(row, text="Family", width=12, style="Panel.TLabel").pack(side="left")
        families = ["All styles", "Core", "Fine Art", "Cinema & Genre", "Print & Poster", "Experimental", "Commercial", "Diagnostic"]
        family_combo = ttk.Combobox(row, textvariable=self.art_family_var, values=families, state="readonly", width=20)
        family_combo.pack(side="left", padx=5)
        family_combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh_artistic_library())

        ttk.Label(row, text="Style", style="Panel.TLabel").pack(side="left", padx=(12, 3))
        self.art_style_combo = ttk.Combobox(row, textvariable=self.art_style_var, state="readonly", width=30)
        self.art_style_combo.pack(side="left", fill="x", expand=True, padx=5)
        self.art_style_combo.bind("<<ComboboxSelected>>", lambda _event: self._update_artistic_info())
        ttk.Button(row, text="Apply style", command=self._apply_artistic_selection).pack(side="left", padx=(5, 0))

        ttk.Label(card, textvariable=self.art_style_info_var, style="Muted.TLabel", wraplength=760).pack(anchor="w", pady=(6, 0))
        self._refresh_artistic_library()

    def _styles_for_family(self, family: str) -> list[str]:
        names = list(styles.STYLE_PACKS.keys())
        if family == "All styles":
            return names
        return [name for name in names if STYLE_CATEGORIES.get(name, "Core") == family]

    def _refresh_artistic_library(self):
        values = self._styles_for_family(self.art_family_var.get())
        self.art_style_combo["values"] = values
        if self.art_style_var.get() not in values and values:
            self.art_style_var.set(values[0])
        self._update_artistic_info()

    def _update_artistic_info(self):
        name = self.art_style_var.get()
        pack = styles.STYLE_PACKS.get(name)
        if not pack:
            self.art_style_info_var.set("")
            return
        category = STYLE_CATEGORIES.get(name, "Core")
        stability = STYLE_STABILITY.get(name, "Medium")
        self.art_style_info_var.set(
            f"{category} · continuity {stability} · CN {pack.control_weight:.2f} · temporal {pack.temporal_strength:.2f} · {pack.description}"
        )

    def _apply_artistic_selection(self):
        name = self.art_style_var.get()
        if name not in styles.STYLE_PACKS:
            return
        self.preset_var.set(name)
        self._apply_preset()

    def _apply_preset(self):
        result = super()._apply_preset()
        name = self.preset_var.get()
        if hasattr(self, "art_style_var") and name in styles.STYLE_PACKS:
            self.art_style_var.set(name)
            if hasattr(self, "art_family_var"):
                self.art_family_var.set(STYLE_CATEGORIES.get(name, "Core"))
            if hasattr(self, "art_style_combo"):
                self._refresh_artistic_library()
        return result

    def _render_profile(self) -> dict:
        profile = super()._render_profile()
        name = self.preset_var.get()
        profile["app_version"] = "1.8"
        profile["artistic_expansion"] = {
            "category": STYLE_CATEGORIES.get(name, "Core"),
            "continuity": STYLE_STABILITY.get(name, "Medium"),
            "bundle_version": "1.8",
        }
        return profile
