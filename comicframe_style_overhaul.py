#!/usr/bin/env python3
"""ComicFrame Studio v3.4 — aggressive styles by default.

Product contract:
    Video -> Style -> [ControlNet] [Steps] -> Process

There is no public aggression control. Choosing a ComicFrame style means choosing
an authored, materially transformative render policy. This module retunes every
registered public style, adds a larger experimental library, and keeps only the
structural ControlNet toggle plus sampling-step budget visible.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

import tkinter as tk

import comicframe_artistic as artistic
import comicframe_simple as simple
import comicframe_styles as styles
from comicframe_aggro import (
    DEFAULT_STEPS,
    MAX_STEPS,
    MIN_STEPS,
    ComicFrameStudioApp as AggroApp,
)
from comicframe_styles import StylePack

STYLE_POLICY_VERSION = "3.4"

PUBLIC_TRANSFORM_SUFFIX = (
    ", decisive authored reinterpretation of the source frame, replace photographic surface texture with the selected medium, "
    "strong graphic simplification and material transformation, bold lighting and palette decisions, visibly redrawn environment, "
    "preserve recognizable subject identity, main action, camera direction and broad composition without slavishly copying every source edge"
)


def _neg(extra: str) -> str:
    base = (
        "extra limbs, extra fingers, missing fingers, duplicate person, unreadable face, changed identity, "
        "random text, random lettering, fake logos, accidental watermark"
    )
    return f"{base}, {extra}" if extra else base


def _pack(
    *, denoise: float, cfg: float, fx: float, prompt: str, negative: str,
    control_weight: float, guidance_end: float, temporal_strength: float,
    finish: str, description: str, steps: int = 28,
    fx_ink: bool = True, fx_posterize: bool = True, fx_halftone: bool = True,
    fx_misregister: bool = True, fx_grain: bool = True,
) -> StylePack:
    return StylePack(
        denoise=denoise,
        steps=steps,
        cfg=cfg,
        fx=fx,
        prompt=prompt,
        negative=negative,
        control_weight=control_weight,
        guidance_end=guidance_end,
        temporal_strength=temporal_strength,
        temporal_motion=0.055,
        temporal_cut=0.22,
        fx_ink=fx_ink,
        fx_posterize=fx_posterize,
        fx_halftone=fx_halftone,
        fx_misregister=fx_misregister,
        fx_grain=fx_grain,
        finish=finish,
        description=description,
    )


NEW_STYLE_PACKS: dict[str, tuple[StylePack, str, str]] = {
    # Print / photocopy violence
    "Toxic Xerox": (_pack(
        denoise=.68, cfg=6.3, fx=.98, control_weight=.48, guidance_end=.56, temporal_strength=.16,
        prompt="toxic photocopied punk frame, blown-out toner blacks, acid green contamination, ripped paper edges, smeared duplicated contours, hostile DIY print artifact",
        negative=_neg("clean gradients, polite commercial layout, soft photographic realism"),
        finish="flyer", description="Acid-poisoned xerox brutality with crushed toner and ripped-copy energy."), "Print & Poster", "Experimental"),
    "Punk Flyer": (_pack(
        denoise=.66, cfg=6.4, fx=.99, control_weight=.50, guidance_end=.58, temporal_strength=.17,
        prompt="violent underground punk flyer illustration, marker-black anatomy, photocopy overexposure, ripped collage pressure, stapled-zine ugliness without generated text",
        negative=_neg("clean vector branding, legible generated typography, pastel softness"),
        finish="flyer", description="Raw photocopy flyer aggression with marker-black silhouettes."), "Print & Poster", "Experimental"),
    "Newsprint Panic": (_pack(
        denoise=.64, cfg=6.1, fx=.96, control_weight=.54, guidance_end=.60, temporal_strength=.18,
        prompt="tabloid newsprint panic frame, coarse newspaper dots, ink starvation, hard black editorial shadows, emergency-red spot color, cheap press misregistration",
        negative=_neg("glossy magazine finish, clean photo reproduction, smooth gradients"),
        finish="riso", description="Coarse newspaper panic with spot-color emergency energy."), "Print & Poster", "Experimental"),
    "Bootleg Anime Print": (_pack(
        denoise=.65, cfg=6.2, fx=.94, control_weight=.55, guidance_end=.62, temporal_strength=.18,
        prompt="bootleg anime VHS-to-print frame, hard cel silhouettes, screaming speed-line accents around real motion, cheap offset color, rough screentone, counterfeit fan-zine texture without text",
        negative=_neg("photoreal skin, polished studio anime still, clean vector gradients"),
        finish="screenprint", description="Cheap bootleg cel-print energy with rough screentone and offset color."), "Print & Poster", "Experimental"),
    "Photocopier Riot": (_pack(
        denoise=.70, cfg=6.4, fx=1.0, control_weight=.44, guidance_end=.52, temporal_strength=.14,
        prompt="photocopier riot frame, repeated-generation xerox decay, black toner avalanches, blown highlights, contour doubling, torn registration, anarchic copy-machine abstraction",
        negative=_neg("clean tonal range, restrained composition, realistic photo texture"),
        finish="flyer", description="Repeated-copy degradation pushed into graphic riot territory."), "Experimental", "Experimental"),
    "Tabloid Apocalypse": (_pack(
        denoise=.69, cfg=6.4, fx=.99, control_weight=.46, guidance_end=.54, temporal_strength=.15,
        prompt="apocalyptic supermarket tabloid illustration, lurid red yellow black ink, sensational painted shadows, cheap paper dots, catastrophic visual hierarchy without generated headlines",
        negative=_neg("subtle art direction, muted palette, generated text"),
        finish="pulpcover", description="Lurid tabloid catastrophe without fake headlines."), "Print & Poster", "Experimental"),
    "Stencil Riot": (_pack(
        denoise=.63, cfg=6.1, fx=.95, control_weight=.58, guidance_end=.64, temporal_strength=.19,
        prompt="street stencil riot frame, hard cut-paper silhouettes, overspray halos, limited black red cream palette, repeated spray-pass registration, confrontational poster scale",
        negative=_neg("soft painterly edges, glossy realism, delicate gradients"),
        finish="screenprint", description="Hard stencil silhouettes and overspray translated into moving poster art."), "Print & Poster", "Medium"),
    "Street Poster Melt": (_pack(
        denoise=.70, cfg=6.3, fx=1.0, control_weight=.45, guidance_end=.54, temporal_strength=.14,
        prompt="street poster wall melting into layered print fragments, torn wheatpaste layers, saturated ink ghosts, ripped silhouettes, offset color slabs, urban graphic collapse",
        negative=_neg("clean untouched walls, precise photographic texture, restrained color"),
        finish="riso", description="Layered wheatpaste and torn-poster collapse with moving print ghosts."), "Experimental", "Experimental"),

    # Electronic / surreal failure
    "Chrome Nightmare": (_pack(
        denoise=.71, cfg=6.3, fx=.97, control_weight=.42, guidance_end=.52, temporal_strength=.13,
        prompt="chrome nightmare illustration, liquid reflective black metal, impossible mirrored edges, neon contamination, cybernetic glare, hostile metallic dream geometry around a recognizable subject",
        negative=_neg("flat matte realism, beige palette, clean product render"),
        finish="cyberpunk", description="Liquid black-chrome hallucination with neon contamination."), "Experimental", "Experimental"),
    "Blackout Gospel": (_pack(
        denoise=.67, cfg=6.2, fx=.96, control_weight=.48, guidance_end=.56, temporal_strength=.15,
        prompt="blackout gospel graphic frame, enormous crushed black masses, blown white revelation, violent red accents, solemn icon-like staging, distressed print pressure without generated religious text",
        negative=_neg("gray low contrast, cheerful commercial light, generated scripture"),
        finish="brutalist", description="Crushed-black revelation imagery with brutal red-white graphic weight."), "Experimental", "Experimental"),
    "Acid Cathedral": (_pack(
        denoise=.72, cfg=6.4, fx=1.0, control_weight=.40, guidance_end=.50, temporal_strength=.12,
        prompt="acid cathedral hallucination frame, fluorescent stained-glass color exploding through real architecture, sacred-scale light shafts, chromatic contour echoes, psychedelic structural mutation",
        negative=_neg("neutral white balance, flat office lighting, random text"),
        finish="relic", description="Fluorescent stained-glass hallucination built from the actual scene."), "Experimental", "Experimental"),
    "Synthetic Fever": (_pack(
        denoise=.70, cfg=6.3, fx=.99, control_weight=.42, guidance_end=.52, temporal_strength=.13,
        prompt="synthetic fever animation frame, plastic neon flesh-lighting, thermal gradients, cyberdelic color contamination, hard synthetic shadows, feverish digital material replacement",
        negative=_neg("naturalistic color, documentary realism, subtle grading"),
        finish="infomercial", description="Overheated synthetic color and plastic-light fever dream."), "Experimental", "Experimental"),
    "Neon Ruin": (_pack(
        denoise=.69, cfg=6.3, fx=.98, control_weight=.46, guidance_end=.54, temporal_strength=.14,
        prompt="neon ruin graphic frame, corroded architecture under toxic cyan magenta orange light, scorched poster textures, electrical edge bloom, decayed future-city material language",
        negative=_neg("clean corporate cyberpunk, pristine surfaces, weak saturation"),
        finish="cyberpunk", description="Corroded neon future-ruin treatment with toxic edge color."), "Experimental", "Experimental"),
    "Dead Channel": (_pack(
        denoise=.71, cfg=6.2, fx=1.0, control_weight=.40, guidance_end=.50, temporal_strength=.11,
        prompt="dead television channel frame, violent horizontal signal loss, ghosted bodies, black dropout bands, phosphor smears, unstable electronic image collapse with recognizable central action",
        negative=_neg("clean digital capture, stable signal, pristine broadcast"),
        finish="rupture", description="Hard signal death: dropout bands, ghosts and electronic collapse."), "Experimental", "Experimental"),
    "Memory Burn": (_pack(
        denoise=.68, cfg=6.0, fx=.94, control_weight=.48, guidance_end=.56, temporal_strength=.15,
        prompt="burned memory illustration, overexposed personal-video ghosts, color chemistry scars, doubled silhouettes, faded emulsion, unstable remembered-space atmosphere",
        negative=_neg("clean archival restoration, neutral exposure, pristine image"),
        finish="analogdecay", description="Personal-video memory burned into unstable color and ghosted emulsion."), "Experimental", "Experimental"),
    "Paranoid Broadcast": (_pack(
        denoise=.66, cfg=6.2, fx=.96, control_weight=.50, guidance_end=.58, temporal_strength=.16,
        prompt="paranoid late-night broadcast illustration, surveillance-green contamination, emergency red spill, unstable CRT geometry, oppressive monitoring atmosphere, hard documentary silhouettes without fake HUD text",
        negative=_neg("generated timestamps, generated labels, clean studio television"),
        finish="surveillance", description="Surveillance broadcast paranoia without fake interface text."), "Cinema & Genre", "Experimental"),

    # Painterly but still hard
    "Heavy Gouache": (_pack(
        denoise=.64, cfg=5.8, fx=.78, control_weight=.60, guidance_end=.66, temporal_strength=.21,
        prompt="heavy gouache animation frame, opaque slabs of hand-painted pigment, aggressive dry-brush edges, simplified anatomy, thick matte color masses, authored illustration rather than photo texture",
        negative=_neg("thin transparent wash, photographic pores, clean digital gradients"),
        finish="gouache", description="Thick opaque gouache with much harder shape simplification."), "Fine Art", "Medium"),
    "Ink Brutalism": (_pack(
        denoise=.66, cfg=6.0, fx=.92, control_weight=.54, guidance_end=.60, temporal_strength=.18,
        prompt="ink brutalism frame, huge black brush masses, knife-sharp white negative space, dry-brush destruction, editorial violence, severe hand-drawn compression of the real scene",
        negative=_neg("soft gray wash, polite line art, photoreal shading"),
        finish="charcoal", description="Massive black ink shapes and destructive dry-brush editorial drawing."), "Fine Art", "Experimental"),
    "Pastel Nightmare": (_pack(
        denoise=.67, cfg=5.8, fx=.84, control_weight=.52, guidance_end=.60, temporal_strength=.17,
        prompt="pastel nightmare frame, chalky candy color pushed into uncanny fluorescent shadows, smeared powder contours, soft-face readability inside hostile dream color",
        negative=_neg("clean cheerful nursery palette, photoreal surface texture"),
        finish="pastel", description="Chalk-pastel softness weaponized into fluorescent nightmare color."), "Fine Art", "Experimental"),
    "Pulp Oil": (_pack(
        denoise=.65, cfg=6.1, fx=.90, control_weight=.56, guidance_end=.62, temporal_strength=.18,
        prompt="lurid pulp oil-paint frame, thick painted figures, sensational red-orange lighting, cheap paperback drama, brush-loaded shadows, exaggerated illustrated material while preserving core action",
        negative=_neg("minimal catalog look, flat cel shading, subtle neutral color"),
        finish="pulpcover", description="Thick painted pulp sensationalism with loaded color and shadows."), "Fine Art", "Experimental"),
    "Storybook Ruin": (_pack(
        denoise=.63, cfg=5.7, fx=.82, control_weight=.60, guidance_end=.66, temporal_strength=.20,
        prompt="ruined storybook illustration, hand-painted gouache shapes under ominous color, scratched paper, warped cheerful palette, tactile children's-book medium turned uncanny",
        negative=_neg("clean vector cartoon, photographic realism, pristine paper"),
        finish="gouache", description="Tactile storybook paint pushed into uncanny damaged illustration."), "Fine Art", "Medium"),
    "Charred Sketch": (_pack(
        denoise=.65, cfg=5.8, fx=.88, control_weight=.56, guidance_end=.62, temporal_strength=.18,
        prompt="charred sketch animation frame, black charcoal scars, rubbed graphite smoke, erased highlights, burned-paper tonal fields, frantic gestural reconstruction of the real scene",
        negative=_neg("clean pencil diagram, full-color glossy render, smooth photo gradients"),
        finish="charcoal", description="Burned charcoal and graphite reconstruction with frantic gestural damage."), "Fine Art", "Experimental"),
}


CURATED_STYLE_ORDER = (
    "Graphic Shock · maximum print",
    "Cyberpunk Print",
    "Toxic Xerox",
    "Punk Flyer",
    "Photocopier Riot",
    "Newsprint Panic",
    "Bootleg Anime Print",
    "Street Poster Melt",
    "Stencil Riot",
    "Dream Collapse",
    "Signal Rupture",
    "Glitch Collapse",
    "Dead Channel",
    "Chrome Nightmare",
    "Acid Cathedral",
    "Synthetic Fever",
    "Neon Ruin",
    "Blackout Gospel",
    "Memory Burn",
    "Paranoid Broadcast",
    "Analog Decay",
    "VHS Horror",
    "Grindhouse Damage",
    "Underground Flyer",
    "Risograph Zine",
    "Screenprint Poster",
    "Manga Motion",
    "Neo-Noir",
    "Retro 70s Print",
    "Pulp Horror",
    "Pulp Cover",
    "Tabloid Apocalypse",
    "Pulp Oil",
    "Album Art",
    "Brutalist Dreamstate",
    "Surveillance State",
    "Dystopian Sci-Fi",
    "Liminal Haze",
    "Relic Iconography",
    "Infomercial Fever Dream",
    "Hype Drop",
    "Propaganda Poster",
    "Heavy Gouache",
    "Ink Brutalism",
    "Pastel Nightmare",
    "Storybook Ruin",
    "Charred Sketch",
    "Watercolor Wash",
    "Gouache Storybook",
    "Oil Impasto",
    "Charcoal Study",
    "Pastel Dream",
    "Ink Wash",
    "Dream-Pop Haze",
    "Arthouse Melancholy",
    "Clean Graphic Novel",
    "Luxury Ad",
    "Hero Tech Promo",
)


def aggressive_baseline(name: str, pack: StylePack, category: str, stability: str) -> StylePack:
    """Retune every public pack toward authored redraw instead of filtered footage."""
    if category == "Diagnostic":
        return pack

    if stability == "Experimental":
        denoise_floor, cn_cap, guidance_cap, fx_floor, temporal_cap = .64, .55, .62, .90, .22
    elif stability == "High":
        denoise_floor, cn_cap, guidance_cap, fx_floor, temporal_cap = .53, .82, .82, .56, .36
    else:
        denoise_floor, cn_cap, guidance_cap, fx_floor, temporal_cap = .59, .70, .72, .76, .29

    prompt = str(pack.prompt or "")
    if PUBLIC_TRANSFORM_SUFFIX.strip() not in prompt:
        prompt += PUBLIC_TRANSFORM_SUFFIX

    return replace(
        pack,
        denoise=max(float(pack.denoise), denoise_floor),
        fx=max(float(pack.fx), fx_floor),
        control_weight=min(float(pack.control_weight), cn_cap),
        guidance_end=min(float(pack.guidance_end), guidance_cap),
        temporal_strength=min(float(pack.temporal_strength), temporal_cap),
        prompt=prompt,
        description=(str(pack.description or "Visual process.").rstrip(".") + " · Aggressive redraw baseline."),
    )


def register_style_overhaul() -> None:
    """Install v3.4 once, after the v1.8 artistic registry is available."""
    artistic.register_artistic_expansion()

    # New packs join the artistic registry so their chosen deterministic finish
    # names use the already-audited artistic finish implementation.
    for name, (pack, category, stability) in NEW_STYLE_PACKS.items():
        artistic.ARTISTIC_STYLE_PACKS[name] = pack
        styles.STYLE_PACKS[name] = pack
        artistic.STYLE_CATEGORIES[name] = category
        artistic.STYLE_STABILITY[name] = stability

    # Retune every current public pack, including the new additions.
    for name, pack in list(styles.STYLE_PACKS.items()):
        category = artistic.STYLE_CATEGORIES.get(name, "Core")
        stability = artistic.STYLE_STABILITY.get(name, "Medium")
        tuned = aggressive_baseline(name, pack, category, stability)
        styles.STYLE_PACKS[name] = tuned
        if name in artistic.ARTISTIC_STYLE_PACKS:
            artistic.ARTISTIC_STYLE_PACKS[name] = tuned
        if hasattr(styles, "PUBLIC_STYLE_PRESETS"):
            styles.PUBLIC_STYLE_PRESETS[name] = tuned.public_preset()

    # The simple product browser is curated, not an accidental dump of engine
    # diagnostics. Keep sequence processes first; all style rows follow this order.
    simple.STYLE_PROCESS_ORDER = tuple(name for name in CURATED_STYLE_ORDER if name in styles.STYLE_PACKS)


register_style_overhaul()


class ComicFrameStudioApp(AggroApp):
    """v3.3 engine policy with aggression permanently baked into style selection."""

    def __init__(self):
        super().__init__()
        self.title("ComicFrame Studio 3.4 · Aggressive Styles")

    def _install_simple_shell(self) -> None:
        super()._install_simple_shell()

        # Aggro remains an internal always-on compatibility variable for v3.3's
        # render-policy code, but is no longer an operator control.
        self.simple_aggro_var.set(True)
        try:
            self.simple_aggro_toggle.grid_remove()
        except Exception:
            pass

        # Reclaim the removed control's space so the tiny surface is literally
        # ControlNet + Steps beneath the style browser.
        try:
            for child in self.simple_creative_controls.winfo_children():
                if child not in {self.simple_controlnet_toggle, self.simple_aggro_toggle}:
                    child.grid_configure(column=1, sticky="ew")
            self.simple_creative_controls.grid_columnconfigure(1, weight=1)
            self.simple_creative_controls.grid_columnconfigure(2, weight=0)
        except Exception:
            pass
        self._creative_control_changed()

    def _creative_control_changed(self) -> None:
        if not hasattr(self, "simple_creative_hint"):
            return
        enabled = bool(getattr(self, "simple_controlnet_var", None).get())
        if enabled:
            text = "ControlNet keeps a loose structural rail · styles redraw hard by default · fewer steps render faster"
        else:
            text = "UNLEASHED · no ControlNet structure rail · styles redraw hard by default"
        self.simple_creative_hint.configure(text=text)

    def _render_profile(self) -> dict[str, Any]:
        profile = super()._render_profile()
        creative = profile.setdefault("creative_controls", {})
        if isinstance(creative, dict):
            creative.pop("aggro", None)
            creative["version"] = STYLE_POLICY_VERSION
            creative["style_policy"] = "aggressive-by-default"
            creative["style_library"] = len(simple.simple_process_catalog())
        return profile


def main():
    ComicFrameStudioApp().mainloop()


if __name__ == "__main__":
    main()
