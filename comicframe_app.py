#!/usr/bin/env python3
"""ComicFrame Studio current application layer.

v1.5 adds an aggressive deterministic graphic-print finishing stack and optional
A1111 LoRA discovery on top of the adaptive v1.4 render pipeline.
"""
from __future__ import annotations

import json
from pathlib import Path

import requests
import tkinter as tk
from tkinter import ttk

from comicframe_fx import GraphicFXSettings, apply_graphic_fx
from comicframe_ui import ComicFrameStudioUI

APP_VERSION = "1.5"

INFERENCE_MODES = {
    "1280 long edge · recommended": 1280,
    "1024 long edge · fast / stable": 1024,
    "768 long edge · emergency / low VRAM": 768,
    "Source / native · heavy": None,
}

STYLE_PRESETS = {
    "Graphic Shock · maximum print": {
        "denoise": 0.55,
        "steps": 30,
        "cfg": 6.0,
        "fx": 0.90,
        "prompt": (
            "feature-animation comic frame, extreme mixed-media print aesthetic, hard hand-inked contour shapes, "
            "bold two-tone and three-tone posterized shading, offset screen-print plates, dense halftone shadow fields, "
            "Ben-Day dots, crosshatching, dry-brush ink texture, colored rim-light blocks, doubled contour accents, "
            "cyan magenta orange electric-blue color separation, graphic shadow shapes, punchy silhouette design, "
            "dynamic smear-frame energy, intentionally imperfect print registration, dramatic cinematic composition, "
            "preserve the same person, pose, clothing, furniture, architecture, camera position and complete frame"
        ),
    },
    "Comic Punch · strong": {
        "denoise": 0.48,
        "steps": 28,
        "cfg": 6.25,
        "fx": 0.78,
        "prompt": (
            "graphic comic-book feature animation frame, aggressive ink contours, bold cel shadow masses, "
            "halftone dots, crosshatching, screen-print texture, posterized color blocks, offset cyan and magenta ink, "
            "orange and electric blue split lighting, strong silhouette, crisp illustrated details, preserve identity, "
            "pose, room layout, furniture placement, camera framing and full-body proportions"
        ),
    },
    "Structure First · ControlNet test": {
        "denoise": 0.42,
        "steps": 26,
        "cfg": 5.75,
        "fx": 0.62,
        "prompt": (
            "graphic inked animation frame, readable contour hierarchy, posterized cel shadow shapes, comic print texture, "
            "halftone shading, controlled color separation, preserve exact scene geometry, pose, identity and camera framing"
        ),
    },
    "Diffusion Only · diagnostic": {
        "denoise": 0.40,
        "steps": 24,
        "cfg": 6.0,
        "fx": 0.0,
        "prompt": (
            "cinematic comic illustration, inked contours, cel shading, graphic lighting, saturated comic color separation, "
            "preserve pose, identity, scene geometry and camera framing"
        ),
    },
}

NEGATIVE = (
    "photorealism, realistic skin pores, soft painterly rendering, watercolor, airbrush, blurry, low contrast, "
    "weak outlines, muddy colors, flat lighting, generic 3d render, plastic skin, extra arms, extra legs, extra fingers, "
    "missing fingers, duplicated person, warped face, malformed face, changed hairstyle, changed clothes, cropped body, "
    "zoomed-in composition, different camera angle, changed room layout, duplicated furniture, missing furniture, "
    "invented machinery, transformed furniture, random circular objects, text artifacts, random lettering, logo artifacts, "
    "fisheye distortion, melted objects, deformed anatomy"
)


