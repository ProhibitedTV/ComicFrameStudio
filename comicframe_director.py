#!/usr/bin/env python3
"""Easy Shot Director for ComicFrame Studio v2.2.

The renderer has become deliberately sophisticated; the primary UI should not.
This layer turns the existing style/ControlNet/temporal stack into a simple
shot-oriented workflow:

    choose video -> analyze shots -> choose treatment -> preview -> render

Advanced controls remain available, but Easy Mode is the default surface.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any

import tkinter as tk
from tkinter import messagebox, ttk
from PIL import Image, ImageDraw, ImageOps

import comicframe_optical_flow as flow
from comicframe_styles import STYLE_PACKS, StylePack


ORIGINAL = "Original Footage"

LOOKS: dict[str, str] = {
    ORIGINAL: ORIGINAL,
    "Clean Comic": "Clean Graphic Novel",
    "Comic": "Comic Punch · strong",
    "Dark / Noir": "Neo-Noir",
    "Cyberpunk": "Cyberpunk Print",
    "Horror": "Pulp Horror",
    "Dream / Surreal": "Dream Collapse",
    "Glitch": "Signal Rupture",
    "Painted": "Gouache Storybook",
    "Analog": "Analog Broadcast",
    "Product Promo": "Corporate Propaganda",
}
STYLE_TO_LOOK = {style: label for label, style in LOOKS.items()}

INTENSITY_LEVELS = {
    "Low": 0.35,
    "Medium": 0.60,
    "High": 0.82,
    "Insane": 1.00,
}

DIRECTIONS = ("Stay", "Build", "Fade")
TREATMENTS = (
    "Clean Comic",
    "Dark Video Essay",
    "Clean → Chaos",
    "Reality Break",
    "Product Promo",
    "Keep It Stable",
)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _lerp(a: float, b: float, t: float) -> float:
    t = _clamp(t)
    return a + (b - a) * t


def _ease(t: float, curve: str) -> float:
    t = _clamp(t)
    if curve == "ease-in":
        return t * t
    if curve == "ease-out":
        return 1.0 - (1.0 - t) * (1.0 - t)
    if curve == "ease-in-out":
        return t * t * (3.0 - 2.0 * t)
    return t


def _shot_progress(shot: dict[str, Any], frame_number: int) -> float:
    start = int(shot.get("start", frame_number))
    end = int(shot.get("end", start))
    if end <= start:
        return 1.0
    return _clamp((int(frame_number) - start) / float(end - start))


def resolve_shot(timeline: dict[str, Any], frame_number: int) -> dict[str, Any] | None:
    for shot in timeline.get("shots", []):
        if int(shot.get("start", 0)) <= frame_number <= int(shot.get("end", -1)):
            return shot
    return None


def resolve_frame_plan(timeline: dict[str, Any], frame_number: int) -> dict[str, Any]:
    shot = resolve_shot(timeline, frame_number)
    if not shot:
        return {"style": "Video Fidelity · RTX 3060", "intensity": 0.50, "shot": 0}
    p = _ease(_shot_progress(shot, frame_number), str(shot.get("curve") or "linear"))
    start = _clamp(float(shot.get("intensity_start", shot.get("intensity", 0.60))))
    end = _clamp(float(shot.get("intensity_end", shot.get("intensity", 0.60))))
    return {
        "style": str(shot.get("style") or "Video Fidelity · RTX 3060"),
        "intensity": _lerp(start, end, p),
        "shot": int(shot.get("id", 0)),
        "start": int(shot.get("start", frame_number)),
        "end": int(shot.get("end", frame_number)),
    }


def frame_plan_signature(timeline: dict[str, Any], frame_number: int) -> str:
    plan = resolve_frame_plan(timeline, frame_number)
    compact = {
        "style": plan["style"],
        "intensity": round(float(plan["intensity"]), 6),
    }
    return hashlib.sha256(json.dumps(compact, sort_keys=True).encode("utf-8")).hexdigest()


def timeline_hash(timeline: dict[str, Any]) -> str:
    payload = json.dumps(timeline, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _set_shot(shot: dict[str, Any], style: str, start: float, end: float, curve: str = "ease-in-out") -> None:
    shot["style"] = style
    shot["intensity_start"] = round(_clamp(start), 4)
    shot["intensity_end"] = round(_clamp(end), 4)
    shot["curve"] = curve


def apply_treatment(timeline: dict[str, Any], treatment: str) -> dict[str, Any]:
    shots = timeline.get("shots", [])
    n = max(1, len(shots))
    timeline["treatment"] = treatment

    for index, shot in enumerate(shots):
        progress = index / max(1, n - 1)
        if treatment == "Clean Comic":
            _set_shot(shot, "Clean Graphic Novel", 0.48, 0.58)
        elif treatment == "Dark Video Essay":
            style = "Neo-Noir" if index % 3 != 2 else "Clean Graphic Novel"
            _set_shot(shot, style, 0.48, 0.66)
        elif treatment == "Product Promo":
            style = "Corporate Propaganda" if index % 4 != 3 else "Graphic Shock · maximum print"
            _set_shot(shot, style, 0.52, 0.72 if style.startswith("Corporate") else 0.86)
        elif treatment == "Keep It Stable":
            _set_shot(shot, "Video Fidelity · RTX 3060", 0.34, 0.42)
        elif treatment == "Reality Break":
            if n >= 4 and index == n - 1:
                _set_shot(shot, ORIGINAL, 0.0, 0.0, "linear")
            elif 0.38 <= progress <= 0.72:
                _set_shot(shot, "Dream Collapse", 0.45, 0.84)
            else:
                _set_shot(shot, "Clean Graphic Novel", 0.36, 0.52)
        else:  # Clean → Chaos
            if n >= 4 and index == n - 1:
                _set_shot(shot, ORIGINAL, 0.0, 0.0, "linear")
            elif progress < 0.30:
                _set_shot(shot, "Clean Graphic Novel", 0.24, 0.42)
            elif progress < 0.62:
                _set_shot(shot, "Comic Punch · strong", 0.40, 0.68)
            elif progress < 0.86:
                _set_shot(shot, "Dream Collapse", 0.58, 0.90)
            else:
                _set_shot(shot, "Signal Rupture", 0.78, 1.00)
    return timeline


class EasyShotDirectorMixin:
    """Shot-aware render orchestration with a deliberately simple default UX."""

    def _build_ui(self):
        self.director_easy_var = tk.BooleanVar(value=True)
        self.director_treatment_var = tk.StringVar(value="Clean → Chaos")
        self.director_shot_var = tk.StringVar(value="")
        self.director_look_var = tk.StringVar(value="Comic")
        self.director_intensity_var = tk.StringVar(value="Medium")
        self.director_direction_var = tk.StringVar(value="Stay")
        self.director_summary_var = tk.StringVar(value="No shot plan yet · Analyze Shots to begin")
        self._director_timeline: dict[str, Any] = {}
        self._director_hidden_panels: list[Any] = []
        self._director_render_card = None
        self._director_preview_mode = False
        super()._build_ui()
        self._build_easy_director_card()
        self._load_director_timeline(silent=True)
        self.after(0, self._apply_easy_mode_visibility)

    # ---------- Easy UI ----------

    def _label_frame_title(self, widget) -> str:
        try:
            return str(widget.cget("text") or "")
        except Exception:
            return ""

    def _build_easy_director_card(self) -> None:
        children = list(self.left.winfo_children())
        render_card = next((w for w in children if self._label_frame_title(w).startswith("5 · Render")), None)
        self._director_render_card = render_card

        card = self._panel(self.left, "3 · Easy Shot Director · v2.2")
        if render_card is not None:
            card.pack(fill="x", pady=8, before=render_card)
        else:
            card.pack(fill="x", pady=8)
        self.director_card = card

        intro = ttk.Frame(card, style="Panel.TFrame")
        intro.pack(fill="x")
        ttk.Label(
            intro,
            text="Simple mode: analyze the cuts, pick a treatment, preview it, render it.",
            style="Panel.TLabel",
        ).pack(side="left")
        ttk.Checkbutton(
            intro,
            text="Show advanced controls",
            variable=self.director_easy_var,
            command=self._director_toggle_clicked,
        ).pack(side="right")
        # The variable reads True as Easy Mode. Reverse the checkbutton's visible
        # semantics with a command so the normal state stays simple.
        self.director_easy_var.set(True)

        row = ttk.Frame(card, style="Panel.TFrame")
        row.pack(fill="x", pady=(10, 4))
        ttk.Button(row, text="1  Analyze Shots", style="Accent.TButton", command=self._director_analyze_clicked).pack(side="left")
        ttk.Label(row, text="Treatment", style="Panel.TLabel").pack(side="left", padx=(14, 4))
        ttk.Combobox(
            row,
            textvariable=self.director_treatment_var,
            values=TREATMENTS,
            state="readonly",
            width=22,
        ).pack(side="left")
        ttk.Button(row, text="2  Apply Treatment", command=self._director_apply_treatment_clicked).pack(side="left", padx=5)

        ttk.Label(card, textvariable=self.director_summary_var, style="Muted.TLabel").pack(anchor="w", pady=(2, 8))

        edit = ttk.LabelFrame(card, text="Optional · tweak one shot", padding=8)
        edit.pack(fill="x")
        er = ttk.Frame(edit, style="Panel.TFrame")
        er.pack(fill="x")
        ttk.Label(er, text="Shot", style="Panel.TLabel").pack(side="left")
        self.director_shot_combo = ttk.Combobox(er, textvariable=self.director_shot_var, state="readonly", width=18)
        self.director_shot_combo.pack(side="left", padx=4)
        self.director_shot_combo.bind("<<ComboboxSelected>>", lambda _e: self._director_load_selected_shot())
        ttk.Label(er, text="Look", style="Panel.TLabel").pack(side="left", padx=(10, 3))
        ttk.Combobox(er, textvariable=self.director_look_var, values=list(LOOKS.keys()), state="readonly", width=19).pack(side="left")
        ttk.Label(er, text="Intensity", style="Panel.TLabel").pack(side="left", padx=(10, 3))
        ttk.Combobox(er, textvariable=self.director_intensity_var, values=list(INTENSITY_LEVELS.keys()), state="readonly", width=10).pack(side="left")
        ttk.Label(er, text="Motion", style="Panel.TLabel").pack(side="left", padx=(10, 3))
        ttk.Combobox(er, textvariable=self.director_direction_var, values=DIRECTIONS, state="readonly", width=9).pack(side="left")
        ttk.Button(er, text="Apply to Shot", command=self._director_apply_selected_shot).pack(side="left", padx=(10, 0))

        actions = ttk.Frame(card, style="Panel.TFrame")
        actions.pack(fill="x", pady=(10, 0))
        ttk.Button(actions, text="3  Preview Project", style="Accent.TButton", command=self._director_preview_clicked).pack(side="left")
        ttk.Button(actions, text="4  RENDER VIDEO", style="Accent.TButton", command=self._director_render_clicked).pack(side="left", padx=6)
        ttk.Button(actions, text="STOP", style="Danger.TButton", command=self._stop_clicked).pack(side="right")
        ttk.Progressbar(card, variable=self.progress, maximum=100).pack(fill="x", pady=(10, 3))
        ttk.Label(card, textvariable=self.progress_label_var, style="Muted.TLabel").pack(anchor="w")
        ttk.Label(
            card,
            text=(
                "Low/Medium/High/Insane drive the underlying denoise, print FX, ControlNet pressure, temporal stability and Shot Memory together. "
                "Original Footage bypasses diffusion for that shot."
            ),
            style="Muted.TLabel",
            wraplength=760,
        ).pack(anchor="w", pady=(6, 0))

    def _director_toggle_clicked(self) -> None:
        # Clicking the checkbutton toggles the underlying Easy Mode boolean. The
        # label asks to show advanced controls, so false means advanced is shown.
        self._apply_easy_mode_visibility()

    def _apply_easy_mode_visibility(self) -> None:
        easy = bool(self.director_easy_var.get())
        candidates = []
        for child in self.left.winfo_children():
            if child is getattr(self, "director_card", None):
                continue
            title = self._label_frame_title(child)
            if title.startswith(("2B", "3B", "3 · Look", "4 ·", "4B", "4C", "5 · Render")):
                candidates.append(child)
        self._director_hidden_panels = candidates

        if easy:
            for widget in candidates:
                try:
                    widget.pack_forget()
                except Exception:
                    pass
        else:
            # Restore technical panels before the Director card so the simple
            # controls remain adjacent to the render actions at the bottom.
            for widget in candidates:
                try:
                    if not widget.winfo_manager():
                        widget.pack(fill="x", pady=8, before=self.director_card)
                except Exception:
                    pass

    # ---------- Timeline storage ----------

    def _timeline_path(self) -> Path:
        return self.project_paths()["root"] / "comicframe_timeline.json"

    def _rendered_timeline_path(self) -> Path:
        return self.project_paths()["root"] / "comicframe_timeline.rendered.json"

    def _load_director_timeline(self, silent: bool = False) -> dict[str, Any]:
        path = self._timeline_path()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and isinstance(data.get("shots"), list):
                    self._director_timeline = data
                    self.after(0, self._refresh_director_ui)
                    return data
            except Exception as exc:
                if not silent:
                    self._log(f"Shot Director timeline ignored: {exc}")
        self._director_timeline = {}
        return self._director_timeline

    def _save_director_timeline(self) -> None:
        path = self._timeline_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._director_timeline["version"] = "2.2"
        path.write_text(json.dumps(self._director_timeline, indent=2), encoding="utf-8")
        self.after(0, self._refresh_director_ui)

    def _refresh_director_ui(self) -> None:
        shots = self._director_timeline.get("shots", [])
        fps = float(self._director_timeline.get("fps") or 30.0)
        values = []
        for shot in shots:
            start, end = int(shot["start"]), int(shot["end"])
            values.append(f"{int(shot['id']):02d} · {start / fps:.1f}s–{end / fps:.1f}s")
        self.director_shot_combo["values"] = values
        if values and self.director_shot_var.get() not in values:
            self.director_shot_var.set(values[0])
            self._director_load_selected_shot()
        treatment = str(self._director_timeline.get("treatment") or self.director_treatment_var.get())
        if treatment in TREATMENTS:
            self.director_treatment_var.set(treatment)
        if shots:
            self.director_summary_var.set(
                f"{len(shots)} shot(s) · {treatment} · plan saved to comicframe_timeline.json"
            )
        else:
            self.director_summary_var.set("No shot plan yet · Analyze Shots to begin")

    def _selected_shot(self) -> dict[str, Any] | None:
        value = self.director_shot_var.get().strip()
        match = re.match(r"(\d+)", value)
        if not match:
            return None
        target = int(match.group(1))
        return next((s for s in self._director_timeline.get("shots", []) if int(s.get("id", 0)) == target), None)

    def _director_load_selected_shot(self) -> None:
        shot = self._selected_shot()
        if not shot:
            return
        style = str(shot.get("style") or "Comic Punch · strong")
        self.director_look_var.set(STYLE_TO_LOOK.get(style, "Comic"))
        peak = max(float(shot.get("intensity_start", 0.6)), float(shot.get("intensity_end", 0.6)))
        nearest = min(INTENSITY_LEVELS, key=lambda name: abs(INTENSITY_LEVELS[name] - peak))
        self.director_intensity_var.set(nearest)
        a = float(shot.get("intensity_start", peak))
        b = float(shot.get("intensity_end", peak))
        self.director_direction_var.set("Build" if b > a + 0.04 else "Fade" if a > b + 0.04 else "Stay")

    # ---------- Shot detection ----------

    @staticmethod
    def _proxy_gray(path: Path, long_edge: int = 320):
        cv2, np = flow.cv2, flow.np
        with Image.open(path) as image:
            rgb = np.asarray(image.convert("RGB"))
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        h, w = gray.shape[:2]
        longest = max(h, w)
        if longest > long_edge:
            scale = long_edge / float(longest)
            gray = cv2.resize(gray, (max(1, round(w * scale)), max(1, round(h * scale))), interpolation=cv2.INTER_AREA)
        return gray

    def _detect_shot_boundaries(self, frames: list[Path]) -> list[int]:
        if len(frames) < 2 or flow.cv2 is None or flow.np is None:
            return [1]
        cv2 = flow.cv2
        cut_threshold = max(0.12, min(0.50, float(getattr(self, "temporal_cut_var").get()) * 0.82))
        boundaries = [1]
        previous = self._proxy_gray(frames[0])
        min_gap = 6
        for index, path in enumerate(frames[1:], start=2):
            current = self._proxy_gray(path)
            if previous.shape != current.shape:
                previous = cv2.resize(previous, (current.shape[1], current.shape[0]), interpolation=cv2.INTER_AREA)
            diff = cv2.absdiff(previous, current)
            mean_change = float(diff.mean()) / 255.0
            h1 = cv2.calcHist([previous], [0], None, [32], [0, 256])
            h2 = cv2.calcHist([current], [0], None, [32], [0, 256])
            cv2.normalize(h1, h1)
            cv2.normalize(h2, h2)
            corr = float(cv2.compareHist(h1, h2, cv2.HISTCMP_CORREL))
            if mean_change >= cut_threshold and corr < 0.62 and index - boundaries[-1] >= min_gap:
                boundaries.append(index)
            previous = current
        return boundaries

    def _analyze_shots(self) -> dict[str, Any]:
        info = self._extract_frames()
        paths = self.project_paths()
        frames = sorted(paths["frames"].glob("frame_*.png"))
        if not frames:
            raise RuntimeError("No source frames exist after extraction.")
        self._set_progress(8, "Analyzing shot boundaries…")
        boundaries = self._detect_shot_boundaries(frames)
        shots: list[dict[str, Any]] = []
        total = len(frames)
        for idx, start in enumerate(boundaries):
            end = boundaries[idx + 1] - 1 if idx + 1 < len(boundaries) else total
            shots.append({
                "id": idx + 1,
                "start": int(start),
                "end": int(end),
                "style": "Clean Graphic Novel",
                "intensity_start": 0.45,
                "intensity_end": 0.55,
                "curve": "ease-in-out",
            })
        self._director_timeline = {
            "version": "2.2",
            "fps": float(info.get("fps") or 30.0),
            "total_frames": total,
            "source_width": int(info.get("width") or 0),
            "source_height": int(info.get("height") or 0),
            "treatment": self.director_treatment_var.get(),
            "shots": shots,
        }
        apply_treatment(self._director_timeline, self.director_treatment_var.get())
        self._save_director_timeline()
        self._log(f"Shot Director: detected {len(shots)} shot(s) across {total} frames.")
        self._set_progress(100, f"Shot analysis complete · {len(shots)} shots")
        return self._director_timeline

    def _director_analyze_clicked(self) -> None:
        self._run_worker(self._analyze_shots)

    def _director_apply_treatment_clicked(self) -> None:
        if not self._director_timeline.get("shots"):
            self._run_worker(self._analyze_shots)
            return
        apply_treatment(self._director_timeline, self.director_treatment_var.get())
        self._save_director_timeline()
        self._log(f"Shot Director treatment applied: {self.director_treatment_var.get()}")

    def _director_apply_selected_shot(self) -> None:
        shot = self._selected_shot()
        if not shot:
            return
        style = LOOKS.get(self.director_look_var.get(), "Comic Punch · strong")
        level = INTENSITY_LEVELS.get(self.director_intensity_var.get(), 0.60)
        direction = self.director_direction_var.get()
        if style == ORIGINAL:
            start = end = 0.0
            curve = "linear"
        elif direction == "Build":
            start, end, curve = max(0.10, level * 0.35), level, "ease-in-out"
        elif direction == "Fade":
            start, end, curve = level, max(0.10, level * 0.35), "ease-in-out"
        else:
            start = end = level
            curve = "linear"
        _set_shot(shot, style, start, end, curve)
        self._save_director_timeline()
        self._log(
            f"Shot Director: shot {shot['id']} -> {self.director_look_var.get()} · "
            f"{self.director_intensity_var.get()} · {direction}"
        )

    # ---------- Per-frame direction ----------

    def _ensure_director_timeline(self) -> dict[str, Any]:
        if not self._director_timeline.get("shots"):
            self._load_director_timeline(silent=True)
        if not self._director_timeline.get("shots"):
            return self._analyze_shots()
        return self._director_timeline

    def _director_style_pack(self, style_name: str) -> StylePack:
        pack = STYLE_PACKS.get(style_name)
        if pack is None:
            pack = STYLE_PACKS["Video Fidelity · RTX 3060"]
        return pack

    @staticmethod
    def _capture_var(obj, name: str):
        var = getattr(obj, name, None)
        if var is not None and hasattr(var, "get") and hasattr(var, "set"):
            return var, var.get()
        return None

    def _apply_frame_direction(self, style_name: str, intensity: float, settings):
        pack = self._director_style_pack(style_name)
        t = _clamp(intensity)
        saved = {}
        for name in (
            "preset_var", "fx_enabled_var", "fx_intensity_var", "fx_ink_var", "fx_posterize_var",
            "fx_halftone_var", "fx_misregister_var", "fx_grain_var", "control_weight_var",
            "control_guidance_end_var", "temporal_enabled_var", "temporal_strength_var",
            "temporal_motion_var", "temporal_cut_var", "shot_memory_enabled_var",
            "shot_memory_strength_var", "shot_palette_strength_var",
        ):
            captured = self._capture_var(self, name)
            if captured:
                saved[name] = captured

        # Human intensity is intentionally a meta-control. Low intensity preserves
        # structure and source pixels; high intensity progressively hands more room
        # to the selected StylePack.
        self.preset_var.set(style_name)
        self.fx_enabled_var.set(pack.fx > 0 and t > 0.02)
        self.fx_intensity_var.set(pack.fx * t)
        self.fx_ink_var.set(pack.fx_ink)
        self.fx_posterize_var.set(pack.fx_posterize)
        self.fx_halftone_var.set(pack.fx_halftone)
        self.fx_misregister_var.set(pack.fx_misregister)
        self.fx_grain_var.set(pack.fx_grain)
        self.control_weight_var.set(_lerp(1.06, pack.control_weight, t))
        self.control_guidance_end_var.set(_lerp(0.98, pack.guidance_end, t))
        self.temporal_enabled_var.set(True)
        self.temporal_strength_var.set(_lerp(0.48, pack.temporal_strength, t))
        self.temporal_motion_var.set(pack.temporal_motion)
        self.temporal_cut_var.set(pack.temporal_cut)
        self.shot_memory_enabled_var.set(True)
        self.shot_memory_strength_var.set(_lerp(0.28, 0.18, t))
        self.shot_palette_strength_var.set(_lerp(0.08, 0.14, t))

        lora_tokens = re.findall(r"<lora:[^>]+>", str(settings.prompt or ""))
        prompt = pack.prompt
        if lora_tokens:
            prompt = ", ".join(lora_tokens) + ", " + prompt
        directed_settings = replace(
            settings,
            prompt=prompt,
            negative_prompt=pack.negative,
            denoise=_lerp(0.18, pack.denoise, 0.40 + 0.60 * t),
            cfg_scale=_lerp(4.8, pack.cfg, t),
            steps=max(18, int(round(_lerp(20, pack.steps, t)))),
            controlnet_weight=float(self.control_weight_var.get()),
        )
        return directed_settings, saved

    @staticmethod
    def _restore_vars(saved: dict[str, tuple[Any, Any]]) -> None:
        for _name, (var, value) in saved.items():
            try:
                var.set(value)
            except Exception:
                pass

    def _blend_source_intensity(self, frame_path: Path, out_path: Path, intensity: float) -> None:
        t = _clamp(intensity)
        if t >= 0.995:
            return
        with Image.open(out_path) as styled, Image.open(frame_path) as source:
            styled_rgb = styled.convert("RGB")
            source_rgb = source.convert("RGB").resize(styled_rgb.size, Image.Resampling.LANCZOS)
            final = Image.blend(source_rgb, styled_rgb, t)
            final.save(out_path, format="PNG", optimize=False)

    def _write_original_frame(self, frame_path: Path, out_path: Path, width: int, height: int) -> None:
        target_width, target_height = self._target_dimensions(width, height)
        with Image.open(frame_path) as source:
            image = source.convert("RGB")
            if image.size != (target_width, target_height):
                image = image.resize((target_width, target_height), Image.Resampling.LANCZOS)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            image.save(out_path, format="PNG", optimize=False)

    def _render_one(self, frame_path, out_path, settings, width, height, frame_number):
        timeline = self._director_timeline if self._director_timeline.get("shots") else self._load_director_timeline(silent=True)
        if not timeline.get("shots"):
            return super()._render_one(frame_path, out_path, settings, width, height, frame_number)

        plan = resolve_frame_plan(timeline, int(frame_number))
        style_name = str(plan["style"])
        intensity = float(plan["intensity"])
        if style_name == ORIGINAL:
            self._write_original_frame(Path(frame_path), Path(out_path), width, height)
            self._log(f"Shot Director: frame {frame_number} uses original footage")
            return None

        directed_settings, saved = self._apply_frame_direction(style_name, intensity, settings)
        try:
            result = super()._render_one(frame_path, out_path, directed_settings, width, height, frame_number)
            self._blend_source_intensity(Path(frame_path), Path(out_path), intensity)
            return result
        finally:
            self._restore_vars(saved)

    # ---------- Preview ----------

    def _director_preflight(self) -> None:
        if self.seed_mode_var.get() != "fixed":
            self.seed_mode_var.set("fixed")
        if bool(getattr(self, "control_required_var").get()):
            if not getattr(self, "_controlnet_available", False):
                self._detect_controlnet()
            if not getattr(self, "_controlnet_available", False):
                raise RuntimeError("ControlNet is required for preview but no usable model was detected. Sync WebUI and retry.")
            self.control_enabled_var.set(True)
            self._select_controlnet_defaults()
            self._validate_controlnet_family()
        self._probe_gpu_memory()
        self._ensure_checkpoint_loaded()

    @staticmethod
    def _representative_shots(shots: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
        if len(shots) <= limit:
            return shots
        indexes = sorted({round(i * (len(shots) - 1) / (limit - 1)) for i in range(limit)})
        return [shots[i] for i in indexes]

    def _make_director_contact_sheet(self, rendered: list[tuple[Path, str]]) -> Path:
        thumb_w, thumb_h = 360, 220
        cols = 2
        rows = max(1, math.ceil(len(rendered) / cols))
        sheet = Image.new("RGB", (cols * thumb_w, rows * (thumb_h + 34)), (18, 19, 24))
        draw = ImageDraw.Draw(sheet)
        for idx, (path, label) in enumerate(rendered):
            x = (idx % cols) * thumb_w
            y = (idx // cols) * (thumb_h + 34)
            with Image.open(path) as source:
                image = ImageOps.contain(source.convert("RGB"), (thumb_w, thumb_h), Image.Resampling.LANCZOS)
            px = x + (thumb_w - image.width) // 2
            py = y + (thumb_h - image.height) // 2
            sheet.paste(image, (px, py))
            draw.text((x + 8, y + thumb_h + 8), label[:54], fill=(238, 241, 247))
        target = self.project_paths()["root"] / "DIRECTOR_PREVIEW.jpg"
        target.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(target, format="JPEG", quality=92)
        return target

    def _preview_director_plan(self) -> None:
        timeline = self._ensure_director_timeline()
        info = self._extract_frames()
        self._director_preflight()
        frames_dir = self.project_paths()["frames"]
        preview_dir = self.project_paths()["root"] / "director_preview_frames"
        if preview_dir.exists():
            shutil.rmtree(preview_dir)
        preview_dir.mkdir(parents=True, exist_ok=True)
        shots = self._representative_shots(list(timeline.get("shots", [])))
        settings = self._settings()
        rendered: list[tuple[Path, str]] = []
        self._director_preview_mode = True
        try:
            for idx, shot in enumerate(shots, 1):
                if self.stop_event.is_set():
                    break
                frame_number = (int(shot["start"]) + int(shot["end"])) // 2
                frame = frames_dir / f"frame_{frame_number:06d}.png"
                out = preview_dir / f"shot_{int(shot['id']):04d}.png"
                self._log(f"Director preview [{idx}/{len(shots)}] shot {shot['id']} frame {frame_number}")
                self._render_one(frame, out, settings, int(info["width"]), int(info["height"]), frame_number)
                plan = resolve_frame_plan(timeline, frame_number)
                look = STYLE_TO_LOOK.get(str(plan["style"]), str(plan["style"]))
                rendered.append((out, f"Shot {shot['id']} · {look} · {float(plan['intensity']):.0%}"))
                self._set_progress(10 + (idx / max(1, len(shots))) * 80, f"Preview {idx}/{len(shots)}")
        finally:
            self._director_preview_mode = False
        if not rendered:
            raise RuntimeError("No preview frames were rendered.")
        sheet = self._make_director_contact_sheet(rendered)
        self.after(0, lambda p=sheet: self._show_image(p, self.output_preview, "output"))
        self.after(0, lambda: self.output_preview_status.set("Shot Director contact sheet"))
        self._set_progress(100, f"Preview ready · {sheet.name}")
        self._log(f"Shot Director preview: {sheet}")

    def _director_preview_clicked(self) -> None:
        self._run_worker(self._preview_director_plan)

    def _director_render_clicked(self) -> None:
        if not self.video_var.get().strip():
            messagebox.showwarning("ComicFrame Studio", "Choose a source video first.")
            return
        if not messagebox.askyesno(
            "ComicFrame Studio",
            "Render the full video using the Shot Director plan?\n\nUnchanged completed shots will be reused when possible.",
        ):
            return
        def job():
            try:
                self._ensure_director_timeline()
                self._render_range(1, None, False)
            except Exception as exc:
                self._log(f"ERROR: {exc}")
                self._set_progress(0, "Full render failed")
        self._run_worker(job)

    # ---------- Shot-aware resume / invalidation ----------

    @staticmethod
    def _profile_without_director(profile: dict[str, Any]) -> dict[str, Any]:
        copy = json.loads(json.dumps(profile))
        copy.pop("shot_director", None)
        return copy

    def _invalidate_changed_timeline_frames(self, old: dict[str, Any], new: dict[str, Any]) -> int:
        total = max(int(old.get("total_frames") or 0), int(new.get("total_frames") or 0))
        styled = self.project_paths()["styled"]
        changed = 0
        for frame_number in range(1, total + 1):
            if frame_plan_signature(old, frame_number) == frame_plan_signature(new, frame_number):
                continue
            candidate = styled / f"frame_{frame_number:06d}.png"
            if candidate.exists():
                candidate.unlink()
                changed += 1
        # Anchors encode style history. Rebuild them when any directed frame changes,
        # while leaving unaffected final rendered PNGs available for resume skipping.
        if changed:
            memory_root = self.project_paths()["root"] / "shot_memory" / "full"
            if memory_root.exists():
                shutil.rmtree(memory_root)
        return changed

    def _prepare_resume_state(self, start, count, test_only):
        timeline = self._ensure_director_timeline()
        paths = self.project_paths()
        paths["root"].mkdir(parents=True, exist_ok=True)
        paths["test"].mkdir(parents=True, exist_ok=True)
        paths["styled"].mkdir(parents=True, exist_ok=True)
        profile = self._render_profile()
        profile_path = paths["root"] / "comicframe_profile.json"

        if test_only:
            if count is not None:
                for frame_number in range(start, start + count):
                    candidate = paths["test"] / f"frame_{frame_number:06d}.png"
                    if candidate.exists():
                        candidate.unlink()
            (paths["root"] / "comicframe_test_profile.json").write_text(json.dumps(profile, indent=2), encoding="utf-8")
            return

        existing = sorted(paths["styled"].glob("frame_*.png"))
        rendered_timeline_path = self._rendered_timeline_path()
        if existing:
            if not profile_path.exists() or not rendered_timeline_path.exists():
                raise RuntimeError(
                    "Existing styled frames predate Shot Director resume tracking. Use a new project directory or clear styled_frames once."
                )
            old_profile = json.loads(profile_path.read_text(encoding="utf-8"))
            if self._profile_without_director(old_profile) != self._profile_without_director(profile):
                raise RuntimeError(
                    "A non-timeline render setting changed (checkpoint, inference, sampler, ControlNet, etc.). "
                    "Restore the old setting, use a new project, or clear styled_frames."
                )
            old_timeline = json.loads(rendered_timeline_path.read_text(encoding="utf-8"))
            if timeline_hash(old_timeline) != timeline_hash(timeline):
                invalidated = self._invalidate_changed_timeline_frames(old_timeline, timeline)
                self._log(
                    f"Shot Director resume: timeline changed; invalidated {invalidated} rendered frame(s). "
                    "Unchanged frames remain cached."
                )

        profile_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
        rendered_timeline_path.write_text(json.dumps(timeline, indent=2), encoding="utf-8")

    def _render_profile(self) -> dict:
        profile = super()._render_profile()
        timeline = self._director_timeline if self._director_timeline.get("shots") else self._load_director_timeline(silent=True)
        profile["shot_director"] = {
            "enabled": True,
            "timeline_hash": timeline_hash(timeline) if timeline else "",
            "treatment": str(timeline.get("treatment") or "") if timeline else "",
            "shots": len(timeline.get("shots", [])) if timeline else 0,
            "intensity_model": "style-aware meta-control + source blend",
            "resume": "per-frame timeline signature invalidation",
        }
        return profile

    def _render_range(self, start, count, test_only):
        self._ensure_director_timeline()
        self._log(
            f"Shot Director v2.2: {len(self._director_timeline.get('shots', []))} shot(s) · "
            f"{self._director_timeline.get('treatment', 'custom')}"
        )
        return super()._render_range(start, count, test_only)
