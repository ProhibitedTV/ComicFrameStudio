#!/usr/bin/env python3
"""ComicFrame public style library and aggressive redraw policy.

This module owns style registration only. It deliberately contains no Tk UI and
no application subclass. The stable product shell lives in comicframe_product.py.
"""
from __future__ import annotations

from dataclasses import replace
from typing import NamedTuple

import comicframe_artistic as artistic
import comicframe_simple as simple
import comicframe_styles as styles
from comicframe_styles import StylePack

STYLE_LIBRARY_VERSION = "3.5"
PUBLIC_TRANSFORM_SUFFIX = (
    ", decisive authored reinterpretation of the source frame, replace photographic surface texture with the selected medium, "
    "strong graphic simplification and material transformation, bold lighting and palette decisions, visibly redrawn environment, "
    "preserve recognizable subject identity, main action, camera direction and broad composition without slavishly copying every source edge"
)


class StyleSpec(NamedTuple):
    prompt: str
    negative: str
    finish: str
    description: str
    category: str = "Experimental"
    stability: str = "Experimental"
    denoise: float = 0.68
    cfg: float = 6.2
    fx: float = 0.96
    control_weight: float = 0.48
    guidance_end: float = 0.56
    temporal_strength: float = 0.16


def _negative(extra: str = "") -> str:
    base = (
        "extra limbs, extra fingers, missing fingers, duplicate person, unreadable face, changed identity, "
        "random text, random lettering, fake logos, accidental watermark"
    )
    return f"{base}, {extra}" if extra else base


def _pack(spec: StyleSpec) -> StylePack:
    return StylePack(
        denoise=spec.denoise,
        steps=28,
        cfg=spec.cfg,
        fx=spec.fx,
        prompt=spec.prompt,
        negative=_negative(spec.negative),
        control_weight=spec.control_weight,
        guidance_end=spec.guidance_end,
        temporal_strength=spec.temporal_strength,
        temporal_motion=0.055,
        temporal_cut=0.22,
        fx_ink=True,
        fx_posterize=True,
        fx_halftone=True,
        fx_misregister=True,
        fx_grain=True,
        finish=spec.finish,
        description=spec.description,
    )


