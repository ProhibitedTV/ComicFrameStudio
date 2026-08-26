#!/usr/bin/env python3
"""Canonical ComicFrame Studio product shell.

Public contract: video -> look -> ControlNet/steps -> process -> result.
The mature renderer stays below comicframe_simple; this module owns only the
small operator surface and the public redraw policy.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import tkinter as tk
from tkinter import ttk

import comicframe_artistic as artistic
import comicframe_simple as simple
import comicframe_styles as styles
from comicframe_style_library import STYLE_LIBRARY_VERSION, register_style_library

register_style_library()

PRODUCT_VERSION = "3.5"
MIN_STEPS, MAX_STEPS, DEFAULT_STEPS = 12, 36, 24
DEFAULT_PROCESS = "Graphic Shock · maximum print"
LIVE_PREVIEW_EVERY = 5
RUNTIME_TRANSFORM_SUFFIX = (
    ", radical visual reinterpretation through the selected medium, redraw photographic surfaces as authored illustration, "
    "strong material transformation, bold environmental restyling, break literal photo texture, preserve recognizable subject identity, "
    "main action and broad composition rather than slavishly copying every source edge"
)


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def preferences_path(home: Path | None = None) -> Path:
    if home is not None:
        return Path(home) / ".comicframe_studio" / "preferences.json"
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "ComicFrameStudio" / "preferences.json"
    return Path.home() / ".comicframe_studio" / "preferences.json"


def normalize_preferences(data: Any, catalog: list[str] | None = None) -> dict[str, Any]:
    allowed = list(catalog if catalog is not None else simple.simple_process_catalog())
    raw = data if isinstance(data, dict) else {}
    style = str(raw.get("style") or DEFAULT_PROCESS)
    if style not in allowed:
        style = DEFAULT_PROCESS if DEFAULT_PROCESS in allowed else (allowed[0] if allowed else "")
    try:
        steps = int(round(float(raw.get("steps", DEFAULT_STEPS))))
    except Exception:
        steps = DEFAULT_STEPS
    return {
        "style": style,
        "controlnet": bool(raw.get("controlnet", True)),
        "steps": max(MIN_STEPS, min(MAX_STEPS, steps)),
    }


def load_preferences(path: Path | None = None) -> dict[str, Any]:
    target = Path(path) if path is not None else preferences_path()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    return normalize_preferences(data)


def save_preferences(data: dict[str, Any], path: Path | None = None) -> Path:
    target = Path(path) if path is not None else preferences_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(json.dumps(normalize_preferences(data), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, target)
    return target


def filter_processes(query: str) -> list[str]:
    needle = " ".join(str(query or "").lower().split())
    values = simple.simple_process_catalog()
    if not needle:
        return values
    found: list[str] = []
    for name in values:
        category = artistic.STYLE_CATEGORIES.get(name, "Sequence" if name in simple.SEQUENCE_PROCESSES else "Style")
        stability = artistic.STYLE_STABILITY.get(name, "shot progression" if name in simple.SEQUENCE_PROCESSES else "Medium")
        haystack = f"{name} {category} {stability} {simple.process_description(name)}".lower()
        if all(part in haystack for part in needle.split()):
            found.append(name)
    return found


def primary_action_state(video_text: str, busy: bool) -> tuple[str, str]:
    if busy:
        return "PROCESSING…", "disabled"
    text = str(video_text or "").strip()
    if not text:
        return "CHOOSE A VIDEO FIRST", "disabled"
    if not Path(text).expanduser().exists():
        return "SOURCE MISSING", "disabled"
    return "PROCESS VIDEO", "normal"


def aggressive_render_parameters(style_name: str, controlnet_enabled: bool) -> dict[str, float | bool]:
    pack = styles.STYLE_PACKS.get(style_name)
    if pack is None:
        return {
            "controlnet_enabled": bool(controlnet_enabled), "denoise": .68,
            "control_weight": .40 if controlnet_enabled else 0.0,
            "guidance_end": .56 if controlnet_enabled else 0.0,
            "fx": .96, "temporal_strength": .18,
        }
    stability = str(artistic.STYLE_STABILITY.get(style_name, "Medium"))
    if stability == "Experimental":
        denoise_boost, control_factor, guidance_cap, fx_boost, temporal_factor = .18, .36, .56, .10, .64
    elif stability == "High":
        denoise_boost, control_factor, guidance_cap, fx_boost, temporal_factor = .10, .64, .76, .06, .84
    else:
        denoise_boost, control_factor, guidance_cap, fx_boost, temporal_factor = .15, .48, .66, .09, .74
    return {
        "controlnet_enabled": bool(controlnet_enabled),
        "denoise": clamp(max(pack.denoise * 1.18, pack.denoise + denoise_boost), .30, .78),
        "control_weight": clamp(pack.control_weight * control_factor, .18, .72) if controlnet_enabled else 0.0,
        "guidance_end": min(float(pack.guidance_end), guidance_cap) if controlnet_enabled else 0.0,
        "fx": clamp(pack.fx + fx_boost),
        "temporal_strength": clamp(pack.temporal_strength * temporal_factor, .10, .42),
    }


class ComicFrameStudioApp(simple.ComicFrameStudioApp):
    """One product layer over the mature simple-flow engine."""

    def __init__(self):
        self._product_preferences_path = preferences_path()
        self._product_preferences = load_preferences(self._product_preferences_path)
        self._product_preference_job = None
        self._presence_started_at: float | None = None
        self._presence_tick_job = None
        self._presence_last_preview_frame: int | None = None
        super().__init__()
        self.title("ComicFrame Studio 3.5")
        self._update_primary_action()

    def _install_simple_shell(self) -> None:
        super()._install_simple_shell()
        prefs = self._product_preferences
        catalog = simple.simple_process_catalog()
        chosen = prefs["style"] if prefs["style"] in catalog else DEFAULT_PROCESS
        self.simple_process_var.set(chosen)
        self.simple_process_info_var.set(simple.process_description(chosen))

         process_row = self.simple_process_combo.master
        process_panel = process_row.master
        search_row = ttk.Frame(process_panel, style="Panel.TFrame")
        search_row.pack(fill="x", pady=(0, 9), before=process_row)
        ttk.Label(search_row, text="FIND LOOK", style="Muted.TLabel").pack(side="left")
        self.simple_filter_var = tk.StringVar(value="")
        self.simple_filter_entry = ttk.Entry(search_row, textvariable=self.simple_filter_var)
        self.simple_filter_entry.pack(side="left", fill="x", expand=True, padx=(9, 0))
        self.simple_filter_var.trace_add("write", self._filter_changed)
        self.simple_process_combo.configure(values=catalog)

        action = self.simple_process_button.master
        shell = action.master
        controls = ttk.Frame(shell)
        controls.pack(fill="x", pady=(14, 0), before=action)
        self.simple_controlnet_var = tk.BooleanVar(value=bool(prefs["controlnet"]))
        self.simple_steps_var = tk.IntVar(value=int(prefs["steps"]))
        self.simple_steps_text_var = tk.StringVar(value=f"{int(prefs['steps'])} steps")
        self.simple_controlnet_toggle = ttk.Checkbutton(
            controls, text="CONTROLNET", variable=self.simple_controlnet_var, command=self._creative_changed,
        )
        self.simple_controlnet_toggle.pack(side="left")
        ttk.Label(controls, text="STEPS", style="Muted.TLabel").pack(side="left", padx=(18, 6))
        self.simple_steps_scale = tk.Scale(
            controls, from_=MIN_STEPS, to=MAX_STEPS, orient="horizontal", variable=self.simple_steps_var,
            command=self._steps_changed, showvalue=False, resolution=1, length=220, highlightthickness=0,
        )
        self.simple_steps_scale.pack(side="left", fill="x", expand=True)
        ttk.Label(controls, textvariable=self.simple_steps_text_var, style="Muted.TLabel", width=9).pack(side="left", padx=(8, 0))
        self.simple_creative_hint = ttk.Label(shell, text="", style="Muted.TLabel")
        self.simple_creative_hint.pack(fill="x", pady=(5, 0), before=action)

        result_actions = self.simple_save_button.master
        self.simple_copy_path_button = ttk.Button(
            result_actions, text="COPY PATH", command=self._simple_copy_result_path, state="disabled",
        )
        self.simple_copy_path_button.pack(side="left", padx=(8, 0))

        self.progress_label_var.trace_add("write", self._presence_progress_changed)
        self.simple_process_var.trace_add("write", self._schedule_preference_save)
        self._creative_changed()
        self._update_primary_action()

    def _filter_changed(self, *_args) -> None:
        matches = filter_processes(self.simple_filter_var.get())
        self.simple_process_combo.configure(values=matches)
        if matches and self.simple_process_var.get() not in matches:
            self.simple_process_var.set(matches[0])
            self.simple_process_info_var.set(simple.process_description(matches[0]))

    def _steps_changed(self, value=None) -> None:
        try:
            steps = int(round(float(value if value is not None else self.simple_steps_var.get())))
        except Exception:
            steps = DEFAULT_STEPS
        steps = max(MIN_STEPS, min(MAX_STEPS, steps))
        self.simple_steps_var.set(steps)
        self.simple_steps_text_var.set(f"{steps} steps")
        self._schedule_preference_save()

    def _creative_changed(self) -> None:
        enabled = bool(self.simple_controlnet_var.get())
        self.simple_creative_hint.configure(
            text=("Loose structural rail ÷ aggressive redraw stays on" if enabled else "UNLEASHED · no ControlNet structure rail")
        )
        self._schedule_preference_save()

    def _schedule_preference_save(self, *_args) -> None:
        if self._product_preference_job is not None:
            try:
                self.after_cancel(self._product_preference_job)
            except Exception:
                pass
        try:
            self._product_preference_job = self.after(250, self._save_preferences_now)
        except Exception:
            pass

    def _save_preferences_now(self) -> None:
        self._product_preference_job = None
        try:
            save_preferences({
                "style": self.simple_process_var.get(),
                "controlnet": bool(self.simple_controlnet_var.get()),
                "steps": int(self.simple_steps_var.get()),
            }, self._product_preferences_path)
        except Exception:
            pass

    def _simple_process_changed(self, _event=None) -> None:
        super()._simple_process_changed(_event)
        self._schedule_preference_save()

    def _simple_choose_video(self) -> None:
        super()._simple_choose_video()
        self._update_primary_action()

    def _update_primary_action(self) -> None:
        text, state = primary_action_state(str(self.video_var.get() or ""), bool(self._simple_busy))
        try:
            self.simple_process_button.configure(text=text, state=state)
        except Exception:
            pass

    def _simple_set_busy(self, busy: bool) -> None:
        super()._simple_set_busy(busy)
        state = "disabled" if busy else "normal"
        for widget in (self.simple_filter_entry, self.simple_controlnet_toggle, self.simple_steps_scale):
            try:
                widget.configure(state=state)
            except Exception:
                pass
        if busy:
            self._presence_started_at = time.monotonic()
            self._presence_last_preview_frame = None
            self._presence_tick_job = self.after(500, self._presence_tick)
        else:
            if self._presence_tick_job is not None:
                try:
                    self.after_cancel(self._presence_tick_job)
                except Exception:
                    pass
            self._presence_tick_job = None
        self._update_primary_action()

    def _presence_tick(self) -> None:
        self._presence_tick_job = None
        if not self._simple_busy:
            return
        elapsed = max(0, int(time.monotonic() - (self._presence_started_at or time.monotonic())))
        mins, secs = divmod(elapsed, 60)
        base = str(self.progress_label_var.get() or "Working").split(" · ")[0]
        self.progress_label_var.set(f"{base} · {mins:02d}:{secs:02d} elapsed")
        self._presence_tick_job = self.after(500, self._presence_tick)

    def _presence_progress_changed(self, *_args) -> None:
        if not self._simple_busy:
            return
        label = str(self.progress_label_var.get() or "")
        match = re.match(r^\s*\d+\s*/\s*\d+\s*:\s*(frame_(\d+)\.png)", label, re.IGNORECASE)
        if not match:
            return
        filename, number_text = match.group(1), match.group(2)
        number = int(number_text)
        if self._presence_last_preview_frame is not None and number - self._presence_last_preview_frame < LIVE_PREVIEW_EVERY:
            return
        try:
            path = Path(self.project_paths()["styled"]) / filename
        except Exception:
            return
        if not path.exists() or path.stat().st_size <= 0:
            return
        self._presence_last_preview_frame = number
        self.after_idle(lambda p=path: self._simple_show_image(p))

    def _simple_set_result_buttons(self, enabled: bool) -> None:
        super()._simple_set_result_buttons(enabled)
        try:
            self.simple_copy_path_button.configure(state="normal" if enabled else "disabled")
        except Exception:
            pass

    def _simple_copy_result_path(self) -> None:
        path = self._simple_valid_output()
        if path is None:
            return
        try:
            self.clipboard_clear()
            self.clipboard_append(str(path))
            self.update_idletasks()
        except Exception:
            pass

    def _enforce_public_controlnet_choice(self) -> None:
        public_var = getattr(self, "simple_controlnet_var", None)
        if public_var is None or not hasattr(public_var, "get"):
            return
        enabled = bool(public_var.get())
        for name in ("control_enabled_var", "control_required_var"):
            target = getattr(self, name, None)
            try:
                if target is not None and hasattr(target, "set"):
                    target.set(enabled)
            except Exception:
                pass

    def _sync_webui(self):
        result = super()._sync_webui()
        self._enforce_public_controlnet_choice()
        return result

    def _select_controlnet_defaults(self):
        result = super()._select_controlnet_defaults()
        self._enforce_public_controlnet_choice()
        return result

    def _simple_apply_hidden_defaults(self) -> None:
        super()._simple_apply_hidden_defaults()
        self._enforce_public_controlnet_choice()

    @staticmethod
    def _remember_variable(saved: dict[str, tuple[Any, Any]], obj: Any, name: str) -> None:
        var = getattr(obj, name, None)
        if var is not None and hasattr(var, "get") and hasattr(var, "set") and name not in saved:
            saved[name] = (var, var.get())

    def _apply_frame_direction(self, style_name: str, intensity: float, settings):
        directed, saved = super()._apply_frame_direction(style_name, intensity, settings)
        enabled = bool(self.simple_controlnet_var.get())
        steps = max(MIN_STEPS, min(MAX_STEPS, int(self.simple_steps_var.get())))
        for name in ("control_enabled_var", "control_required_var"):
            self._remember_variable(saved, self, name)
            var = getattr(self, name, None)
            if var is not None:
                try:
                    var.set(enabled)
                except Exception:
                    pass

        params = aggressive_render_parameters(style_name, enabled)
        prompt = str(directed.prompt or "")
        if "radical visual reinterpretation through the selected medium" not in prompt:
            prompt += RUNTIME_TRANSFORM_SUFFIX
        for name, value in (
            ("control_weight_var", float(params["control_weight"])),
            ("control_guidance_end_var", float(params["guidance_end"])),
            ("fx_intensity_var", float(params["fx"])),
            ("temporal_strength_var", float(params["temporal_strength"])),
        ):
            var = getattr(self, name, None)
            if var is not None and hasattr(var, "set"):
                try:
                    var.set(value)
                except Exception:
                    pass
        return replace(
            directed, prompt=prompt, denoise=float(params["denoise"]), steps=steps,
            controlnet_enabled=enabled, controlnet_weight=float(params["control_weight"]),
        ), saved

    def _blend_source_intensity(self, source, output, intensity: float) -> None:
        return super()._blend_source_intensity(source, output, clamp(.58 + .46 * float(intensity)))

    def _render_profile(self) -> dict[str, Any]:
        profile = super()._render_profile()
        profile["app_version"] = PRODUCT_VERSION
        control_var = getattr(self, "simple_controlnet_var", None)
        steps_var = getattr(self, "simple_steps_var", None)
        profile["creative_controls"] = {
            "version": PRODUCT_VERSION,
            "controlnet": bool(control_var.get()) if control_var is not None else True,
            "steps": int(steps_var.get()) if steps_var is not None else DEFAULT_STEPS,
            "style_policy": "aggressive-by-default",
            "style_library": STYLE_LIBRARY_VERSION,
        }
        shell = profile.setdefault("simple_shell", {})
        if isinstance(shell, dict):
            shell.update({
                "version": PRODUCT_VERSION,
                "operator_surface": "video -> look -> controlnet/steps -> video",
                "engine_controls_hidden": True,
                "searchable_style_browser": True,
                "live_preview_every": LIVE_PREVIEW_EVERY,
            })
        return profile


def main():
    ComicFrameStudioApp().mainloop()


if __name__ == "__main__":
    main()
