#!/usr/bin/env python3
"""Compatibility normalization for sd-webui-controlnet API payloads.

ControlNet v3 validates several fields as string enums. Older ComicFrame code
used the historical integer value ``0`` for ``control_mode``. Normalize the
final payload at the canonical runtime boundary so both old internal builders
and current ControlNet servers receive the modern API representation.
"""
from __future__ import annotations

from typing import Any


_CONTROL_MODE_MAP = {
    0: "Balanced",
    1: "My prompt is more important",
    2: "ControlNet is more important",
    "0": "Balanced",
    "1": "My prompt is more important",
    "2": "ControlNet is more important",
}

_RESIZE_MODE_MAP = {
    0: "Just Resize",
    1: "Crop and Resize",
    2: "Resize and Fill",
    "0": "Just Resize",
    "1": "Crop and Resize",
    "2": "Resize and Fill",
}


def normalize_controlnet_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize ControlNet units in-place to current v3 API values."""
    scripts = payload.get("alwayson_scripts")
    if not isinstance(scripts, dict):
        return payload

    controlnet = scripts.get("controlnet") or scripts.get("ControlNet")
    if not isinstance(controlnet, dict):
        return payload

    args = controlnet.get("args")
    if not isinstance(args, list):
        return payload

    for unit in args:
        if not isinstance(unit, dict):
            continue
        mode = unit.get("control_mode")
        if mode in _CONTROL_MODE_MAP:
            unit["control_mode"] = _CONTROL_MODE_MAP[mode]
        resize = unit.get("resize_mode")
        if resize in _RESIZE_MODE_MAP:
            unit["resize_mode"] = _RESIZE_MODE_MAP[resize]

        # ControlNet v3 defaults this API-only field to True, which can append
        # preprocessor/detected maps to API image responses. ComicFrame never
        # consumes those maps; disabling them shrinks response payloads and
        # keeps the img2img response unambiguous.
        if unit.get("enabled", True):
            unit["save_detected_map"] = False
    return payload


class ControlNetV3CompatMixin:
    """Normalize the fully-built img2img payload before it leaves ComicFrame."""

    def _build_payload(self, frame_path, settings, width, height, frame_number):
        payload = super()._build_payload(frame_path, settings, width, height, frame_number)
        return normalize_controlnet_payload(payload)