NEW_STYLE_SPECS: dict[str, StyleSpec] = {
    "Toxic Xerox": StyleSpec(
        "toxic photocopied punk frame, blown-out toner blacks, acid contamination, ripped paper edges, smeared duplicated contours, hostile DIY print artifact",
        "clean gradients, polite commercial layout, soft photographic realism",
        "flyer", "Acid-poisoned xerox brutality with crushed toner and ripped-copy energy.", "Print & Poster",
        denoise=.68, cfg=6.3, fx=.98, control_weight=.48, guidance_end=.56, temporal_strength=.16,
    ),
    "Punk Flyer": StyleSpec(
        "violent underground punk flyer illustration, marker-black anatomy, photocopy overexposure, ripped collage pressure, stapled-zine ugliness without generated text",
        "clean vector branding, legible generated typography, pastel softness",
        "flyer", "Raw photocopy flyer aggression with marker-black silhouettes.", "Print & Poster",
        denoise=.66, cfg=6.4, fx=.99, control_weight=.50, guidance_end=.58, temporal_strength=.17,
    ),
    "Newsprint Panic": StyleSpec(
        "tabloid newsprint panic frame, coarse newspaper dots, ink starvation, hard black editorial shadows, emergency-red spot color, cheap press misregistration",
        "glossy magazine finish, clean photo reproduction, smooth gradients",
        "riso", "Coarse newspaper panic with spot-color emergency energy.", "Print & Poster",
        denoise=.64, cfg=6.1, fx=.96, control_weight=.54, guidance_end=.60, temporal_strength=.18,
    ),
    "Bootleg Anime Print": StyleSpec(
        "bootleg anime VHS-to-print frame, hard cel silhouettes, screaming speed-line accents around real motion, cheap offset color, rough screentone, counterfeit fan-zine texture without text",
        "photoreal skin, polished studio anime still, clean vector gradients",
        "screenprint", "Cheap bootleg cel-print energy with rough screentone and offset color.", "Print & Poster",
        denoise=.65, cfg=6.2, fx=.94, control_weight=.55, guidance_end=.62, temporal_strength=.18,
    ),
    "Photocopier Riot": StyleSpec(
        "photocopier riot frame, repeated-generation xerox decay, black toner avalanches, blown highlights, contour doubling, torn registration, anarchic copy-machine abstraction",
        "clean tonal range, restrained composition, realistic photo texture",
        "flyer", "Repeated-copy degradation pushed into graphic riot territory.",
        denoise=.70, cfg=6.4, fx=1.0, control_weight=.44, guidance_end=.52, temporal_strength=.14,
    ),
    "Tabloid Apocalypse": StyleSpec(
        "apocalyptic supermarket tabloid illustration, lurid red yellow black ink, sensational painted shadows, cheap paper dots, catastrophic visual hierarchy without generated headlines",
        "subtle art direction, muted palette, generated text",
        "pulpcover", "Lurid tabloid catastrophe without fake headlines.", "Print & Poster",
        denoise=.69, cfg=6.4, fx=.99, control_weight=.46, guidance_end=.54, temporal_strength=.15,
    ),
    "Stencil Riot": StyleSpec(
        "street stencil riot frame, hard cut-paper silhouettes, overspray halos, limited black red cream palette, repeated spray-pass registration, confrontational poster scale",
        "soft painterly edges, glossy realism, delicate gradients",
        "screenprint", "Hard stencil silhouettes and overspray translated into moving poster art.", "Print & Poster", "Medium",
        denoise=.63, cfg=6.1, fx=.95, control_weight=.58, guidance_end=.64, temporal_strength=.19,
    ),
    "Street Poster Melt": StyleSpec(
        "street poster wall melting into layered print fragments, torn wheatpaste layers, saturated ink ghosts, ripped silhouettes, offset color slabs, urban graphic collapse",
        "clean untouched walls, precise photographic texture, restrained color",
        "riso", "Layered wheatpaste and torn-poster collapse with moving print ghosts.",
        denoise=.70, cfg=6.3, fx=1.0, control_weight=.45, guidance_end=.54, temporal_strength=.14,
    ),
    "Chrome Nightmare": StyleSpec(
        "chrome nightmare illustration, liquid reflective black metal, impossible mirrored edges, neon contamination, cybernetic glare, hostile metallic dream geometry around a recognizable subject",
        "flat matte realism, beige palette, clean product render",
        "albumart", "Liquid black-chrome hallucination with neon contamination.",
        denoise=.71, cfg=6.3, fx=.97, control_weight=.42, guidance_end=.52, temporal_strength=.13,
    ),
    "Blackout Gospel": StyleSpec(
        "blackout gospel graphic frame, enormous crushed black masses, blown white revelation, violent red accents, solemn icon-like staging, distressed print pressure without generated religious text",
        "gray low contrast, cheerful commercial light, generated scripture",
        "brutalist", "Crushed-black revelation imagery with brutal red-white graphic weight.",
        denoise=.67, cfg=6.2, fx=.96, control_weight=.48, guidance_end=.56, temporal_strength=.15,
    ),
    "Acid Cathedral": StyleSpec(
        "acid cathedral hallucination frame, fluorescent stained-glass color exploding through real architecture, sacred-scale light shafts, chromatic contour echoes, psychedelic structural mutation",
        "neutral white balance, flat office lighting, random text",
        "relic", "Fluorescent stained-glass hallucination built from the actual scene.",
        denoise=.72, cfg=6.4, fx=1.0, control_weight=.40, guidance_end=.50, temporal_strength=.12,
    ),
    "Synthetic Fever": StyleSpec(
        "synthetic fever animation frame, plastic neon flesh-lighting, thermal gradients, cyberdelic color contamination, hard synthetic shadows, feverish digital material replacement",
        "naturalistic color, documentary realism, subtle grading",
        "infomercial", "Overheated synthetic color and plastic-light fever dream.",
        denoise=.70, cfg=6.3, fx=.99, control_weight=.42, guidance_end=.52, temporal_strength=.13,
    ),
    "Neon Ruin": StyleSpec(
        "neon ruin graphic frame, corroded architecture under toxic cyan magenta orange light, scorched poster textures, electrical edge bloom, decayed future-city material language",
        "clean corporate cyberpunk, pristine surfaces, weak saturation",
        "glitchcollapse", "Corroded neon future-ruin treatment with toxic edge color.",
        denoise=.69, cfg=6.3, fx=.98, control_weight=.46, guidance_end=.54, temporal_strength=.14,
    ),
    "Dead Channel": StyleSpec(
        "dead television channel frame, violent horizontal signal loss, ghosted bodies, black dropout bands, phosphor smears, unstable electronic image collapse with recognizable central action",
        "clean digital capture, stable signal, pristine broadcast",
        "rupture", "Hard signal death: dropout bands, ghosts and electronic collapse.",
        denoise=.71, cfg=6.2, fx=1.0, control_weight=.40, guidance_end=.50, temporal_strength=.11,
    ),
    "Memory Burn": StyleSpec(
        "burned memory illustration, overexposed personal-video ghosts, color chemistry scars, doubled silhouettes, faded emulsion, unstable remembered-space atmosphere",
        "clean archival restoration, neutral exposure, pristine image",
        "analogdecay", "Personal-video memory burned into unstable color and ghosted emulsion.",
        denoise=.68, cfg=6.0, fx=.94, control_weight=.48, guidance_end=.56, temporal_strength=.15,
    ),
    "Paranoid Broadcast": StyleSpec(
        "paranoid late-night broadcast illustration, surveillance-green contamination, emergency red spill, unstable CRT geometry, oppressive monitoring atmosphere, hard documentary silhouettes without fake HUD text",
        "generated timestamps, generated labels, clean studio television",
        "surveillance", "Surveillance broadcast paranoia without fake interface text.", "Cinema & Genre",
        denoise=.66, cfg=6.2, fx=.96, control_weight=.50, guidance_end=.58, temporal_strength=.16,
    ),
    "Heavy Gouache": StyleSpec(
        "heavy gouache animation frame, opaque slabs of hand-painted pigment, aggressive dry-brush edges, simplified anatomy, thick matte color masses, authored illustration rather than photo texture",
        "thin transparent wash, photographic pores, clean digital gradients",
        "gouache", "Thick opaque gouache with much harder shape simplification.", "Fine Art", "Medium",
        denoise=.64, cfg=5.8, fx=.78, control_weight=.60, guidance_end=.66, temporal_strength=.21,
    ),
    "Ink Brutalism": StyleSpec(
        "ink brutalism frame, huge black brush masses, knife-sharp white negative space, dry-brush destruction, editorial violence, severe hand-drawn compression of the real scene",
        "soft gray wash, polite line art, photoreal shading",
        "charcoal", "Massive black ink shapes and destructive dry-brush editorial drawing.", "Fine Art",
        denoise=.66, cfg=6.0, fx=.92, control_weight=.54, guidance_end=.60, temporal_strength=.18,
    ),
    "Pastel Nightmare": StyleSpec(
        "pastel nightmare frame, chalky candy color pushed into uncanny fluorescent shadows, smeared powder contours, soft-face readability inside hostile dream color",
        "clean cheerful nursery palette, photoreal surface texture",
        "pastel", "Chalk-pastel softness weaponized into fluorescent nightmare color.", "Fine Art",
        denoise=.67, cfg=5.8, fx=.84, control_weight=.52, guidance_end=.60, temporal_strength=.17,
    ),
    "Pulp Oil": StyleSpec(
        "lurid pulp oil-paint frame, thick painted figures, sensational red-orange lighting, cheap paperback drama, brush-loaded shadows, exaggerated illustrated material while preserving core action",
        "minimal catalog look, flat cel shading, subtle neutral color",
        "pulpcover", "Thick painted pulp sensationalism with loaded color and shadows.", "Fine Art",
        denoise=.65, cfg=6.1, fx=.90, control_weight=.56, guidance_end=.62, temporal_strength=.18,
    ),
    "Storybook Ruin": StyleSpec(
        "ruined storybook illustration, hand-painted gouache shapes under ominous color, scratched paper, warped cheerful palette, tactile children's-book medium turned uncanny",
        "clean vector cartoon, photographic realism, pristine paper",
        "gouache", "Tactile storybook paint pushed into uncanny damaged illustration.", "Fine Art", "Medium",
        denoise=.63, cfg=5.7, fx=.82, control_weight=.60, guidance_end=.66, temporal_strength=.20,
    ),
    "Charred Sketch": StyleSpec(
        "charred sketch animation frame, black charcoal scars, rubbed graphite smoke, erased highlights, burned-paper tonal fields, frantic gestural reconstruction of the real scene",
        "clean pencil diagram, full-color glossy render, smooth photo gradients",
        "charcoal", "Burned charcoal and graphite reconstruction with frantic gestural damage.", "Fine Art",
        denoise=.65, cfg=5.8, fx=.88, control_weight=.56, guidance_end=.62, temporal_strength=.18,
    ),
}