class ComicFrameStudioApp(ComicFrameStudioUI):
    def _build_ui(self):
        self.inference_mode_var = tk.StringVar(value="1024 long edge · fast / stable")
        self.upscale_to_source_var = tk.BooleanVar(value=True)
        self.lora_var = tk.StringVar(value="(none)")
        self.lora_weight_var = tk.DoubleVar(value=0.75)
        self.fx_enabled_var = tk.BooleanVar(value=True)
        self.fx_intensity_var = tk.DoubleVar(value=0.90)
        self.fx_ink_var = tk.BooleanVar(value=True)
        self.fx_posterize_var = tk.BooleanVar(value=True)
        self.fx_halftone_var = tk.BooleanVar(value=True)
        self.fx_misregister_var = tk.BooleanVar(value=True)
        self.fx_grain_var = tk.BooleanVar(value=True)
        self._lora_names: list[str] = []
        super()._build_ui()

    def __init__(self):
        super().__init__()
        self.title(f"ComicFrame Studio {APP_VERSION}")

    @staticmethod
    def _round_to_multiple(value: float, multiple: int = 8) -> int:
        return max(multiple, int(round(value / multiple) * multiple))

    def _target_dimensions(self, source_width: int, source_height: int) -> tuple[int, int]:
        max_edge = INFERENCE_MODES.get(self.inference_mode_var.get())
        if max_edge is None or max(source_width, source_height) <= max_edge:
            return source_width, source_height
        scale = max_edge / max(source_width, source_height)
        return self._round_to_multiple(source_width * scale), self._round_to_multiple(source_height * scale)

    # ---------- Look / style UI ----------

    def _build_style_card(self):
        card = self._panel(self.left, "3 · Look + graphic print stack")
        card.pack(fill="x", pady=8)
        self.preset_var.set("Graphic Shock · maximum print")

        top = ttk.Frame(card, style="Panel.TFrame")
        top.pack(fill="x", pady=(0, 6))
        ttk.Label(top, text="Preset", width=12, style="Panel.TLabel").pack(side="left")
        ttk.Combobox(
            top,
            textvariable=self.preset_var,
            state="readonly",
            values=list(STYLE_PRESETS.keys()),
            width=34,
        ).pack(side="left", padx=5)
        ttk.Button(top, text="Apply preset", command=self._apply_preset).pack(side="left")

        ttk.Label(card, text="Positive prompt", style="Panel.TLabel").pack(anchor="w")
        self.prompt_text = self._make_text(card, 5)
        self.prompt_text.pack(fill="x", pady=(2, 6))
        self.prompt_text.insert("1.0", STYLE_PRESETS[self.preset_var.get()]["prompt"])

        ttk.Label(card, text="Negative prompt", style="Panel.TLabel").pack(anchor="w")
        self.negative_text = self._make_text(card, 3)
        self.negative_text.pack(fill="x", pady=(2, 8))
        self.negative_text.insert("1.0", NEGATIVE)

        g = ttk.Frame(card, style="Panel.TFrame")
        g.pack(fill="x")
        self._dark_spin(g, "Steps", self.steps_var, 1, 100, 0)
        self._dark_spin(g, "CFG", self.cfg_var, 1, 30, 1, 0.25)
        self._dark_spin(g, "Diffusion strength", self.denoise_var, 0.05, 0.95, 2, 0.01)
        self._dark_spin(g, "Seed", self.seed_var, -1, 2147483647, 3)
        for i in range(4):
            g.columnconfigure(i, weight=1)

        seedrow = ttk.Frame(card, style="Panel.TFrame")
        seedrow.pack(fill="x", pady=(7, 3))
        ttk.Label(seedrow, text="Seed behavior", style="Panel.TLabel").pack(side="left")
        ttk.Combobox(
            seedrow,
            textvariable=self.seed_mode_var,
            values=["fixed", "increment"],
            state="readonly",
            width=14,
        ).pack(side="left", padx=6)
        ttk.Label(
            seedrow,
            text="Fixed keeps neighboring frames making similar diffusion decisions.",
            style="Muted.TLabel",
        ).pack(side="left", padx=6)

        lora = ttk.Frame(card, style="Panel.TFrame")
        lora.pack(fill="x", pady=(7, 3))
        ttk.Label(lora, text="Style LoRA", width=12, style="Panel.TLabel").pack(side="left")
        self.lora_combo = ttk.Combobox(lora, textvariable=self.lora_var, state="readonly", values=["(none)"])
        self.lora_combo.pack(side="left", fill="x", expand=True, padx=5)
        ttk.Label(lora, text="Weight", style="Panel.TLabel").pack(side="left", padx=(8, 3))
        ttk.Spinbox(lora, textvariable=self.lora_weight_var, from_=0.05, to=2.0, increment=0.05, width=8).pack(side="left")
        ttk.Label(
            card,
            text="LoRAs are discovered from A1111 automatically. Use an illustration/comic SDXL LoRA here when installed; ControlNet handles structure while the LoRA supplies learned style.",
            style="Muted.TLabel",
            wraplength=760,
        ).pack(anchor="w", pady=(2, 6))

        fx = ttk.Frame(card, style="Panel.TFrame")
        fx.pack(fill="x", pady=(4, 2))
        ttk.Checkbutton(fx, text="Graphic Print Finish", variable=self.fx_enabled_var).pack(side="left")
        ttk.Label(fx, text="Intensity", style="Panel.TLabel").pack(side="left", padx=(10, 3))
        ttk.Spinbox(fx, textvariable=self.fx_intensity_var, from_=0.0, to=1.0, increment=0.05, width=7).pack(side="left")
        ttk.Checkbutton(fx, text="Ink", variable=self.fx_ink_var).pack(side="left", padx=(12, 2))
        ttk.Checkbutton(fx, text="Posterize", variable=self.fx_posterize_var).pack(side="left", padx=2)
        ttk.Checkbutton(fx, text="Halftone", variable=self.fx_halftone_var).pack(side="left", padx=2)
        ttk.Checkbutton(fx, text="CMYK split", variable=self.fx_misregister_var).pack(side="left", padx=2)
        ttk.Checkbutton(fx, text="Grain", variable=self.fx_grain_var).pack(side="left", padx=2)
        ttk.Label(
            card,
            text="The finishing stack is deterministic and applies to the whole completed frame: hard ink reinforcement, color posterization, shadow halftones, controlled print misregistration and grain. This is intentionally much more aggressive than ordinary cel shading.",
            style="Muted.TLabel",
            wraplength=760,
        ).pack(anchor="w", pady=(4, 0))

        self._apply_preset()

    def _apply_preset(self):
        p = STYLE_PRESETS[self.preset_var.get()]
        self.denoise_var.set(p["denoise"])
        self.steps_var.set(p["steps"])
        self.cfg_var.set(p["cfg"])
        self.fx_enabled_var.set(p["fx"] > 0)
        self.fx_intensity_var.set(p["fx"])
        self.prompt_text.delete("1.0", "end")
        self.prompt_text.insert("1.0", p["prompt"])

    # ---------- WebUI / LoRA discovery ----------

    def _sync_webui(self):
        super()._sync_webui()
        self._sync_loras()

    def _sync_loras(self):
        url = self.api_url()
        try:
            r = requests.get(f"{url}/sdapi/v1/loras", timeout=20)
            if not r.ok:
                self._log(f"LoRA discovery unavailable: HTTP {r.status_code}")
                return
            names: list[str] = []
            data = r.json()
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, str):
                        name = item
                    elif isinstance(item, dict):
                        name = str(item.get("name") or item.get("alias") or "").strip()
                    else:
                        name = ""
                    if name and name not in names:
                        names.append(name)
            self._lora_names = names

            def apply():
                values = ["(none)"] + names
                self.lora_combo["values"] = values
                if self.lora_var.get() not in values:
                    self.lora_var.set("(none)")

            self.after(0, apply)
            self._log(f"LoRAs discovered: {len(names)}")
        except Exception as exc:
            self._log(f"LoRA discovery skipped: {exc}")

    def _settings(self):
        settings = super()._settings()
        selected = self.lora_var.get().strip()
        if selected and selected != "(none)":
            weight = float(self.lora_weight_var.get())
            token = f"<lora:{selected}:{weight:.2f}>"
            settings.prompt = f"{token}, {settings.prompt}"
        return settings

    # ---------- Render / post processing ----------

    def _build_run_card(self):
        card = self._panel(self.left, "5 · Render")
        card.pack(fill="x", pady=8)
        resolution = ttk.Frame(card, style="Panel.TFrame")
        resolution.pack(fill="x", pady=(0, 8))
        ttk.Label(resolution, text="Inference", style="Panel.TLabel").pack(side="left")
        ttk.Combobox(
            resolution,
            textvariable=self.inference_mode_var,
            values=list(INFERENCE_MODES.keys()),
            state="readonly",
            width=34,
        ).pack(side="left", padx=6)
        ttk.Checkbutton(
            resolution,
            text="Upscale final video back to source resolution",
            variable=self.upscale_to_source_var,
        ).pack(side="left", padx=8)
        ttk.Label(
            card,
            text="Inference resolution changes diffusion workload, not framing. The complete frame is resized proportionally. Start at 1024 on a 12 GB SDXL setup; the deterministic print finish is applied after diffusion at the rendered frame size.",
            style="Muted.TLabel",
            wraplength=760,
        ).pack(anchor="w", pady=(0, 8))

        row = ttk.Frame(card, style="Panel.TFrame")
        row.pack(fill="x")
        ttk.Label(row, text="Test start", style="Panel.TLabel").pack(side="left")
        ttk.Spinbox(row, textvariable=self.test_start_var, from_=1, to=999999, width=8).pack(side="left", padx=5)
        ttk.Label(row, text="Frames", style="Panel.TLabel").pack(side="left", padx=(8, 0))
        ttk.Spinbox(row, textvariable=self.test_count_var, from_=1, to=500, width=8).pack(side="left", padx=5)
        ttk.Button(row, text="Render test", style="Accent.TButton", command=self._test_range_clicked).pack(side="left", padx=(12, 5))
        ttk.Button(row, text="FULL RENDER", style="Accent.TButton", command=self._full_render_clicked).pack(side="left", padx=5)
        ttk.Button(row, text="STOP", style="Danger.TButton", command=self._stop_clicked).pack(side="right")
        ttk.Progressbar(card, variable=self.progress, maximum=100).pack(fill="x", pady=(10, 3))
        ttk.Label(card, textvariable=self.progress_label_var, style="Muted.TLabel").pack(anchor="w")

    def _build_payload(self, frame_path, settings, width, height, frame_number):
        target_width, target_height = self._target_dimensions(width, height)
        return super()._build_payload(frame_path, settings, target_width, target_height, frame_number)

    def _graphic_fx_settings(self) -> GraphicFXSettings:
        return GraphicFXSettings(
            enabled=bool(self.fx_enabled_var.get()),
            intensity=float(self.fx_intensity_var.get()),
            ink=bool(self.fx_ink_var.get()),
            posterize=bool(self.fx_posterize_var.get()),
            halftone=bool(self.fx_halftone_var.get()),
            misregistration=bool(self.fx_misregister_var.get()),
            grain=bool(self.fx_grain_var.get()),
        )

    def _render_one(self, frame_path, out_path, settings, width, height, frame_number):
        target_width, target_height = self._target_dimensions(width, height)
        try:
            result = super()._render_one(frame_path, out_path, settings, width, height, frame_number)
            apply_graphic_fx(Path(out_path), self._graphic_fx_settings(), frame_number)
        except RuntimeError as exc:
            text = str(exc)
            if "NansException" in text or "tensor with NaNs" in text or "NaNs was produced" in text:
                raise RuntimeError(
                    "Stable Diffusion produced NaNs in the UNet. ComicFrame did not corrupt the frame. "
                    f"This request is about {target_width}x{target_height}. Try 1024 or 768 inference, a different checkpoint/sampler, "
                    "or A1111 upcast-cross-attention. Avoid --disable-nan-check as the first fix."
                ) from exc
            if "OutOfMemoryError" in text or "CUDA out of memory" in text:
                raise RuntimeError(
                    "Stable Diffusion ran out of VRAM before ComicFrame's print finish. "
                    f"The diffusion request is about {target_width}x{target_height}. Switch to 1024 or 768 long-edge inference. "
                    "On a 12 GB GPU prefer --medvram-sdxl and avoid full-precision SDXL unless it is required for stability."
                ) from exc
            raise
        self.after(0, lambda p=Path(out_path): self._show_image(p, self.output_preview, "output"))
        self.after(0, lambda n=Path(out_path).name: self.output_preview_status.set(n))
        return result

    # ---------- Resume manifest ----------

    def _render_profile(self) -> dict:
        return {
            "app_version": APP_VERSION,
            "checkpoint": self.checkpoint_var.get().strip(),
            "sampler": self.sampler_var.get().strip(),
            "scheduler": self.scheduler_var.get().strip(),
            "steps": int(self.steps_var.get()),
            "cfg": float(self.cfg_var.get()),
            "style_strength": float(self.denoise_var.get()),
            "seed": int(self.seed_var.get()),
            "seed_mode": self.seed_mode_var.get(),
            "positive_prompt": self.prompt_text.get("1.0", "end").strip(),
            "negative_prompt": self.negative_text.get("1.0", "end").strip(),
            "lora": self.lora_var.get().strip(),
            "lora_weight": float(self.lora_weight_var.get()),
            "controlnet_enabled": bool(self.control_enabled_var.get()),
            "controlnet_module": self.control_module_var.get().strip(),
            "controlnet_model": self.control_model_var.get().strip(),
            "controlnet_weight": float(self.control_weight_var.get()),
            "inference_mode": self.inference_mode_var.get(),
            "upscale_final_to_source": bool(self.upscale_to_source_var.get()),
            "graphic_fx": {
                "enabled": bool(self.fx_enabled_var.get()),
                "intensity": float(self.fx_intensity_var.get()),
                "ink": bool(self.fx_ink_var.get()),
                "posterize": bool(self.fx_posterize_var.get()),
                "halftone": bool(self.fx_halftone_var.get()),
                "misregistration": bool(self.fx_misregister_var.get()),
                "grain": bool(self.fx_grain_var.get()),
            },
        }

    def _prepare_resume_state(self, start, count, test_only):
        p = self.project_paths()
        p["root"].mkdir(parents=True, exist_ok=True)
        p["test"].mkdir(parents=True, exist_ok=True)
        p["styled"].mkdir(parents=True, exist_ok=True)
        profile = self._render_profile()
        profile_path = p["root"] / "comicframe_profile.json"
        if test_only:
            if count is not None:
                for frame_number in range(start, start + count):
                    candidate = p["test"] / f"frame_{frame_number:06d}.png"
                    if candidate.exists():
                        candidate.unlink()
            (p["root"] / "comicframe_test_profile.json").write_text(json.dumps(profile, indent=2), encoding="utf-8")
            return
        existing = sorted(p["styled"].glob("frame_*.png"))
        if existing:
            if not profile_path.exists():
                raise RuntimeError(
                    "Existing styled frames predate profile-aware resume tracking. Use a new project directory or remove styled_frames before starting this full render."
                )
            old_profile = json.loads(profile_path.read_text(encoding="utf-8"))
            if old_profile != profile:
                raise RuntimeError(
                    "Current settings do not match the profile that created the existing styled frames. Restore the prior settings, use a new project directory, or clear styled_frames."
                )
        profile_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")

    def _render_range(self, start, count, test_only):
        self._prepare_resume_state(start, count, test_only)
        return super()._render_range(start, count, test_only)

    def _assemble(self, info):
        p = self.project_paths()
        video = Path(self.video_var.get().strip()).expanduser().resolve()
        frames = sorted(p["frames"].glob("frame_*.png"))
        styled = sorted(p["styled"].glob("frame_*.png"))
        if len(styled) < len(frames):
            raise RuntimeError(f"Cannot assemble full video: {len(styled)}/{len(frames)} styled frames exist.")
        self._set_progress(92, "Encoding styled video…")
        fps_expr = info.get("fps_expr") or str(info["fps"])
        encode = ["ffmpeg", "-y", "-framerate", fps_expr, "-i", str(p["styled"] / "frame_%06d.png")]
        target_w, target_h = self._target_dimensions(info["width"], info["height"])
        if self.upscale_to_source_var.get() and (target_w, target_h) != (info["width"], info["height"]):
            encode += ["-vf", f"scale={info['width']}:{info['height']}:flags=lanczos"]
        encode += [
            "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(p["silent"])
        ]
        self._run(encode)
        self._set_progress(97, "Restoring original audio…")
        self._run([
            "ffmpeg", "-y", "-i", str(p["silent"]), "-i", str(video), "-map", "0:v:0", "-map", "1:a:0?", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(p["final"])
        ])
        self._set_progress(100, f"DONE: {p['final']}")
        self._log(f"FINAL VIDEO: {p['final']}")


def main():
    ComicFrameStudioApp().mainloop()


if __name__ == "__main__":
    main()
