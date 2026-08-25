#!/usr/bin/env python3
"""Race-safe ControlNet inventory and auto-selection for ComicFrame Studio."""
from __future__ import annotations

from typing import Any

import requests


class ControlNetPreflightMixin:
    @staticmethod
    def _looks_sdxl(name: str) -> bool:
        """Recognize common SDXL naming conventions such as JuggernautXL."""
        return "xl" in (name or "").lower()

    @staticmethod
    def _inventory_values(data: Any, *keys: str) -> list[str]:
        if isinstance(data, list):
            raw = data
        elif isinstance(data, dict):
            raw = []
            for key in keys:
                candidate = data.get(key)
                if isinstance(candidate, list):
                    raw = candidate
                    break
        else:
            raw = []
        out: list[str] = []
        for item in raw:
            if isinstance(item, str):
                value = item.strip()
            elif isinstance(item, dict):
                value = str(item.get("name") or item.get("title") or item.get("label") or "").strip()
            else:
                value = ""
            if value and value.lower() not in {"none", "none [none]"} and value not in out:
                out.append(value)
        return out

    def _probe_gpu_memory(self):
        """Apply a conservative inference profile from A1111's CUDA memory report."""
        try:
            response = requests.get(f"{self.api_url()}/sdapi/v1/memory", timeout=15)
            if not response.ok:
                return
            data = response.json()
            total = None
            if isinstance(data, dict):
                cuda = data.get("cuda")
                if isinstance(cuda, dict):
                    system = cuda.get("system")
                    if isinstance(system, dict):
                        candidate = system.get("total")
                        if isinstance(candidate, (int, float)) and candidate > 0:
                            total = int(candidate)
            if not total:
                return

            gib = total / (1024 ** 3)
            self._detected_vram_gb = gib
            if gib < 8.0:
                self.control_low_vram_var.set(True)
                self.inference_mode_var.set("768 long edge · emergency / low VRAM")
                self.gpu_status_var.set(
                    f"GPU VRAM detected: {gib:.1f} GiB · low-VRAM ControlNet ON · inference forced to 768"
                )
            else:
                self.control_low_vram_var.set(False)
                if self.inference_mode_var.get().startswith("Source"):
                    self.inference_mode_var.set("1024 long edge · fast / stable")
                self.gpu_status_var.set(
                    f"GPU VRAM detected: {gib:.1f} GiB · RTX 3060-class profile · 1024 recommended"
                )
            self._log(f"GPU memory probe: {gib:.1f} GiB VRAM")
        except Exception as exc:
            self._log(f"GPU memory probe skipped: {exc}")

    def _direct_controlnet_inventory(self) -> tuple[list[str], list[str]]:
        url = self.api_url()
        models: list[str] = []
        modules: list[str] = []
        for endpoint in ("/controlnet/model_list?update=true", "/controlnet/model_list"):
            try:
                response = requests.get(f"{url}{endpoint}", timeout=20)
                if response.ok:
                    models = self._inventory_values(response.json(), "model_list", "models")
                    if models:
                        break
            except Exception:
                pass
        for endpoint in ("/controlnet/module_list?alias_names=false", "/controlnet/module_list"):
            try:
                response = requests.get(f"{url}{endpoint}", timeout=20)
                if response.ok:
                    modules = self._inventory_values(response.json(), "module_list", "modules", "preprocessors")
                    if modules:
                        break
            except Exception:
                pass
        return models, modules

    def _select_controlnet_defaults(self):
        models = list(self.control_model_combo["values"] or [])
        modules = list(self.control_module_combo["values"] or [])
        if not models:
            models, direct_modules = self._direct_controlnet_inventory()
            modules = direct_modules or modules
            if models:
                self.control_model_combo["values"] = models
            if modules:
                self.control_module_combo["values"] = modules
        if not models:
            return

        checkpoint = self.checkpoint_var.get().strip()
        wants_xl = self._looks_sdxl(checkpoint)

        def score(name: str) -> tuple[int, int, int, int]:
            low = name.lower()
            return (
                1 if "canny" in low else 0,
                1 if self._looks_sdxl(name) == wants_xl else 0,
                1 if "mid" in low else 0,
                1 if "small" in low else 0,
            )

        best = max(models, key=score)
        self.control_model_var.set(best)
        if modules:
            module = next((m for m in modules if m.lower() == "canny"), None)
            if not module:
                module = next((m for m in modules if "canny" in m.lower()), modules[0])
            self.control_module_var.set(module)
        self.control_enabled_var.set(True)
        self.control_weight_var.set(0.95)
        self._log(f"ControlNet auto-selected: module={self.control_module_var.get()}, model={best}")
