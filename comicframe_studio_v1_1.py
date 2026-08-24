#!/usr/bin/env python3
"""ComicFrame Studio v1.1 compatibility wrapper.

Adds robust ControlNet detection/diagnostics on top of the v1 renderer without
changing the proven extract/render/reassemble pipeline.
"""
from __future__ import annotations

import requests

import comicframe_studio as v1


class ComicFrameStudioV11(v1.ComicFrameStudio):
    def __init__(self):
        super().__init__()
        self.title("ComicFrame Studio 1.1")
        self._rename_controlnet_button()

    def _rename_controlnet_button(self):
        """Rename the old button without depending on private widget handles."""
        def walk(widget):
            for child in widget.winfo_children():
                try:
                    if child.winfo_class() == "TButton" and child.cget("text") == "Refresh ControlNet":
                        child.configure(text="Probe ControlNet")
                except Exception:
                    pass
                walk(child)
        walk(self)

    def _refresh_controlnet(self):
        """Detect ControlNet and explain exactly what A1111 exposes.

        Canonical sd-webui-controlnet routes:
          /controlnet/version
          /controlnet/control_types
          /controlnet/model_list
          /controlnet/module_list

        A1111 routes are also queried so we can distinguish a missing extension
        from an installed extension with no models.
        """
        url = self.api_url()
        models = []
        modules = []
        detected = False
        evidence = []

        def get_json(path, timeout=15):
            try:
                r = requests.get(f"{url}{path}", timeout=timeout)
                evidence.append(f"GET {path} -> HTTP {r.status_code}")
                if r.ok:
                    try:
                        return r.json()
                    except Exception:
                        evidence.append(f"GET {path} -> response was not JSON")
            except Exception as exc:
                evidence.append(f"GET {path} -> {type(exc).__name__}: {exc}")
            return None

        # A1111-level detection.
        extensions = get_json("/sdapi/v1/extensions")
        if isinstance(extensions, list):
            for item in extensions:
                if isinstance(item, dict):
                    name = str(item.get("name", ""))
                    enabled = bool(item.get("enabled", True))
                else:
                    name = str(item)
                    enabled = True
                if "controlnet" in name.lower() and enabled:
                    detected = True
                    evidence.append(f"A1111 extension detected: {name}")

        scripts = get_json("/sdapi/v1/scripts")
        if isinstance(scripts, dict):
            names = []
            for value in scripts.values():
                if isinstance(value, list):
                    names.extend(str(x) for x in value)
            if any("controlnet" in name.lower() for name in names):
                detected = True
                evidence.append("A1111 ControlNet script detected")

        # ControlNet extension-level detection.
        version = get_json("/controlnet/version")
        if isinstance(version, dict):
            detected = True
            evidence.append(f"ControlNet API version: {version.get('version', 'unknown')}")

        # Newer versions expose grouped control types, including useful defaults.
        control_types = get_json("/controlnet/control_types")
        if isinstance(control_types, dict):
            detected = True
            groups = control_types.get("control_types") or {}
            if isinstance(groups, dict):
                canny_key = next((k for k in groups if "canny" in k.lower()), None)
                group = groups.get(canny_key) if canny_key else None
                if isinstance(group, dict):
                    modules = list(group.get("module_list") or [])
                    models = list(group.get("model_list") or [])
                    default_module = group.get("default_option")
                    default_model = group.get("default_model")
                    if default_module:
                        self.after(0, lambda x=default_module: self.control_module_var.set(x))
                    if default_model:
                        self.after(0, lambda x=default_model: self.control_model_var.set(x))

        # Canonical fallbacks.
        if not models:
            data = get_json("/controlnet/model_list?update=true")
            if not isinstance(data, dict):
                data = get_json("/controlnet/model_list")
            if isinstance(data, dict):
                detected = True
                models = list(data.get("model_list") or data.get("models") or [])

        if not modules:
            data = get_json("/controlnet/module_list?alias_names=false")
            if not isinstance(data, dict):
                data = get_json("/controlnet/module_list")
            if isinstance(data, dict):
                detected = True
                modules = list(data.get("module_list") or data.get("modules") or [])

        if models:
            def apply_models():
                self.control_model_combo["values"] = models
                current = self.control_model_var.get().strip()
                if current not in models:
                    self.control_model_var.set(next((m for m in models if "canny" in m.lower()), models[0]))
            self.after(0, apply_models)

        if modules:
            def apply_modules():
                self.control_module_combo["values"] = modules
                current = self.control_module_var.get().strip()
                if current not in modules:
                    self.control_module_var.set(next((m for m in modules if "canny" in m.lower()), modules[0]))
            self.after(0, apply_modules)

        if detected and models:
            self._log(f"CONTROLNET READY: {len(models)} model(s), {len(modules)} module(s).")
            self._set_progress(0, "ControlNet ready")
        elif detected:
            self._log("CONTROLNET DETECTED, BUT NO MODELS ARE INSTALLED/EXPOSED.")
            self._log("Install a ControlNet model compatible with the loaded checkpoint, then Probe ControlNet again.")
            self._set_progress(0, "ControlNet detected; no models")
        else:
            self._log("CONTROLNET NOT DETECTED.")
            self._log("A1111 is reachable, but the sd-webui-controlnet API/routes are absent.")
            self._log("Install/enable sd-webui-controlnet, restart A1111, or uncheck ControlNet for plain img2img.")
            self.after(0, lambda: self.control_enabled_var.set(False))
            self._set_progress(0, "ControlNet not installed/enabled")

        self._log("ControlNet probe details:")
        for line in evidence:
            self._log(f"  {line}")

    def _build_payload(self, frame_path, settings, width, height, frame_number):
        payload = super()._build_payload(frame_path, settings, width, height, frame_number)
        # The extension's documented always-on script name is lowercase.
        scripts = payload.get("alwayson_scripts")
        if isinstance(scripts, dict) and "ControlNet" in scripts and "controlnet" not in scripts:
            scripts["controlnet"] = scripts.pop("ControlNet")
        return payload

    def _render_range(self, start, count, test_only):
        if self.control_enabled_var.get() and not self.control_model_var.get().strip():
            raise RuntimeError(
                "ControlNet is enabled but no model is selected. Click Probe ControlNet first. "
                "If the probe says ControlNet is missing, install/enable the extension or uncheck "
                "ControlNet for a plain img2img baseline."
            )
        return super()._render_range(start, count, test_only)


def main():
    ComicFrameStudioV11().mainloop()


if __name__ == "__main__":
    main()
