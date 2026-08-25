#!/usr/bin/env python3
"""ControlNet-first video continuity for ComicFrame Studio.

This layer turns ComicFrame from an image batch renderer into a source-faithful
video stylizer: ControlNet is required by default, RTX 3060-class VRAM is
probed/tuned automatically, and a motion-aware temporal lock suppresses shimmer
without blending across moving regions or scene cuts.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import requests
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageChops, ImageFilter, ImageStat


VIDEO_FIDELITY_PRESET = {
    "denoise": 0.40,
    "steps": 24,
    "cfg": 5.5,
    "fx": 0.72,
    "prompt": (
        "source-faithful comic animation frame, restyle the photographed frame without redesigning it, "
        "hard inked contour hierarchy, clean cel-shadow shapes, restrained halftone and screen-print texture, "
        "graphic color separation, cinematic contrast, preserve exact identity, expression, pose, hands, clothing, "
        "object count, furniture, architecture, camera position, lens perspective, crop, silhouette and scene geometry, "
        "same shot and same action as the source video frame"
    ),
}


class ControlNetFirstVideoMixin:
    """Make ControlNet + temporal stabilization the default production path."""

    def _build_ui(self):
        # These must exist before ComicFrameStudioUI builds the continuity card.
        self.control_required_var = tk.BooleanVar(value=True)
        self.control_guidance_end_var = tk.DoubleVar(value=0.92)
        self.control_low_vram_var = tk.BooleanVar(value=False)
        self.temporal_enabled_var = tk.BooleanVar(value=True)
        self.temporal_strength_var = tk.DoubleVar(value=0.35)
        self.temporal_motion_var = tk.DoubleVar(value=0.08)
        self.temporal_cut_var = tk.DoubleVar(value=0.22)
        self.gpu_status_var = tk.StringVar(value="GPU memory not probed yet")
        self._detected_vram_gb: float | None = None

        # Add a fidelity-first preset without forcing a rewrite of the app layer.
        try:
            import comicframe_app as app_layer
            app_layer.STYLE_PRESETS.setdefault("Video Fidelity · RTX 3060", VIDEO_FIDELITY_PRESET)
        except Exception:
            pass
        super()._build_ui()

    def __init__(self):
        super().__init__()
        self.title("ComicFrame Studio 1.6 · ControlNet Video Lock")
        self.control_enabled_var.set(True)
        self.seed_mode_var.set("fixed")
        self.control_weight_var.set(0.95)

    # ---------- Fidelity-first look ----------

    def _build_style_card(self):
        super()._build_style_card()
        try:
            self.preset_var.set("Video Fidelity · RTX 3060")
            self._apply_preset()
        except Exception:
            # The renderer remains usable if a future app layer changes preset plumbing.
            self.denoise_var.set(0.40)
            self.steps_var.set(24)
            self.cfg_var.set(5.5)

    # ---------- ControlNet + temporal UI ----------

    def _build_continuity_card(self):
        card = self._panel(self.left, "4 · Video lock · ControlNet required by default")
        card.pack(fill="x", pady=8)

        row = ttk.Frame(card, style="Panel.TFrame")
        row.pack(fill="x")
        self.cn_check = ttk.Checkbutton(
            row,
            text="Use ControlNet structural guidance",
            variable=self.control_enabled_var,
        )
        self.cn_check.pack(side="left")
        ttk.Checkbutton(row, text="Require for render", variable=self.control_required_var).pack(side="left", padx=8)
        ttk.Button(row, text="Detect / auto-select", command=self._detect_controlnet_background).pack(side="left", padx=7)
        self.cn_status_label = ttk.Label(row, textvariable=self.cn_status_var, style="Muted.TLabel")
        self.cn_status_label.pack(side="left", padx=5)

        ttk.Label(
            card,
            text=(
                "ComicFrame now treats ControlNet as the normal production path. Canny anchors the source silhouette, "
                "pose, furniture and camera geometry while img2img changes rendering style. Model/module selection is "
                "automatic when a compatible Canny model is exposed by the WebUI."
            ),
            style="Muted.TLabel",
            wraplength=760,
        ).pack(anchor="w", pady=(5, 7))

        fields = ttk.Frame(card, style="Panel.TFrame")
        fields.pack(fill="x")
        ttk.Label(fields, text="Module", style="Panel.TLabel").grid(row=0, column=0, sticky="w")
        self.control_module_combo = ttk.Combobox(
            fields,
            textvariable=self.control_module_var,
            values=["canny", "lineart_realistic", "lineart"],
            width=22,
        )
        self.control_module_combo.grid(row=1, column=0, sticky="ew", padx=(0, 6))

        ttk.Label(fields, text="Model", style="Panel.TLabel").grid(row=0, column=1, sticky="w")
        self.control_model_combo = ttk.Combobox(fields, textvariable=self.control_model_var)
        self.control_model_combo.grid(row=1, column=1, sticky="ew", padx=(0, 6))

        ttk.Label(fields, text="Weight", style="Panel.TLabel").grid(row=0, column=2, sticky="w")
        ttk.Spinbox(fields, textvariable=self.control_weight_var, from_=0.0, to=2.0, increment=0.05, width=9).grid(
            row=1, column=2, sticky="ew", padx=(0, 6)
        )

        ttk.Label(fields, text="Guidance end", style="Panel.TLabel").grid(row=0, column=3, sticky="w")
        ttk.Spinbox(fields, textvariable=self.control_guidance_end_var, from_=0.2, to=1.0, increment=0.02, width=10).grid(
            row=1, column=3, sticky="ew", padx=(0, 6)
        )

        ttk.Checkbutton(fields, text="Low-VRAM CN", variable=self.control_low_vram_var).grid(
            row=1, column=4, sticky="w"
        )
        fields.columnconfigure(1, weight=1)

        temporal = ttk.LabelFrame(card, text="Motion-aware temporal lock", padding=8)
        temporal.pack(fill="x", pady=(10, 0))
        tr = ttk.Frame(temporal, style="Panel.TFrame")
        tr.pack(fill="x")
        ttk.Checkbutton(tr, text="Stabilize unchanged regions", variable=self.temporal_enabled_var).pack(side="left")
        ttk.Label(tr, text="Strength", style="Panel.TLabel").pack(side="left", padx=(12, 3))
        ttk.Spinbox(tr, textvariable=self.temporal_strength_var, from_=0.0, to=0.75, increment=0.05, width=7).pack(side="left")
        ttk.Label(tr, text="Motion threshold", style="Panel.TLabel").pack(side="left", padx=(12, 3))
        ttk.Spinbox(tr, textvariable=self.temporal_motion_var, from_=0.01, to=0.5, increment=0.01, width=7).pack(side="left")
        ttk.Label(tr, text="Scene cut", style="Panel.TLabel").pack(side="left", padx=(12, 3))
        ttk.Spinbox(tr, textvariable=self.temporal_cut_var, from_=0.05, to=0.8, increment=0.01, width=7).pack(side="left")
        ttk.Label(
            temporal,
            text=(
                "The previous styled frame is reused only where consecutive source frames are visually stable. "
                "Moving pixels stay current; hard cuts bypass temporal blending entirely. This reduces texture/line shimmer "
                "without smearing motion."
            ),
            style="Muted.TLabel",
            wraplength=740,
        ).pack(anchor="w", pady=(5, 0))

        ttk.Label(card, textvariable=self.gpu_status_var, style="Muted.TLabel").pack(anchor="w", pady=(8, 0))

    # ---------- WebUI / GPU / ControlNet auto configuration ----------

    @staticmethod
    def _vram_total_bytes(data: Any) -> int | None:
        if not isinstance(data, dict):
            return None
        cuda = data.get("cuda")
        if isinstance(cuda, dict):
            system = cuda.get("system")
            if isinstance(system, dict):
                total = system.get("total")
                if isinstance(total, (int, float)) and total > 0:
                    return int(total)
        return None

    def _probe_gpu_memory(self):
        try:
            response = requests.get(f"{self.api_url()}/sdapi/v1/memory", timeout=15)
            if not response.ok:
                return
            total = self._vram_total_bytes(response.json())
            if not total:
                return
            gib = total / (1024 ** 3)
            self._detected_vram_gb = gib
            if gib < 8.0:
                self.control_low_vram_var.set(True)
                if self.inference_mode_var.get().startswith("1280") or self.inference_mode_var.get().startswith("Source"):
                    self.inference_mode_var.set("768 long edge · emergency / low VRAM")
                self.gpu_status_var.set(f"GPU VRAM detected: {gib:.1f} GiB · low-VRAM ControlNet enabled · prefer 768")
            else:
                self.control_low_vram_var.set(False)
                if self.inference_mode_var.get().startswith("Source"):
                    self.inference_mode_var.set("1024 long edge · fast / stable")
                self.gpu_status_var.set(f"GPU VRAM detected: {gib:.1f} GiB · RTX 3060-class profile · 1024 recommended")
            self._log(f"GPU memory probe: {gib:.1f} GiB VRAM")
        except Exception as exc:
            self._log(f"GPU memory probe skipped: {exc}")

    def _sync_webui(self):
        result = super()._sync_webui()
        self._probe_gpu_memory()
        return result

    @staticmethod
    def _looks_sdxl(name: str) -> bool:
        low = name.lower()
        return "sdxl" in low or " xl" in low or low.startswith("xl") or "xl_" in low or "_xl" in low

    def _select_controlnet_defaults(self):
        values = list(self.control_model_combo["values"] or [])
        modules = list(self.control_module_combo["values"] or [])
        if not values:
            return
        checkpoint = self.checkpoint_var.get().strip()
        wants_xl = self._looks_sdxl(checkpoint)

        def score(name: str) -> tuple[int, int, int, int]:
            low = name.lower()
            canny = 1 if "canny" in low else 0
            family = 1 if self._looks_sdxl(name) == wants_xl else 0
            mid = 1 if "mid" in low else 0
            small = 1 if "small" in low else 0
            return (canny, family, mid, small)

        best = max(values, key=score)
        self.control_model_var.set(best)
        if modules:
            module = next((m for m in modules if m.lower() == "canny"), None)
            if not module:
                module = next((m for m in modules if "canny" in m.lower()), modules[0])
            self.control_module_var.set(module)
        self.control_enabled_var.set(True)
        self.control_weight_var.set(0.95)
        self._log(f"ControlNet auto-selected: module={self.control_module_var.get()}, model={best}")

    def _detect_controlnet(self):
        result = super()._detect_controlnet()
        if getattr(self, "_controlnet_available", False):
            self.control_enabled_var.set(True)
            # DirectControlNetProbeMixin applies combo values on the Tk event loop.
            self.after(25, self._select_controlnet_defaults)
        return result

    def _validate_controlnet_family(self):
        checkpoint = self.checkpoint_var.get().strip()
        model = self.control_model_var.get().strip()
        if not model:
            raise RuntimeError("ControlNet is available but no model is selected. Click Detect / auto-select and retry.")
        if self._looks_sdxl(checkpoint) and any(tag in model.lower() for tag in ("sd15", "sd1.5", "1.5")):
            raise RuntimeError(
                f"Checkpoint looks like SDXL but ControlNet model looks like SD1.5: {model}. "
                "Install/select an SDXL Canny ControlNet model."
            )

    # ---------- Request hardening ----------

    def _build_payload(self, frame_path, settings, width, height, frame_number):
        payload = super()._build_payload(frame_path, settings, width, height, frame_number)
        scripts = payload.get("alwayson_scripts")
        if isinstance(scripts, dict):
            cn = scripts.get("controlnet") or scripts.get("ControlNet")
            if isinstance(cn, dict):
                args = cn.get("args")
                if isinstance(args, list):
                    for unit in args:
                        if not isinstance(unit, dict):
                            continue
                        unit["weight"] = float(self.control_weight_var.get())
                        unit["guidance_start"] = 0.0
                        unit["guidance_end"] = float(self.control_guidance_end_var.get())
                        unit["low_vram"] = bool(self.control_low_vram_var.get())
                        unit["pixel_perfect"] = True
                        unit["control_mode"] = 0
                        # Do not preprocess above the actual diffusion edge.
                        target_w = int(payload.get("width") or width)
                        target_h = int(payload.get("height") or height)
                        unit["processor_res"] = min(1024, max(target_w, target_h))
        return payload

    # ---------- Motion-aware temporal stabilization ----------

    def _temporal_lock(self, frame_path: Path, out_path: Path, frame_number: int):
        if not self.temporal_enabled_var.get() or frame_number <= 1:
            return
        previous_out = out_path.parent / f"frame_{frame_number - 1:06d}.png"
        previous_source = frame_path.parent / f"frame_{frame_number - 1:06d}.png"
        if not previous_out.exists() or not previous_source.exists():
            return

        strength = max(0.0, min(0.75, float(self.temporal_strength_var.get())))
        if strength <= 0:
            return
        motion_threshold = max(0.0, min(0.95, float(self.temporal_motion_var.get())))
        cut_threshold = max(0.01, min(0.95, float(self.temporal_cut_var.get())))

        with Image.open(out_path) as cur_im, Image.open(previous_out) as prev_im:
            current = cur_im.convert("RGB")
            previous = prev_im.convert("RGB")
            if previous.size != current.size:
                previous = previous.resize(current.size, Image.Resampling.LANCZOS)

            with Image.open(frame_path) as src_cur_im, Image.open(previous_source) as src_prev_im:
                source_current = src_cur_im.convert("RGB").resize(current.size, Image.Resampling.BILINEAR)
                source_previous = src_prev_im.convert("RGB").resize(current.size, Image.Resampling.BILINEAR)

            diff = ImageChops.difference(source_current, source_previous).convert("L")
            mean_change = ImageStat.Stat(diff).mean[0] / 255.0
            if mean_change >= cut_threshold:
                self._log(
                    f"Temporal lock: frame {frame_number} treated as scene cut "
                    f"({mean_change:.3f} >= {cut_threshold:.3f})"
                )
                return

            floor = int(motion_threshold * 255)
            denom = max(1, 255 - floor)
            motion_mask = diff.point(
                lambda value: 0 if value <= floor else min(255, int((value - floor) * 255 / denom))
            )
            blur_radius = max(1.0, min(current.size) / 420.0)
            motion_mask = motion_mask.filter(ImageFilter.GaussianBlur(radius=blur_radius))

            # White selects current; black selects previous. The baseline keeps
            # most of the current render even in static areas, preventing drag.
            baseline = int(round(255 * (1.0 - strength)))
            span = 255 - baseline
            effective_mask = motion_mask.point(lambda value: min(255, baseline + int(span * value / 255)))
            stabilized = Image.composite(current, previous, effective_mask)
            stabilized.save(out_path, format="PNG", optimize=False)

    def _render_one(self, frame_path, out_path, settings, width, height, frame_number):
        result = super()._render_one(frame_path, out_path, settings, width, height, frame_number)
        self._temporal_lock(Path(frame_path), Path(out_path), frame_number)
        return result

    # ---------- Resume profile / preflight ----------

    def _render_profile(self) -> dict:
        profile = super()._render_profile()
        profile["video_lock"] = {
            "controlnet_required": bool(self.control_required_var.get()),
            "controlnet_guidance_end": float(self.control_guidance_end_var.get()),
            "controlnet_low_vram": bool(self.control_low_vram_var.get()),
            "temporal_enabled": bool(self.temporal_enabled_var.get()),
            "temporal_strength": float(self.temporal_strength_var.get()),
            "temporal_motion_threshold": float(self.temporal_motion_var.get()),
            "temporal_scene_cut_threshold": float(self.temporal_cut_var.get()),
        }
        return profile

    def _render_range(self, start, count, test_only):
        if self.seed_mode_var.get() != "fixed":
            self._log("Video lock forces fixed seed mode to prevent avoidable frame-to-frame diffusion drift.")
            self.seed_mode_var.set("fixed")

        if self.control_required_var.get():
            if not getattr(self, "_controlnet_available", False):
                self._log("ControlNet preflight: probing extension and models before render.")
                self._detect_controlnet()
            if not getattr(self, "_controlnet_available", False):
                raise RuntimeError(
                    "ControlNet is required for this render but no usable ControlNet model was detected. "
                    "Install sd-webui-controlnet plus a checkpoint-compatible Canny model, Sync WebUI, then retry. "
                    "You can explicitly disable 'Require for render' for diagnostic img2img-only tests."
                )
            self.control_enabled_var.set(True)
            # If async combo application has not happened yet, try one direct selection pass.
            self._select_controlnet_defaults()
            self._validate_controlnet_family()

        self._probe_gpu_memory()
        self._log(
            "Video-lock preflight: "
            f"ControlNet={'ON' if self.control_enabled_var.get() else 'OFF'}, "
            f"temporal={'ON' if self.temporal_enabled_var.get() else 'OFF'}, "
            f"inference={self.inference_mode_var.get()}, seed=fixed"
        )
        return super()._render_range(start, count, test_only)
