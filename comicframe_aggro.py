#!/usr/bin/env python3
"""ComicFrame Studio v3.3 — tiny creative controls, materially stronger styles.

The public contract stays small:

    Video -> Style -> [ControlNet] [Aggro] [Steps] -> Process

Everything else remains engine-owned. Aggro is intentionally a pipeline mode,
not a saturation knob: it raises diffusion authority, weakens structural
pressure, shortens ControlNet guidance, strengthens deterministic finishing and
reduces source blending while leaving identity/reference continuity available.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

import tkinter as tk
from tkinter import ttk

import comicframe_styles as styles
from comicframe_artistic import STYLE_STABILITY
from comicframe_presence import ComicFrameStudioApp as PresenceApp
from comicframe_interface import ACCENT, CARD, MUTED, TEXT

AGGRO_VERSION = "3.3"
MIN_STEPS = 12
MAX_STEPS = 36
DEFAULT_STEPS = 24


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def aggro_parameters(style_name: str, controlnet_enabled: bool) -> dict[str, float | bool]:
    """Return deliberately simple style-freedom parameters for one style."""
    pack = styles.STYLE_PACKS.get(style_name)
    if pack is None:
        return {
            "controlnet_enabled": bool(controlnet_enabled),
            "denoise": 0.62,
            "control_weight": 0.40 if controlnet_enabled else 0.0,
            "guidance_end": 0.60 if controlnet_enabled else 0.0,
            "fx": 0.95,
            "temporal_strength": 0.22,
        }

    stability = str(STYLE_STABILITY.get(style_name, "Medium"))
    if stability == "Experimental":
        denoise_boost, control_factor, guidance_cap, fx_boost, temporal_factor = 0.18, 0.36, 0.56, 0.10, 0.64
    elif stability == "High":
        denoise_boost, control_factor, guidance_cap, fx_boost, temporal_factor = 0.10, 0.64, 0.76, 0.06, 0.84
    else:
        denoise_boost, control_factor, guidance_cap, fx_boost, temporal_factor = 0.15, 0.48, 0.66, 0.09, 0.74

    return {
        "controlnet_enabled": bool(controlnet_enabled),
        "denoise": clamp(max(pack.denoise * 1.18, pack.denoise + denoise_boost), 0.30, 0.78),
        "control_weight": clamp(pack.control_weight * control_factor, 0.18, 0.72) if controlnet_enabled else 0.0,
        "guidance_end": min(float(pack.guidance_end), guidance_cap) if controlnet_enabled else 0.0,
        "fx": clamp(pack.fx + fx_boost),
        "temporal_strength": clamp(pack.temporal_strength * temporal_factor, 0.10, 0.42),
    }


class ComicFrameStudioApp(PresenceApp):
    """v3.2 product shell plus three understandable creative controls."""

    def __init__(self):
        super().__init__()
        self.title("ComicFrame Studio 3.3 · Video In / Video Out")

    def _install_simple_shell(self) -> None:
        super()._install_simple_shell()

        self.simple_controlnet_var = tk.BooleanVar(value=True)
        self.simple_aggro_var = tk.BooleanVar(value=True)
        self.simple_steps_var = tk.IntVar(value=DEFAULT_STEPS)
        self.simple_steps_text_var = tk.StringVar(value=f"{DEFAULT_STEPS} steps")

        process_card = self.simple_process_button.master
        self.simple_process_button.grid_configure(row=6, pady=(12, 0))

        controls = tk.Frame(process_card, bg=CARD)
        controls.grid(row=5, column=0, sticky="ew", pady=(2, 0))
        controls.grid_columnconfigure(2, weight=1)
        self.simple_creative_controls = controls

        self.simple_controlnet_toggle = ttk.Checkbutton(
            controls,
            text="CONTROLNET",
            variable=self.simple_controlnet_var,
            command=self._creative_control_changed,
        )
        self.simple_controlnet_toggle.grid(row=0, column=0, sticky="w", padx=(0, 14))

        self.simple_aggro_toggle = ttk.Checkbutton(
            controls,
            text="AGGRO",
            variable=self.simple_aggro_var,
            command=self._creative_control_changed,
        )
        self.simple_aggro_toggle.grid(row=0, column=1, sticky="w", padx=(0, 14))

        step_wrap = tk.Frame(controls, bg=CARD)
        step_wrap.grid(row=0, column=2, sticky="ew")
        step_wrap.grid_columnconfigure(1, weight=1)
        tk.Label(
            step_wrap,
            text="STEPS",
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI Semibold", 8),
        ).grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.simple_steps_scale = tk.Scale(
            step_wrap,
            from_=MIN_STEPS,
            to=MAX_STEPS,
            orient="horizontal",
            variable=self.simple_steps_var,
            command=self._steps_changed,
            showvalue=False,
            resolution=1,
            bg=CARD,
            fg=TEXT,
            troughcolor="#252a36",
            activebackground=ACCENT,
            highlightthickness=0,
            bd=0,
            sliderrelief="flat",
            length=190,
        )
        self.simple_steps_scale.grid(row=0, column=1, sticky="ew")
        tk.Label(
            step_wrap,
            textvariable=self.simple_steps_text_var,
            bg=CARD,
            fg="#bcaeff",
            font=("Segoe UI Semibold", 8),
            width=8,
            anchor="e",
        ).grid(row=0, column=2, sticky="e", padx=(8, 0))

        self.simple_creative_hint = tk.Label(
            process_card,
            text="AGGRO redraws harder · ControlNet holds structure · fewer steps render faster",
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 8),
            anchor="w",
        )
        self.simple_creative_hint.grid(row=7, column=0, sticky="ew", pady=(7, 0))
        self._creative_control_changed()

    def _steps_changed(self, value=None) -> None:
        try:
            steps = int(round(float(value if value is not None else self.simple_steps_var.get())))
        except Exception:
            steps = DEFAULT_STEPS
        steps = max(MIN_STEPS, min(MAX_STEPS, steps))
        self.simple_steps_var.set(steps)
        self.simple_steps_text_var.set(f"{steps} steps")

    def _creative_control_changed(self) -> None:
        if not hasattr(self, "simple_creative_hint"):
            return
        if bool(self.simple_aggro_var.get()):
            if bool(self.simple_controlnet_var.get()):
                text = "AGGRO · weak structure lock, harder redraw · fewer steps render faster"
            else:
                text = "AGGRO UNLEASHED · no ControlNet structure lock · expect maximum drift"
        else:
            text = "ControlNet holds structure · fewer steps render faster"
        self.simple_creative_hint.configure(text=text)

    def _simple_set_busy(self, busy: bool) -> None:
        super()._simple_set_busy(busy)
        state = "disabled" if busy else "normal"
        for widget in (
            getattr(self, "simple_controlnet_toggle", None),
            getattr(self, "simple_aggro_toggle", None),
            getattr(self, "simple_steps_scale", None),
        ):
            try:
                if widget is not None:
                    widget.configure(state=state)
            except Exception:
                pass

    def _enforce_public_controlnet_choice(self) -> None:
        """Keep backend auto-detection from silently overriding the public toggle."""
        var = getattr(self, "simple_controlnet_var", None)
        if var is None or not hasattr(var, "get"):
            return
        enabled = bool(var.get())
        for name, value in (
            ("control_enabled_var", enabled),
            ("control_required_var", enabled),
        ):
            target = getattr(self, name, None)
            try:
                if target is not None and hasattr(target, "set"):
                    target.set(value)
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
        aggro = bool(self.simple_aggro_var.get())
        steps = max(MIN_STEPS, min(MAX_STEPS, int(self.simple_steps_var.get())))

        for name in ("control_enabled_var", "control_required_var"):
            self._remember_variable(saved, self, name)
        for name in ("control_enabled_var", "control_required_var"):
            var = getattr(self, name, None)
            try:
                if var is not None:
                    var.set(enabled)
            except Exception:
                pass

        if not aggro:
            return replace(
                directed,
                steps=steps,
                controlnet_enabled=enabled,
                controlnet_weight=float(directed.controlnet_weight) if enabled else 0.0,
            ), saved

        params = aggro_parameters(style_name, enabled)
        prompt = str(directed.prompt or "") + (
            ", radical visual reinterpretation through the selected medium, redraw photographic surfaces as authored illustration, "
            "strong material transformation, bold environmental restyling, break literal photo texture, preserve recognizable subject identity, "
            "main action and broad composition rather than slavishly copying every source edge"
        )

        for name, value in (
            ("control_weight_var", float(params["control_weight"])),
            ("control_guidance_end_var", float(params["guidance_end"])),
            ("fx_intensity_var", float(params["fx"])),
            ("temporal_strength_var", float(params["temporal_strength"])),
        ):
            var = getattr(self, name, None)
            try:
                if var is not None and hasattr(var, "set"):
                    var.set(value)
            except Exception:
                pass

        return replace(
            directed,
            prompt=prompt,
            denoise=float(params["denoise"]),
            steps=steps,
            controlnet_enabled=enabled,
            controlnet_weight=float(params["control_weight"]),
        ), saved

    def _blend_source_intensity(self, source, output, intensity: float) -> None:
        aggro_var = getattr(self, "simple_aggro_var", None)
        if aggro_var is not None and hasattr(aggro_var, "get") and bool(aggro_var.get()):
            intensity = clamp(0.58 + 0.46 * float(intensity))
        return super()._blend_source_intensity(source, output, intensity)

    def _render_profile(self) -> dict[str, Any]:
        profile = super()._render_profile()
        control_var = getattr(self, "simple_controlnet_var", None)
        aggro_var = getattr(self, "simple_aggro_var", None)
        steps_var = getattr(self, "simple_steps_var", None)
        profile["creative_controls"] = {
            "version": AGGRO_VERSION,
            "controlnet": bool(control_var.get()) if control_var is not None else True,
            "aggro": bool(aggro_var.get()) if aggro_var is not None else True,
            "steps": int(steps_var.get()) if steps_var is not None else DEFAULT_STEPS,
        }
        return profile


def main():
    ComicFrameStudioApp().mainloop()


if __name__ == "__main__":
    main()