CURATED_STYLE_ORDER = (
    "Graphic Shock · maximum print", "Cyberpunk Print",
    "Toxic Xerox", "Punk Flyer", "Photocopier Riot", "Newsprint Panic", "Bootleg Anime Print",
    "Street Poster Melt", "Stencil Riot", "Dream Collapse", "Signal Rupture", "Glitch Collapse",
    "Dead Channel", "Chrome Nightmare", "Acid Cathedral", "Synthetic Fever", "Neon Ruin",
    "Blackout Gospel", "Memory Burn", "Paranoid Broadcast", "Analog Decay", "VHS Horror",
    "Grindhouse Damage", "Underground Flyer", "Risograph Zine", "Screenprint Poster", "Manga Motion",
    "Neo-Noir", "Retro 70s Print", "Pulp Horror", "Pulp Cover", "Tabloid Apocalypse", "Pulp Oil",
    "Album Art", "Brutalist Dreamstate", "Surveillance State", "Dystopian Sci-Fi", "Liminal Haze",
    "Relic Iconography", "Infomercial Fever Dream", "Hype Drop", "Propaganda Poster",
    "Heavy Gouache", "Ink Brutalism", "Pastel Nightmare", "Storybook Ruin", "Charred Sketch",
    "Watercolor Wash", "Gouache Storybook", "Oil Impasto", "Charcoal Study", "Pastel Dream",
    "Ink Wash", "Dream-Pop Haze", "Arthouse Melancholy", "Clean Graphic Novel", "Luxury Ad",
    "Hero Tech Promo",
)


