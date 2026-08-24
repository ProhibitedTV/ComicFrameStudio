#!/usr/bin/env python3
"""ComicFrame Studio current application layer.

Adds adaptive inference resolution, optional upscale-to-source output, live frame
previews, actionable Stable Diffusion diagnostics, and profile-aware resume safety.
"""
from __future__ import annotations

import json
from pathlib import Path

import tkinter as tk
from tkinter import ttk

from comicframe_ui import ComicFrameStudioUI

APP_VERSION = "1.4"

INFERENCE_MODES = {
    "1280 long edge · recommended": 1280,
    "1024 long edge · fast / stable": 1024,
    "768 long edge · emergency / low VRAM": 768,
    "Source / native · heavy": None,
}


class ComicFrameStudioApp(ComicFrameStudioUI):
    def _build_ui(self):
        self.inference_mode_var = tk.StringVar(value="1280 long edge · recommended")
        self.upscale_to_source_var = tk.BooleanVar(value=True)
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

    def _build_run_card(self):
        card = self._panel(self.left, "5 · Render")
        card.pack(fill="x", pady=8)
        resolution = ttk.Frame(card, style="Panel.TFrame"); resolution.pack(fill="x", pady=(0, 8))
        ttk.Label(resolution, text="Inference", style="Panel.TLabel").pack(side="left")
        ttk.Combobox(resolution, textvariable=self.inference_mode_var, values=list(INFERENCE_MODES.keys()), state="readonly", width=34).pack(side="left", padx=6)
        ttk.Checkbutton(resolution, text="Upscale final video back to source resolution", variable=self.upscale_to_source_var).pack(side="left", padx=8)
        ttk.Label(card, text="Inference resolution changes diffusion workload, not framing. The whole source frame is resized proportionally; nothing is cropped. 1280 long edge is the default because native 1080p SDXL is slower and more prone to memory/numerical failures.", style="Muted.TLabel", wraplength=760).pack(anchor="w", pady=(0, 8))
        row = ttk.Frame(card, style="Panel.TFrame"); row.pack(fill="x")
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

    def _render_one(self, frame_path, out_path, settings, width, height, frame_number):
        target_width, target_height = self._target_dimensions(width, height)
        try:
            result = super()._render_one(frame_path, out_path, settings, width, height, frame_number)
        except RuntimeError as exc:
            text = str(exc)
            if "NansException" in text or "tensor with NaNs" in text or "NaNs was produced" in text:
                raise RuntimeError(
                    "Stable Diffusion produced NaNs in the UNet. ComicFrame did not corrupt the frame. "
                    f"This render was requested at about {target_width}x{target_height}. Try the 1024 or 768 "
                    "inference mode, a different checkpoint/sampler, or enable A1111 full-precision/upcast-cross-attention options. "
                    "Do not use --disable-nan-check as the first fix."
                ) from exc
            if "OutOfMemoryError" in text or "CUDA out of memory" in text:
                raise RuntimeError(
                    "Stable Diffusion ran out of VRAM. ComicFrame preserved the source; no output frame was written. "
                    f"The current diffusion request is about {target_width}x{target_height}. Switch to 1024 or 768 long-edge inference. "
                    "On a 12 GB GPU, avoid A1111 --precision full/--no-half unless required for NaN stability because full precision uses much more VRAM. "
                    "For SDXL, --medvram-sdxl is also worth trying."
                ) from exc
            raise
        self.after(0, lambda p=Path(out_path): self._show_image(p, self.output_preview, "output"))
        self.after(0, lambda n=Path(out_path).name: self.output_preview_status.set(n))
        return result

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
            "controlnet_enabled": bool(self.control_enabled_var.get()),
            "controlnet_module": self.control_module_var.get().strip(),
            "controlnet_model": self.control_model_var.get().strip(),
            "controlnet_weight": float(self.control_weight_var.get()),
            "inference_mode": self.inference_mode_var.get(),
            "upscale_final_to_source": bool(self.upscale_to_source_var.get()),
        }

    def _prepare_resume_state(self, start, count, test_only):
        p = self.project_paths()
        p["root"].mkdir(parents=True, exist_ok=True); p["test"].mkdir(parents=True, exist_ok=True); p["styled"].mkdir(parents=True, exist_ok=True)
        profile = self._render_profile(); profile_path = p["root"] / "comicframe_profile.json"
        if test_only:
            if count is not None:
                for frame_number in range(start, start + count):
                    candidate = p["test"] / f"frame_{frame_number:06d}.png"
                    if candidate.exists(): candidate.unlink()
            (p["root"] / "comicframe_test_profile.json").write_text(json.dumps(profile, indent=2), encoding="utf-8")
            return
        existing = sorted(p["styled"].glob("frame_*.png"))
        if existing:
            if not profile_path.exists():
                raise RuntimeError("Existing styled frames predate profile-aware resume tracking. Use a new project directory or remove styled_frames before starting this full render.")
            old_profile = json.loads(profile_path.read_text(encoding="utf-8"))
            if old_profile != profile:
                raise RuntimeError("Current settings do not match the profile that created the existing styled frames. Restore the prior settings, use a new project directory, or clear styled_frames.")
        profile_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")

    def _render_range(self, start, count, test_only):
        self._prepare_resume_state(start, count, test_only)
        return super()._render_range(start, count, test_only)

    def _assemble(self, info):
        p = self.project_paths(); video = Path(self.video_var.get().strip()).expanduser().resolve()
        frames = sorted(p["frames"].glob("frame_*.png")); styled = sorted(p["styled"].glob("frame_*.png"))
        if len(styled) < len(frames): raise RuntimeError(f"Cannot assemble full video: {len(styled)}/{len(frames)} styled frames exist.")
        self._set_progress(92, "Encoding styled video…")
        fps_expr = info.get("fps_expr") or str(info["fps"])
        encode = ["ffmpeg", "-y", "-framerate", fps_expr, "-i", str(p["styled"] / "frame_%06d.png")]
        target_w, target_h = self._target_dimensions(info["width"], info["height"])
        if self.upscale_to_source_var.get() and (target_w, target_h) != (info["width"], info["height"]):
            encode += ["-vf", f"scale={info['width']}:{info['height']}:flags=lanczos"]
        encode += ["-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(p["silent"])]
        self._run(encode)
        self._set_progress(97, "Restoring original audio…")
        self._run(["ffmpeg", "-y", "-i", str(p["silent"]), "-i", str(video), "-map", "0:v:0", "-map", "1:a:0?", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(p["final"])])
        self._set_progress(100, f"DONE: {p['final']}"); self._log(f"FINAL VIDEO: {p['final']}")


def main():
    ComicFrameStudioApp().mainloop()


if __name__ == "__main__":
    main()
