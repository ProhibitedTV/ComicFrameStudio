#!/usr/bin/env python3
"""A1111 / Forge API contract hardening for ComicFrame Studio v2.1.

ComicFrame intentionally supports more than one Stable Diffusion WebUI.  Treat
those WebUIs as external services rather than assuming every A1111-compatible
build exposes every discovery endpoint perfectly.  This layer centralizes
capability probing, checkpoint verification, API-error normalization and image
response validation while leaving the rendering/style mixins above it intact.
"""
from __future__ import annotations

import base64
import json
import re
from io import BytesIO
from pathlib import Path
from typing import Any

import requests
import tkinter as tk
from tkinter import ttk
from PIL import Image


class WebUIContractMixin:
    """Harden external WebUI boundaries without changing the artistic pipeline."""

    def _build_ui(self):
        self.api_contract_status_var = tk.StringVar(value="API contract not probed yet")
        self._webui_capabilities: dict[str, bool] = {}
        self._webui_backend = "A1111-compatible"
        self._webui_model_catalog_degraded = False
        super()._build_ui()

    def _build_webui_card(self):
        result = super()._build_webui_card()
        card = self._panel(self.left, "2B · API contract · v2.1")
        card.pack(fill="x", pady=(0, 8))
        ttk.Label(
            card,
            text=(
                "ComicFrame probes the running backend instead of assuming every A1111-compatible build exposes the same optional routes. "
                "Core generation requires /sdapi/v1/options and img2img. Model/scheduler catalogs degrade safely when an older Forge/A1111 build has a broken discovery endpoint."
            ),
            style="Muted.TLabel",
            wraplength=760,
        ).pack(anchor="w")
        ttk.Label(card, textvariable=self.api_contract_status_var, style="Muted.TLabel", wraplength=760).pack(
            anchor="w", pady=(5, 0)
        )
        return result

    # ---------- HTTP / schema helpers ----------

    @staticmethod
    def _compact_json(value: Any, limit: int = 900) -> str:
        try:
            text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            text = str(value)
        text = " ".join(text.split())
        return text if len(text) <= limit else text[:limit] + "…"

    @classmethod
    def _response_error_text(cls, response) -> str:
        """Normalize A1111/Forge/FastAPI error envelopes into one useful message."""
        try:
            data = response.json()
        except Exception:
            text = (getattr(response, "text", "") or "").strip()
            return text[:1000] if text else f"HTTP {getattr(response, 'status_code', '?')}"

        if isinstance(data, dict):
            parts: list[str] = []
            # A1111 commonly exposes detail/body/errors; Forge variants may use
            # detail/body/message/error. Keep all meaningful fields instead of
            # hard-coding a single backend envelope.
            for key in ("detail", "message", "error", "errors", "body"):
                value = data.get(key)
                if value in (None, "", [], {}):
                    continue
                rendered = cls._compact_json(value, 500)
                if rendered not in parts:
                    parts.append(rendered)
            if parts:
                return " · ".join(parts)[:1200]
        return cls._compact_json(data, 1000)

    def _api_json(
        self,
        method: str,
        path: str,
        *,
        timeout: float = 20,
        json_body: dict | None = None,
        required: bool = False,
        quiet: bool = False,
    ) -> Any | None:
        url = f"{self.api_url()}{path}"
        try:
            response = requests.request(
                method.upper(),
                url,
                json=json_body,
                timeout=timeout,
                headers={"Accept": "application/json"},
            )
        except requests.RequestException as exc:
            if required:
                raise RuntimeError(f"WebUI request failed: {method.upper()} {path}: {exc}") from exc
            if not quiet:
                self._log(f"WebUI optional route unavailable: {method.upper()} {path}: {exc}")
            return None

        if not response.ok:
            detail = self._response_error_text(response)
            if required:
                raise RuntimeError(
                    f"WebUI API {method.upper()} {path} returned HTTP {response.status_code}: {detail}"
                )
            if not quiet:
                self._log(
                    f"WebUI optional route {method.upper()} {path} -> HTTP {response.status_code}: {detail}"
                )
            return None

        if not response.content:
            return {}
        try:
            return response.json()
        except Exception as exc:
            if required:
                raise RuntimeError(
                    f"WebUI API {method.upper()} {path} returned HTTP {response.status_code} but not valid JSON."
                ) from exc
            if not quiet:
                self._log(f"WebUI optional route {method.upper()} {path} returned non-JSON data.")
            return None

    @staticmethod
    def _checkpoint_key(value: str) -> str:
        value = (value or "").strip().replace("\\", "/")
        value = value.rsplit("/", 1)[-1]
        value = value.split(" [", 1)[0]
        for suffix in (".safetensors", ".ckpt", ".pt"):
            if value.lower().endswith(suffix):
                value = value[: -len(suffix)]
                break
        return value.casefold()

    @classmethod
    def _checkpoint_matches(cls, current: str, target: str) -> bool:
        if not current or not target:
            return False
        return current == target or cls._checkpoint_key(current) == cls._checkpoint_key(target)

    @staticmethod
    def _route_backend(paths: set[str]) -> str:
        # Forge currently exposes /sdapi/v1/sd-modules whereas upstream A1111
        # exposes /sdapi/v1/sd-vae. This is only a display/fingerprint hint;
        # capability checks, not this label, control behavior.
        if "/sdapi/v1/sd-modules" in paths:
            return "Forge"
        if "/sdapi/v1/sd-vae" in paths:
            return "AUTOMATIC1111"
        return "A1111-compatible"

    # ---------- Capability-driven WebUI sync ----------

    def _fetch_model_catalog(self, current_checkpoint: str) -> list[str]:
        data = self._api_json("GET", "/sdapi/v1/sd-models", timeout=30, quiet=True)
        names = self._names_from_list(data, ("title", "model_name", "name")) if data is not None else []
        if names:
            self._webui_capabilities["models"] = True
            self._webui_model_catalog_degraded = False
            return names

        # Older Forge builds have shipped temporary sd-models response-model
        # regressions. Refresh once and retry, then fall back to the active
        # checkpoint rather than making the entire app unusable.
        self._api_json("POST", "/sdapi/v1/refresh-checkpoints", timeout=60, quiet=True)
        data = self._api_json("GET", "/sdapi/v1/sd-models", timeout=30, quiet=True)
        names = self._names_from_list(data, ("title", "model_name", "name")) if data is not None else []
        self._webui_capabilities["models"] = bool(names)
        self._webui_model_catalog_degraded = not bool(names)
        if names:
            return names
        if current_checkpoint:
            self._log(
                "Checkpoint catalog unavailable; using the currently loaded checkpoint as a safe one-item fallback."
            )
            return [current_checkpoint]
        return []

    def _sync_webui(self):
        # /options is the minimum control-plane contract. If that is absent,
        # pretending the backend is usable only postpones a clearer failure.
        options = self._api_json("GET", "/sdapi/v1/options", timeout=20, required=True)
        if not isinstance(options, dict):
            raise RuntimeError("WebUI /sdapi/v1/options returned an unexpected response shape.")
        self._webui_capabilities["options"] = True

        paths: set[str] = set()
        openapi = self._api_json("GET", "/openapi.json", timeout=15, quiet=True)
        if isinstance(openapi, dict) and isinstance(openapi.get("paths"), dict):
            paths = set(openapi["paths"].keys())
        self._api_routes = paths
        self._webui_backend = self._route_backend(paths)
        self._webui_capabilities["img2img"] = (
            "/sdapi/v1/img2img" in paths if paths else True
        )

        current = str(options.get("sd_model_checkpoint") or "").strip()
        current_sampler = str(options.get("sampler_name") or "").strip()
        model_names = self._fetch_model_catalog(current)

        samplers_data = self._api_json("GET", "/sdapi/v1/samplers", timeout=20, quiet=True)
        sampler_names = self._names_from_list(samplers_data, ("name", "label")) if samplers_data is not None else []
        self._webui_capabilities["samplers"] = bool(sampler_names)
        if not sampler_names and self.sampler_var.get().strip():
            # Retain the user's configured sampler as a degraded fallback. The
            # generation call will still validate it server-side.
            sampler_names = [self.sampler_var.get().strip()]
            self._log("Sampler catalog unavailable; retaining the configured sampler and deferring validation to img2img.")

        sched_data = self._api_json("GET", "/sdapi/v1/schedulers", timeout=20, quiet=True)
        schedulers = self._names_from_list(sched_data, ("name", "label")) if sched_data is not None else []
        self._webui_capabilities["schedulers"] = bool(schedulers)

        memory_data = self._api_json("GET", "/sdapi/v1/memory", timeout=15, quiet=True)
        self._webui_capabilities["memory"] = isinstance(memory_data, dict)

        # Both current upstream A1111 and Forge expose LoRA inventory through a
        # built-in extension. Treat it as optional because users can disable the
        # extension without breaking core img2img.
        lora_data = self._api_json("GET", "/sdapi/v1/loras", timeout=20, quiet=True)
        self._webui_capabilities["loras"] = isinstance(lora_data, list)

        # Keep Base UI's route cache useful for legacy fallback discovery.
        def apply():
            self.checkpoint_combo["values"] = model_names
            if current:
                match = next((m for m in model_names if self._checkpoint_matches(current, m)), None)
                self.checkpoint_var.set(match or current)
            elif model_names and not self.checkpoint_var.get():
                self.checkpoint_var.set(model_names[0])

            self.sampler_combo["values"] = sampler_names
            if current_sampler and current_sampler in sampler_names:
                self.sampler_var.set(current_sampler)
            elif sampler_names and self.sampler_var.get() not in sampler_names:
                preferred = next((s for s in sampler_names if s.casefold() == "dpm++ 2m"), sampler_names[0])
                self.sampler_var.set(preferred)

            self.scheduler_combo["values"] = schedulers
            if schedulers and self.scheduler_var.get() not in schedulers:
                self.scheduler_var.set(next((s for s in schedulers if s.casefold() == "automatic"), schedulers[0]))
            elif not schedulers:
                self.scheduler_var.set("")

            self.loaded_checkpoint_var.set(current or "Unknown")
            degraded = " · checkpoint catalog fallback" if self._webui_model_catalog_degraded else ""
            self.webui_status_var.set(
                f"{self._webui_backend} ready · {len(model_names)} model(s) · {len(sampler_names)} sampler(s){degraded}"
            )
            self.webui_status_label.configure(style="Good.TLabel")

            cap = self._webui_capabilities
            self.api_contract_status_var.set(
                f"{self._webui_backend} · img2img={'yes' if cap.get('img2img') else 'unknown'} · "
                f"models={'yes' if cap.get('models') else 'fallback'} · "
                f"schedulers={'yes' if cap.get('schedulers') else 'omit'} · "
                f"memory={'yes' if cap.get('memory') else 'unavailable'} · "
                f"LoRA={'yes' if cap.get('loras') else 'optional/unavailable'}"
            )

        self.after(0, apply)
        self._log(
            f"WebUI contract: backend={self._webui_backend}, models={len(model_names)}, "
            f"samplers={len(sampler_names)}, schedulers={len(schedulers)}, "
            f"memory={'yes' if self._webui_capabilities['memory'] else 'no'}, "
            f"loras={'yes' if self._webui_capabilities['loras'] else 'no'}"
        )

        # Keep existing LoRA UI plumbing and ControlNet's direct v3 probe. The
        # latter deliberately does not depend on OpenAPI advertising extension routes.
        if hasattr(self, "_sync_loras"):
            self._sync_loras()
        self._detect_controlnet()

    # ---------- Checkpoint loading ----------

    def _ensure_checkpoint_loaded(self):
        target = self.checkpoint_var.get().strip()
        if not target:
            return

        options = self._api_json("GET", "/sdapi/v1/options", timeout=20, required=True)
        current = str((options or {}).get("sd_model_checkpoint") or "").strip()
        if self._checkpoint_matches(current, target):
            self._log(f"Checkpoint already active: {target}")
            return

        self._log(f"Loading checkpoint: {target}")
        self._set_progress(self.progress.get(), f"Loading checkpoint: {target}")
        self._api_json(
            "POST",
            "/sdapi/v1/options",
            timeout=900,
            json_body={"sd_model_checkpoint": target},
            required=True,
        )

        # A 200 response only means the settings request completed. Verify that
        # the backend actually reports the requested checkpoint as active.
        verify = self._api_json("GET", "/sdapi/v1/options", timeout=30, required=True)
        active = str((verify or {}).get("sd_model_checkpoint") or "").strip()
        if not self._checkpoint_matches(active, target):
            raise RuntimeError(
                f"WebUI accepted the checkpoint change request but reports '{active or 'unknown'}' active instead of '{target}'."
            )

        self._log(f"Checkpoint loaded and verified: {active}")
        self.after(0, lambda: self.loaded_checkpoint_var.set(active))

    # ---------- Request contract ----------

    def _build_payload(self, frame_path, settings, width, height, frame_number):
        payload = super()._build_payload(frame_path, settings, width, height, frame_number)

        # Make the response contract explicit instead of depending on backend
        # defaults. Current A1111 and Forge both define these fields.
        payload["send_images"] = True
        payload["save_images"] = False
        payload["include_init_images"] = False
        payload["batch_size"] = 1
        payload["n_iter"] = 1

        # Scheduler is supported by current A1111 and Forge, but older compatible
        # servers may not expose it. If sync proved it unavailable, omit it.
        if self._webui_capabilities.get("schedulers") is False:
            payload.pop("scheduler", None)
        return payload

    @staticmethod
    def _save_api_image(data, out_path):
        """Decode any backend sample format, verify it, then atomically store a real PNG."""
        if not isinstance(data, str) or not data.strip():
            raise RuntimeError("WebUI img2img response contained an empty/non-string image payload.")
        encoded = data.strip()
        if encoded.startswith("data:image"):
            if "," not in encoded:
                raise RuntimeError("WebUI returned a malformed data-URI image.")
            encoded = encoded.split(",", 1)[1]
        # Some encoders insert harmless whitespace/newlines into base64 output.
        encoded = "".join(encoded.split())
        try:
            raw = base64.b64decode(encoded, validate=True)
        except Exception as exc:
            raise RuntimeError("WebUI returned image data that is not valid base64.") from exc

        try:
            with Image.open(BytesIO(raw)) as image:
                image.load()
                rgb = image.convert("RGB")
        except Exception as exc:
            raise RuntimeError("WebUI returned base64 bytes that Pillow could not decode as an image.") from exc

        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        temp = out_path.with_name(out_path.name + ".part")
        try:
            rgb.save(temp, format="PNG", optimize=False)
            with Image.open(temp) as check:
                check.verify()
            temp.replace(out_path)
        finally:
            if temp.exists():
                try:
                    temp.unlink()
                except Exception:
                    pass

    @classmethod
    def _normalize_runtime_error(cls, text: str) -> str | None:
        match = re.match(r"Stable Diffusion API HTTP\s+(\d+):\s*(.*)", text, flags=re.DOTALL)
        if not match:
            return None
        status, body = match.groups()
        body = body.strip()
        detail = body
        try:
            parsed = json.loads(body)
            if isinstance(parsed, dict):
                fields = []
                for key in ("detail", "message", "error", "errors", "body"):
                    value = parsed.get(key)
                    if value not in (None, "", [], {}):
                        rendered = cls._compact_json(value, 500)
                        if rendered not in fields:
                            fields.append(rendered)
                if fields:
                    detail = " · ".join(fields)
        except Exception:
            pass
        return f"WebUI img2img failed (HTTP {status}): {detail[:1200]}"

    def _render_one(self, frame_path, out_path, settings, width, height, frame_number):
        try:
            result = super()._render_one(frame_path, out_path, settings, width, height, frame_number)
        except RuntimeError as exc:
            normalized = self._normalize_runtime_error(str(exc))
            if normalized:
                raise RuntimeError(normalized) from exc
            raise

        path = Path(out_path)
        if not path.exists() or path.stat().st_size <= 0:
            raise RuntimeError(f"WebUI render completed without producing {path.name}.")
        try:
            with Image.open(path) as image:
                image.verify()
        except Exception as exc:
            try:
                path.unlink()
            except Exception:
                pass
            raise RuntimeError(f"Rendered frame {path.name} failed image verification and was removed.") from exc
        return result

    # ---------- Resume diagnostics ----------

    def _render_profile(self) -> dict:
        profile = super()._render_profile()
        profile["app_version"] = "2.1"
        profile["webui_contract"] = {
            "backend": self._webui_backend,
            "scheduler_capability": bool(self._webui_capabilities.get("schedulers", False)),
            "model_catalog_degraded": bool(self._webui_model_catalog_degraded),
            "explicit_send_images": True,
            "atomic_png_decode": True,
        }
        return profile