def aggressive_baseline(name: str, pack: StylePack, category: str, stability: str) -> StylePack:
    """Retune a public style toward authored redraw instead of filtered footage."""
    if category == "Diagnostic":
        return pack
    if stability == "Experimental":
        denoise_floor, cn_cap, guidance_cap, fx_floor, temporal_cap = .64, .55, .62, .90, .22
    elif stability == "High":
        denoise_floor, cn_cap, guidance_cap, fx_floor, temporal_cap = .53, .82, .82, .56, .36
    else:
        denoise_floor, cn_cap, guidance_cap, fx_floor, temporal_cap = .59, .70, .72, .76, .29

    prompt = str(pack.prompt or "")
    if "decisive authored reinterpretation" not in prompt:
        prompt += PUBLIC_TRANSFORM_SUFFIX
    description = str(pack.description or "Visual process.").rstrip(".")
    if "Aggressive redraw baseline" not in description:
        description += " · Aggressive redraw baseline"

    return replace(
        pack,
        denoise=max(float(pack.denoise), denoise_floor),
        fx=max(float(pack.fx), fx_floor),
        control_weight=min(float(pack.control_weight), cn_cap),
        guidance_end=min(float(pack.guidance_end), guidance_cap),
        temporal_strength=min(float(pack.temporal_strength), temporal_cap),
        prompt=prompt,
        description=description + ".",
    )


_REGISTERED = False


def register_style_library() -> None:
    """Register the public style bundle once and curate the simple browser."""
    global _REGISTERED
    if _REGISTERED:
        return

    artistic.register_artistic_expansion()
    for name, spec in NEW_STYLE_SPECS.items():
        pack = _pack(spec)
        artistic.ARTISTIC_STYLE_PACKS[name] = pack
        styles.STYLE_PACKS[name] = pack
        artistic.STYLE_CATEGORIES[name] = spec.category
        artistic.STYLE_STABILITY[name] = spec.stability

    for name, pack in list(styles.STYLE_PACKS.items()):
        category = artistic.STYLE_CATEGORIES.get(name, "Core")
        stability = artistic.STYLE_STABILITY.get(name, "Medium")
        tuned = aggressive_baseline(name, pack, category, stability)
        styles.STYLE_PACKS[name] = tuned
        if name in artistic.ARTISTIC_STYLE_PACKS:
            artistic.ARTISTIC_STYLE_PACKS[name] = tuned
        if hasattr(styles, "PUBLIC_STYLE_PRESETS"):
            styles.PUBLIC_STYLE_PRESETS[name] = tuned.public_preset()

    simple.STYLE_PROCESS_ORDER = tuple(name for name in CURATED_STYLE_ORDER if name in styles.STYLE_PACKS)
    _REGISTERED = True


register_style_library()
