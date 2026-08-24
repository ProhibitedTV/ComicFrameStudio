#!/usr/bin/env python3
"""ComicFrame Studio v1.2 WebUI-aware compatibility layer.

Discovery is driven by the Stable Diffusion WebUI itself. Instead of assuming
specific ControlNet extension route names, ComicFrame asks FastAPI for
/openapi.json, inspects the routes actually exposed by the running instance,
and then queries matching model/module endpoints.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

import requests

import comicframe_studio as v1


class ComicFrameStudioV12(v1.ComicFrameStudio):
    def __init__(self):
        super().__init__()
        self.title("ComicFrame Studio 1.2")
        self._rename_controlnet_button()

    def _rename_controlnet_button(self):
        """Rename the old button without relying on private widget handles."""
        def walk(widget):
            for child in widget.winfo_children():
                try:
                    if child.winfo_class() == "TButton" and child.cget("text") in {
                        "Refresh ControlNet", "Probe ControlNet"
                    }:
                        child.configure(text="Discover WebUI")
                except Exception:
                    pass
                walk(child)
        walk(self)

    @staticmethod
    def _extract_string_list(data, preferred_keys=()):
        """Pull a useful list of strings out of common API response shapes."""
        if isinstance(data, list):
            result = []
            for item in data:
                if isinstance(item, str):
                    result.append(item)
                elif isinstance(item, dict):
                    for key in ("title", "name", "model_name", "filename", "value"):
                        value = item.get(key)
                        if isinstance(value, str) and value:
                            result.append(value)
                            break
            return result

        if not isinstance(data, dict):
            return []

        for key in preferred_keys:
            value = data.get(key)
            if isinstance(value, list):
                return ComicFrameStudioV12._extract_string_list(value)

        # Common extension response keys.
        for key in (
            "model_list", "models", "module_list", "modules", "preprocessors",
            "processors", "items", "data", "results",
        ):
            value = data.get(key)
            if isinstance(value, list):
                return ComicFrameStudioV12._extract_string_list(value)

        return []

    def _refresh_controlnet(self):
        url = self.api_url()
        evidence = []
        discovered_routes = {}
        models = []
        modules = []
        checkpoints = []
        loaded_checkpoint = None

        def get_json(path, timeout=20):
            try:
                response = requests.get(f"{url}{path}", timeout=timeout)
                evidence.append(f"GET {path} -> HTTP {response.status_code}")
                if response.ok:
                    try:
                        return response.json()
                    except Exception:
                        evidence.append(f"GET {path} -> response was not JSON")
            except Exception as exc:
                evidence.append(f"GET {path} -> {type(exc).__name__}: {exc}")
            return None

        # Ask the Stable Diffusion WebUI what it actually exposes.
        openapi = get_json("/openapi.json")
        if isinstance(openapi, dict):
            paths = openapi.get("paths") or {}
            if isinstance(paths, dict):
                discovered_routes = paths
                self._log(f"WebUI OpenAPI reports {len(paths)} API route(s).")
            else:
                self._log("WebUI returned OpenAPI data without a usable paths map.")
        else:
            self._log("WebUI did not expose /openapi.json; falling back to known sdapi routes.")

        # Core WebUI inventory. These are checkpoints, NOT ControlNet models.
        options = get_json("/sdapi/v1/options")
        if isinstance(options, dict):
            loaded_checkpoint = (
                options.get("sd_model_checkpoint")
                or options.get("sd_checkpoint_hash")
                or options.get("sd_model_hash")
            )

        sd_models = get_json("/sdapi/v1/sd-models")
        checkpoints = self._extract_string_list(sd_models)
        if checkpoints:
            self._log(f"Stable Diffusion API reports {len(checkpoints)} checkpoint(s).")
            if loaded_checkpoint:
                self._log(f"Loaded checkpoint: {loaded_checkpoint}")
            for name in checkpoints[:20]:
                self._log(f"  checkpoint: {name}")
            if len(checkpoints) > 20:
                self._log(f"  ... {len(checkpoints) - 20} more checkpoint(s)")

        # Discover extension routes from the actual OpenAPI document.
        get_routes = []
        for path, methods in discovered_routes.items():
            if not isinstance(path, str) or not isinstance(methods, dict):
                continue
            if "get" not in {str(k).lower() for k in methods.keys()}:
                continue
            get_routes.append(path)

        control_routes = [p for p in get_routes if "control" in p.lower()]
        if control_routes:
            self._log("Control-related routes advertised by this WebUI:")
            for route in control_routes:
                self._log(f"  {route}")

        # Rank routes whose names strongly suggest model inventory.
        model_candidates = sorted(
            [
                p for p in control_routes
                if "model" in p.lower()
                and not re.search(r"/(download|preview|refresh)(/|$)", p.lower())
                and "{" not in p
            ],
            key=lambda p: (
                0 if "list" in p.lower() else 1,
                0 if "model" in p.lower() else 1,
                len(p),
            ),
        )

        # Rank routes that may provide preprocessors/modules/control types.
        module_candidates = sorted(
            [
                p for p in control_routes
                if any(token in p.lower() for token in ("module", "preprocessor", "processor", "control_type"))
                and "{" not in p
            ],
            key=lambda p: (
                0 if "list" in p.lower() else 1,
                len(p),
            ),
        )

        # Query what the running instance says is available.
        for path in model_candidates:
            data = get_json(path)
            found = self._extract_string_list(data, ("model_list", "models"))
            # /control_types can contain nested groups instead of one flat list.
            if not found and isinstance(data, dict):
                groups = data.get("control_types")
                if isinstance(groups, dict):
                    merged = []
                    for group in groups.values():
                        if isinstance(group, dict):
                            merged.extend(self._extract_string_list(group, ("model_list", "models")))
                    found = merged
            if found:
                models = list(dict.fromkeys(found))
                evidence.append(f"Selected model inventory route: {path}")
                break

        for path in module_candidates:
            data = get_json(path)
            found = self._extract_string_list(
                data,
                ("module_list", "modules", "preprocessors", "processors"),
            )
            if not found and isinstance(data, dict):
                groups = data.get("control_types")
                if isinstance(groups, dict):
                    merged = []
                    for group in groups.values():
                        if isinstance(group, dict):
                            merged.extend(
                                self._extract_string_list(
                                    group,
                                    ("module_list", "modules", "preprocessors", "processors"),
                                )
                            )
                    found = merged
            if found:
                modules = list(dict.fromkeys(found))
                evidence.append(f"Selected module inventory route: {path}")
                break

        # Fallbacks for older sd-webui-controlnet versions if OpenAPI is incomplete.
        if not models:
            for path in (
                "/controlnet/model_list?update=true",
                "/controlnet/model_list",
                "/controlnet/models",
            ):
                data = get_json(path)
                found = self._extract_string_list(data, ("model_list", "models"))
                if found:
                    models = list(dict.fromkeys(found))
                    evidence.append(f"Fallback model inventory route: {path}")
                    break

        if not modules:
            for path in (
                "/controlnet/module_list?alias_names=false",
                "/controlnet/module_list",
                "/controlnet/preprocessors",
            ):
                data = get_json(path)
                found = self._extract_string_list(
                    data,
                    ("module_list", "modules", "preprocessors", "processors"),
                )
                if found:
                    modules = list(dict.fromkeys(found))
                    evidence.append(f"Fallback module inventory route: {path}")
                    break

        if models:
            def apply_models():
                self.control_model_combo["values"] = models
                current = self.control_model_var.get().strip()
                if current not in models:
                    preferred = next(
                        (m for m in models if "canny" in m.lower()),
                        next((m for m in models if "line" in m.lower()), models[0]),
                    )
                    self.control_model_var.set(preferred)
            self.after(0, apply_models)

        if modules:
            def apply_modules():
                self.control_module_combo["values"] = modules
                current = self.control_module_var.get().strip()
                if current not in modules:
                    preferred = next(
                        (m for m in modules if "canny" in m.lower()),
                        next((m for m in modules if "line" in m.lower()), modules[0]),
                    )
                    self.control_module_var.set(preferred)
            self.after(0, apply_modules)

        if models:
            self.after(0, lambda: self.control_enabled_var.set(True))
            self._log(f"CONTROLNET READY: discovered {len(models)} model(s) and {len(modules)} module/preprocessor(s).")
            for name in models[:20]:
                self._log(f"  control model: {name}")
            if len(models) > 20:
                self._log(f"  ... {len(models) - 20} more ControlNet model(s)")
            self._set_progress(0, "ControlNet ready")
        elif control_routes:
            self._log("CONTROL API ROUTES FOUND, BUT NO CONTROL MODEL INVENTORY COULD BE PARSED.")
            self._log("The routes are listed above; this tells us exactly what this WebUI exposes so support can be added without guessing.")
            self._set_progress(0, "Control routes found; models unresolved")
        else:
            self._log("NO CONTROLNET/CONTROL ROUTES WERE ADVERTISED BY THE WEBUI API.")
            self._log("Core Stable Diffusion checkpoints were still discovered successfully; ControlNet is being disabled for this run.")
            self.after(0, lambda: self.control_enabled_var.set(False))
            self._set_progress(0, "No ControlNet API routes")

        self._log("Discovery details:")
        for line in evidence:
            self._log(f"  {line}")

    def _build_payload(self, frame_path, settings, width, height, frame_number):
        payload = super()._build_payload(frame_path, settings, width, height, frame_number)
        scripts = payload.get("alwayson_scripts")
        if isinstance(scripts, dict) and "ControlNet" in scripts and "controlnet" not in scripts:
            scripts["controlnet"] = scripts.pop("ControlNet")
        return payload

    def _render_range(self, start, count, test_only):
        if self.control_enabled_var.get() and not self.control_model_var.get().strip():
            raise RuntimeError(
                "ControlNet is enabled but no ControlNet model is selected. Click Discover WebUI first. "
                "If the WebUI advertises no ControlNet routes, uncheck ControlNet and render a plain img2img baseline."
            )
        return super()._render_range(start, count, test_only)


def main():
    ComicFrameStudioV12().mainloop()


if __name__ == "__main__":
    main()
