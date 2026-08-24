#!/usr/bin/env python3
"""Robust ControlNet discovery for ComicFrame Studio.

Some sd-webui-controlnet builds serve their API normally but do not expose the
extension routes in A1111's /openapi.json.  Probe the canonical extension API
first and only fall back to the older OpenAPI-based UI implementation when the
direct endpoints are genuinely absent.
"""
from __future__ import annotations

from typing import Any

import requests


class DirectControlNetProbeMixin:
    """Override ComicFrame's ControlNet discovery with direct endpoint probes."""

    @staticmethod
    def _controlnet_values(data: Any, *keys: str) -> list[str]:
        if isinstance(data, list):
            values = data
        elif isinstance(data, dict):
            values = []
            for key in keys:
                candidate = data.get(key)
                if isinstance(candidate, list):
                    values = candidate
                    break
        else:
            values = []

        out: list[str] = []
        for item in values:
            if isinstance(item, str):
                value = item.strip()
            elif isinstance(item, dict):
                value = str(item.get("name") or item.get("title") or item.get("label") or "").strip()
            else:
                value = ""
            if value and value.lower() not in {"none", "none [none]"} and value not in out:
                out.append(value)
        return out

    def _detect_controlnet(self):
        url = self.api_url()
        evidence: list[str] = []
        models: list[str] = []
        modules: list[str] = []
        extension_detected = False
        version = ""

        def get_json(path: str):
            nonlocal extension_detected
            try:
                response = requests.get(f"{url}{path}", timeout=20)
                evidence.append(f"GET {path} -> HTTP {response.status_code}")
                if not response.ok:
                    return None
                extension_detected = True
                try:
                    return response.json()
                except Exception:
                    evidence.append(f"GET {path} -> response was not JSON")
                    return None
            except Exception as exc:
                evidence.append(f"GET {path} -> {type(exc).__name__}: {exc}")
                return None

        # Canonical sd-webui-controlnet API. These are the important probes;
        # do not require the routes to be advertised in /openapi.json.
        data = get_json("/controlnet/version")
        if isinstance(data, dict):
            version = str(data.get("version") or "").strip()
        elif data is not None:
            version = str(data).strip()

        for endpoint in ("/controlnet/model_list?update=true", "/controlnet/model_list"):
            data = get_json(endpoint)
            found = self._controlnet_values(data, "model_list", "models")
            for value in found:
                if value not in models:
                    models.append(value)
            if models:
                break

        for endpoint in ("/controlnet/module_list?alias_names=false", "/controlnet/module_list"):
            data = get_json(endpoint)
            found = self._controlnet_values(data, "module_list", "modules", "preprocessors")
            for value in found:
                if value not in modules:
                    modules.append(value)
            if modules:
                break

        # Newer builds may expose a grouped control-types inventory. Use it as
        # another source of model/module names if the simple lists are empty.
        if not models or not modules:
            data = get_json("/controlnet/control_types")
            if isinstance(data, dict):
                groups = data.get("control_types") or data
                if isinstance(groups, dict):
                    for group in groups.values():
                        if not isinstance(group, dict):
                            continue
                        for value in self._controlnet_values(group, "model_list", "models"):
                            if value not in models:
                                models.append(value)
                        for value in self._controlnet_values(group, "module_list", "modules"):
                            if value not in modules:
                                modules.append(value)

        # If none of the canonical endpoints exist, preserve compatibility with
        # alternative WebUIs by using the older route-discovery implementation.
        if not extension_detected:
            self._log("ControlNet direct API was not detected; falling back to WebUI route discovery.")
            for line in evidence:
                self._log(f"  {line}")
            return super()._detect_controlnet()

        self._controlnet_extension_available = True
        self._controlnet_available = bool(models)

        def apply():
            if models:
                self.control_model_combo["values"] = models
                current = self.control_model_var.get().strip()
                if current not in models:
                    self.control_model_var.set(next((m for m in models if "canny" in m.lower()), models[0]))

                if modules:
                    self.control_module_combo["values"] = modules
                    current_module = self.control_module_var.get().strip()
                    if current_module not in modules:
                        self.control_module_var.set(next((m for m in modules if m.lower() == "canny" or "canny" in m.lower()), modules[0]))

                version_text = f" {version}" if version else ""
                self.cn_status_var.set(f"Ready · ControlNet{version_text} · {len(models)} model(s)")
                self.cn_status_label.configure(style="Good.TLabel")
            else:
                self.control_enabled_var.set(False)
                version_text = f" {version}" if version else ""
                self.cn_status_var.set(f"ControlNet{version_text} detected · no models")
                self.cn_status_label.configure(style="Warn.TLabel")

        self.after(0, apply)

        self._log(
            f"ControlNet direct probe: version={version or 'unknown'}, "
            f"models={len(models)}, modules={len(modules)}"
        )
        for line in evidence:
            self._log(f"  {line}")
        if models:
            self._log("ControlNet models: " + "; ".join(models))
