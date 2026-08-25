#!/usr/bin/env python3
"""Pipeline-aware visual style packs for ComicFrame Studio.

A style pack owns more than prompt text: diffusion strength, sampler budget,
ControlNet pressure, temporal stabilization and deterministic post-processing
choices travel together so switching looks produces a materially different
video pipeline while retaining the source-faithful ControlNet foundation.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps, ImageDraw


COMMON_NEGATIVE = (
    "photorealistic skin pores, soft painterly mush, watercolor wash, blurry, low contrast, weak silhouette, "
    "extra limbs, extra fingers, missing fingers, duplicate person, warped face, changed identity, changed hairstyle, "
    "changed clothes, changed pose, cropped body, different camera angle, changed room layout, duplicated furniture, "
    "missing furniture, invented objects, melted geometry, malformed anatomy, random text, random lettering, logo artifacts"
)


def _negative(extra: str) -> str:
    return f"{COMMON_NEGATIVE}, {extra}" if extra else COMMON_NEGATIVE


@dataclass(frozen=True)
class StylePack:
    denoise: float
    steps: int
    cfg: float
    fx: float
    prompt: str
    negative: str
    control_weight: float = 0.95
    guidance_end: float = 0.92
    temporal_strength: float = 0.35
    temporal_motion: float = 0.08
    temporal_cut: float = 0.22
    fx_ink: bool = True
    fx_posterize: bool = True
    fx_halftone: bool = True
    fx_misregister: bool = True
    fx_grain: bool = True
    finish: str = "none"
    inference: str = "1024 long edge · fast / stable"
    description: str = ""

    def public_preset(self) -> dict:
        return {
            "denoise": self.denoise,
            "steps": self.steps,
            "cfg": self.cfg,
            "fx": self.fx,
            "prompt": self.prompt,
        }


STYLE_PACKS: dict[str, StylePack] = {
    "Video Fidelity · RTX 3060": StylePack(
        denoise=0.40, steps=24, cfg=5.5, fx=0.72,
        prompt=(
            "source-faithful comic animation frame, restyle the photographed frame without redesigning it, "
            "hard inked contour hierarchy, clean cel-shadow shapes, restrained halftone and screen-print texture, "
            "graphic color separation, cinematic contrast, preserve exact identity, expression, pose, hands, clothing, "
            "object count, furniture, architecture, camera position, lens perspective, crop, silhouette and scene geometry, "
            "same shot and same action as the source video frame"
        ),
        negative=_negative("heavy abstraction, background redesign, excessive chromatic distortion"),
        control_weight=0.95, guidance_end=0.92, temporal_strength=0.35,
        fx_misregister=False, finish="clean",
        description="Balanced source-faithful illustrated video; default production preset.",
    ),
    "Graphic Shock · maximum print": StylePack(
        denoise=0.55, steps=30, cfg=6.0, fx=0.90,
        prompt=(
            "extreme mixed-media comic animation frame, hard hand-inked contours, bold posterized shadow masses, "
            "dense Ben-Day dots, crosshatching, dry-brush ink, offset screen-print plates, cyan magenta orange electric-blue "
            "color separation, doubled contour accents, intentionally imperfect print registration, aggressive kinetic frame energy, "
            "preserve the same person, pose, clothing, furniture, architecture, camera position and complete frame"
        ),
        negative=_negative("clean corporate rendering, timid color, weak ink, flat texture"),
        control_weight=0.90, guidance_end=0.88, temporal_strength=0.27,
        finish="shock",
        description="Maximum chaotic print energy while ControlNet still protects shot geometry.",
    ),
    "Comic Punch · strong": StylePack(
        denoise=0.48, steps=28, cfg=6.25, fx=0.78,
        prompt=(
            "strong graphic comic animation frame, aggressive ink contours, bold cel shadow masses, halftone dots, "
            "crosshatching, screen-print texture, posterized color blocks, offset cyan and magenta ink, strong silhouette, "
            "preserve identity, pose, room layout, furniture placement, camera framing and proportions"
        ),
        negative=_negative("washed out colors, painterly brushwork, weak contours"),
        control_weight=0.93, guidance_end=0.90, temporal_strength=0.32,
        finish="punch",
        description="Strong all-purpose comic treatment with moderate print instability.",
    ),
    "Clean Graphic Novel": StylePack(
        denoise=0.40, steps=25, cfg=5.4, fx=0.52,
        prompt=(
            "clean modern graphic novel panel, confident ink contours, controlled cel shading, selective crosshatching, "
            "clear facial features, restrained color palette, elegant cinematic lighting, crisp readable forms, "
            "preserve exact identity, body proportions, pose, hands, product shapes, environment and camera composition"
        ),
        negative=_negative("glitch, chromatic aberration, heavy halftone, dirty print registration, extreme abstraction"),
        control_weight=0.98, guidance_end=0.95, temporal_strength=0.42,
        fx_halftone=False, fx_misregister=False, fx_grain=False, finish="clean",
        description="Stable, restrained illustrated footage for dialogue and product shots.",
    ),
    "Neo-Noir": StylePack(
        denoise=0.43, steps=26, cfg=5.6, fx=0.76,
        prompt=(
            "neo-noir graphic novel frame, deep black shadow masses, razor rim light, stark chiaroscuro, wet-night contrast, "
            "minimal selective color, hard ink contours, cinematic negative space, tense urban atmosphere, "
            "preserve exact identity, pose, architecture, props and camera geometry"
        ),
        negative=_negative("pastel palette, cheerful flat lighting, soft airbrush, low contrast"),
        control_weight=0.96, guidance_end=0.94, temporal_strength=0.38,
        fx_misregister=False, finish="noir",
        description="Near-monochrome high-contrast ink with hard noir lighting.",
    ),
    "Cyberpunk Print": StylePack(
        denoise=0.49, steps=28, cfg=6.0, fx=0.88,
        prompt=(
            "cyberpunk underground print-comic frame, hard black ink, electric cyan magenta violet and acid-orange lighting, "
            "screen-print color separations, dirty halftone, neon edge bloom translated into graphic shapes, interface-era visual noise, "
            "urban night energy, preserve identity, pose, clothing, objects, room geometry and camera framing"
        ),
        negative=_negative("beige neutral palette, clean corporate minimalism, realistic photographic rendering"),
        control_weight=0.92, guidance_end=0.90, temporal_strength=0.30,
        finish="cyberpunk",
        description="Neon CMYK separation, grime and aggressive high-energy print color.",
    ),
    "Pulp Horror": StylePack(
        denoise=0.50, steps=29, cfg=6.1, fx=0.84,
        prompt=(
            "vintage pulp horror comic frame, scratchy black ink, distressed brush contours, sickly dramatic shadows, "
            "aged four-color printing, ominous red accents, coarse paper texture, uneasy perspective energy without changing camera geometry, "
            "preserve the same people, anatomy, pose, props, architecture and complete source composition"
        ),
        negative=_negative("cute cartoon, glossy 3d, bright cheerful commercial lighting, pristine digital vector art"),
        control_weight=0.91, guidance_end=0.89, temporal_strength=0.28,
        finish="horror",
        description="Distressed old horror-comic inks, dirty paper and ominous color grading.",
    ),
    "Retro 70s Print": StylePack(
        denoise=0.45, steps=26, cfg=5.7, fx=0.74,
        prompt=(
            "1970s offset comic print frame, warm faded four-color palette, coarse Ben-Day dots, imperfect ink registration, "
            "cream paper character, confident black outlines, analog editorial illustration, period print texture, "
            "preserve exact subject identity, pose, objects, set layout and camera framing"
        ),
        negative=_negative("modern neon palette, glossy digital gradients, photorealism, pristine vector finish"),
        control_weight=0.95, guidance_end=0.92, temporal_strength=0.34,
        finish="retro70",
        description="Warm faded four-color comic stock with analog registration errors.",
    ),
    "Manga Motion": StylePack(
        denoise=0.44, steps=26, cfg=5.8, fx=0.66,
        prompt=(
            "high-energy black-and-white manga animation frame, decisive black ink contours, screentone shadows, white highlights, "
            "speed-line energy around real motion only, expressive but source-faithful face, clean silhouette readability, "
            "preserve exact identity, anatomy, pose, hands, props, background geometry and camera angle"
        ),
        negative=_negative("full-color painterly image, soft gray mush, western oil painting, altered facial identity"),
        control_weight=0.97, guidance_end=0.94, temporal_strength=0.36,
        fx_misregister=False, fx_grain=False, finish="manga",
        description="Monochrome ink and screentone treatment with strong motion readability.",
    ),
    "Dream Collapse": StylePack(
        denoise=0.56, steps=30, cfg=6.2, fx=0.92,
        prompt=(
            "surreal digital-alienation comic frame, subject remains recognizable and spatially anchored while the environment fractures, "
            "interdimensional print offsets, doubled architecture echoes, chromatic contour displacement, corrupted halftone fields, "
            "impossible graphic texture transitions, escalating background instability, preserve face, body, pose, main action and camera crop"
        ),
        negative=_negative("subject replacement, unrecognizable face, extra people, completely different room, total composition rewrite"),
        control_weight=0.84, guidance_end=0.82, temporal_strength=0.20,
        temporal_motion=0.06, fx_misregister=True, finish="collapse",
        description="Intentional background breakdown and digital alienation with the subject still anchored.",
    ),
    "Corporate Propaganda": StylePack(
        denoise=0.42, steps=25, cfg=5.6, fx=0.58,
        prompt=(
            "heroic corporate propaganda comic poster frame, immaculate bold ink shapes, idealized product lighting, clean geometric color blocks, "
            "confident low-angle advertising energy, monumental composition, polished mid-century-meets-modern campaign illustration, "
            "preserve exact product shape, readable face identity, pose, hands, environment and camera composition"
        ),
        negative=_negative("grunge overload, illegible product shape, warped mug, random branding, dirty chaotic background"),
        control_weight=0.98, guidance_end=0.96, temporal_strength=0.42,
        fx_halftone=False, fx_misregister=False, fx_grain=False, finish="propaganda",
        description="Clean absurdly heroic advertising art; ideal for product-promo comedy.",
    ),
    "Analog Broadcast": StylePack(
        denoise=0.47, steps=27, cfg=5.8, fx=0.78,
        prompt=(
            "late-night analog broadcast comic frame, illustrated public-access television aesthetic, hard ink contours, "
            "CRT color bleed translated into print shapes, imperfect signal registration, scanline rhythm, noisy local-TV atmosphere, "
            "preserve identity, action, props, architecture and exact source camera framing"
        ),
        negative=_negative("ultra-clean 8k digital commercial, sterile modern UI, photorealistic television screenshot"),
        control_weight=0.92, guidance_end=0.90, temporal_strength=0.26,
        fx_halftone=False, finish="broadcast",
        description="Comic rendering crossed with late-night CRT/public-access signal grime.",
    ),
    "Structure First · ControlNet test": StylePack(
        denoise=0.42, steps=26, cfg=5.75, fx=0.62,
        prompt=(
            "graphic inked animation frame, readable contour hierarchy, posterized cel shadow shapes, comic print texture, "
            "controlled color separation, preserve exact scene geometry, pose, identity and camera framing"
        ),
        negative=_negative("geometry drift, pose drift, scene redesign"),
        control_weight=1.05, guidance_end=0.98, temporal_strength=0.40,
        fx_misregister=False, finish="clean",
        description="Diagnostic style prioritizing structural adherence over transformation.",
    ),
    "Diffusion Only · diagnostic": StylePack(
        denoise=0.40, steps=24, cfg=6.0, fx=0.0,
        prompt=(
            "cinematic comic illustration, inked contours, cel shading, graphic lighting, saturated comic color separation, "
            "preserve pose, identity, scene geometry and camera framing"
        ),
        negative=_negative("geometry drift, face drift"),
        control_weight=0.95, guidance_end=0.92, temporal_strength=0.0,
        fx_ink=False, fx_posterize=False, fx_halftone=False, fx_misregister=False, fx_grain=False,
        finish="none",
        description="Raw diffusion diagnostic with deterministic finishing disabled.",
    ),
}


PUBLIC_STYLE_PRESETS = {name: pack.public_preset() for name, pack in STYLE_PACKS.items()}


def _translate(image: Image.Image, dx: int, dy: int) -> Image.Image:
    out = Image.new("RGB", image.size, (0, 0, 0))
    left = max(0, -dx)
    top = max(0, -dy)
    right = min(image.width, image.width - dx) if dx >= 0 else image.width
    bottom = min(image.height, image.height - dy) if dy >= 0 else image.height
    if right > left and bottom > top:
        out.paste(image.crop((left, top, right, bottom)), (max(0, dx), max(0, dy)))
    return out


def apply_style_finish(path: Path, style_name: str, frame_number: int) -> None:
    """Apply deterministic grading unique to selected style after common print FX."""
    pack = STYLE_PACKS.get(style_name)
    if not pack or pack.finish in {"none", "clean"}:
        if pack and pack.finish == "clean":
            with Image.open(path) as src:
                image = ImageEnhance.Sharpness(src.convert("RGB")).enhance(1.08)
            image.save(path, format="PNG", optimize=False)
        return

    with Image.open(path) as src:
        image = src.convert("RGB")

    if pack.finish == "noir":
        gray = ImageOps.autocontrast(image.convert("L"), cutoff=1)
        gray = ImageEnhance.Contrast(gray).enhance(1.32)
        image = Image.merge("RGB", (gray, gray, gray))
    elif pack.finish == "manga":
        gray = ImageOps.autocontrast(image.convert("L"), cutoff=1)
        gray = ImageEnhance.Contrast(gray).enhance(1.45)
        gray = ImageOps.posterize(gray, 4)
        image = Image.merge("RGB", (gray, gray, gray))
    elif pack.finish == "retro70":
        image = ImageEnhance.Color(image).enhance(0.78)
        image = ImageEnhance.Contrast(image).enhance(0.94)
        warm = Image.new("RGB", image.size, (230, 181, 112))
        image = Image.blend(image, warm, 0.08)
    elif pack.finish == "horror":
        image = ImageEnhance.Color(image).enhance(0.70)
        image = ImageEnhance.Contrast(image).enhance(1.18)
        sick = Image.new("RGB", image.size, (82, 44, 31))
        image = Image.blend(image, sick, 0.09)
    elif pack.finish == "cyberpunk":
        image = ImageEnhance.Color(image).enhance(1.32)
        image = ImageEnhance.Contrast(image).enhance(1.12)
    elif pack.finish == "propaganda":
        image = ImageEnhance.Color(image).enhance(1.12)
        image = ImageEnhance.Contrast(image).enhance(1.10)
        image = ImageEnhance.Sharpness(image).enhance(1.18)
    elif pack.finish == "broadcast":
        ghost = _translate(image, 2 + (frame_number % 2), 0)
        image = Image.blend(image, ghost, 0.08)
        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        alpha = 22
        for y in range(frame_number % 3, image.height, 3):
            draw.line((0, y, image.width, y), fill=(0, 0, 0, alpha), width=1)
        image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
    elif pack.finish == "collapse":
        echo = _translate(image, 3 + (frame_number % 3), (frame_number % 3) - 1)
        edges = ImageChops.difference(image, echo)
        edges = ImageEnhance.Contrast(edges).enhance(1.4)
        image = Image.blend(image, ImageChops.screen(image, edges), 0.12)
    elif pack.finish in {"shock", "punch"}:
        image = ImageEnhance.Contrast(image).enhance(1.08 if pack.finish == "punch" else 1.14)
        image = ImageEnhance.Color(image).enhance(1.08 if pack.finish == "punch" else 1.18)

    image.save(path, format="PNG", optimize=False)


class StylePackMixin:
    """Register and apply complete style pipelines without changing the core renderer."""

    def _build_ui(self):
        # Base UI populates the preset combobox from comicframe_app.STYLE_PRESETS,
        # so register all packs immediately before that combobox is built.
        import comicframe_app as app_layer
        app_layer.STYLE_PRESETS.update(PUBLIC_STYLE_PRESETS)
        super()._build_ui()

    @staticmethod
    def _set_var(obj, name: str, value) -> None:
        var = getattr(obj, name, None)
        if var is not None and hasattr(var, "set"):
            var.set(value)

    def _apply_preset(self):
        result = super()._apply_preset()
        name = self.preset_var.get()
        pack = STYLE_PACKS.get(name)
        if not pack:
            return result

        if hasattr(self, "negative_text"):
            self.negative_text.delete("1.0", "end")
            self.negative_text.insert("1.0", pack.negative)

        self._set_var(self, "control_enabled_var", True)
        self._set_var(self, "control_required_var", True)
        self._set_var(self, "control_weight_var", pack.control_weight)
        self._set_var(self, "control_guidance_end_var", pack.guidance_end)
        self._set_var(self, "temporal_enabled_var", pack.temporal_strength > 0)
        self._set_var(self, "temporal_strength_var", pack.temporal_strength)
        self._set_var(self, "temporal_motion_var", pack.temporal_motion)
        self._set_var(self, "temporal_cut_var", pack.temporal_cut)
        self._set_var(self, "fx_ink_var", pack.fx_ink)
        self._set_var(self, "fx_posterize_var", pack.fx_posterize)
        self._set_var(self, "fx_halftone_var", pack.fx_halftone)
        self._set_var(self, "fx_misregister_var", pack.fx_misregister)
        self._set_var(self, "fx_grain_var", pack.fx_grain)
        self._set_var(self, "seed_mode_var", "fixed")
        self._set_var(self, "inference_mode_var", pack.inference)
        if hasattr(self, "_log"):
            self._log(f"Style pack applied: {name} · {pack.description}")
        return result

    def _render_one(self, frame_path, out_path, settings, width, height, frame_number):
        result = super()._render_one(frame_path, out_path, settings, width, height, frame_number)
        apply_style_finish(Path(out_path), self.preset_var.get(), frame_number)
        return result

    def _render_profile(self) -> dict:
        profile = super()._render_profile()
        name = self.preset_var.get()
        pack = STYLE_PACKS.get(name)
        profile["style_pack"] = {
            "name": name,
            "finish": pack.finish if pack else "legacy",
            "description": pack.description if pack else "",
        }
        return profile
