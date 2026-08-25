#!/usr/bin/env python3
"""Render Intelligence / efficiency layer for ComicFrame Studio v2.5.

The renderer has enough quality systems. v2.5 makes them spend work more
intelligently on RTX 3060-class hardware:

- Fast / Balanced / Quality project performance modes
- shot difficulty analysis and adaptive diffusion steps / inference edge
- one raw optical-flow solve reused by Shot Memory and post-render transport
- persistent flow cache across reruns
- automatic one-frame OOM downgrade from 1024/native to 768
- explicit render-plan metadata and selective invalidation when the plan changes

Easy Mode exposes one human choice: Performance. Everything else is automatic.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import replace
from pathlib import Path
from typing import Any

import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageChops, ImageFilter, ImageOps, ImageStat

import comicframe_optical_flow as flow
from comicframe_director import ORIGINAL, resolve_shot
from comicframe_reference_lock import reference_plan_signature


PERFORMANCE_MODES = ("Fast", "Balanced", "Quality")
DEFAULT_PERFORMANCE = "Balanced"

RESOLUTION_LABELS = {
    768: "768 long edge · emergency / low VRAM",
    1024: "1024 long edge · fast / stable",
    1280: "1280 long edge · recommended",
    0: "Source / native · heavy",
}

POLICIES: dict[str, dict[str, tuple[int, int]]] = {
    # tier -> (long edge, diffusion step target)
    "Fast": {
        "easy": (768, 16),
        "moderate": (768, 19),
        "hard": (768, 22),
    },
    "Balanced": {
        "easy": (768, 18),
        "moderate": (1024, 22),
        "hard": (1024, 26),
    },
    "Quality": {
        "easy": (1024, 22),
        "moderate": (1024, 26),
        "hard": (1024, 30),
    },
}


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def difficulty_tier(score: float) -> str:
    value = _clamp(score)
    if value < 0.42:
        return "easy"
    if value < 0.72:
        return "moderate"
    return "hard"


def difficulty_score(motion: float, detail: float, intensity: float, subject_lock: str) -> float:
    """Combine cheap source metrics with the artistic workload requested."""
    lock_bonus = 0.10 if subject_lock == "Locked" else 0.05 if subject_lock == "Strong" else 0.0
    return _clamp(
        0.36 * _clamp(motion)
        + 0.24 * _clamp(detail)
        + 0.30 * _clamp(intensity)
        + lock_bonus
    )


def policy_for(mode: str, tier: str, original: bool = False) -> dict[str, Any]:
    mode = mode if mode in PERFORMANCE_MODES else DEFAULT_PERFORMANCE
    if original:
        return {
            "mode": mode,
            "tier": "bypass",
            "long_edge": 0,
            "resolution": RESOLUTION_LABELS[0],
            "steps": 0,
            "flow_quality": False,
            "gpu": False,
        }
    tier = tier if tier in {"easy", "moderate", "hard"} else "moderate"
    long_edge, steps = POLICIES[mode][tier]
    return {
        "mode": mode,
        "tier": tier,
        "long_edge": long_edge,
        "resolution": RESOLUTION_LABELS[long_edge],
        "steps": steps,
        "flow_quality": bool(mode == "Quality" and tier == "hard"),
        "gpu": True,
    }


def efficiency_frame_signature(timeline: dict[str, Any], frame_number: int) -> str:
    """Reference-aware frame signature plus v2.5 render-plan decisions."""
    reference = reference_plan_signature(timeline, frame_number)
    shot = resolve_shot(timeline, frame_number) or {}
    directive = shot.get("render_intelligence") if isinstance(shot, dict) else None
    root = timeline.get("render_intelligence") if isinstance(timeline, dict) else None
    compact = {
        "reference": reference,
        "mode": str((root or {}).get("mode") or ""),
        "tier": str((directive or {}).get("tier") or ""),
        "long_edge": int((directive or {}).get("long_edge") or 0),
        "steps": int((directive or {}).get("steps") or 0),
    }
    return hashlib.sha256(json.dumps(compact, sort_keys=True).encode("utf-8")).hexdigest()


def _image_proxy(path: Path, long_edge: int = 288) -> Image.Image:
    with Image.open(path) as source:
        image = source.convert("L")
        w, h = image.size
        longest = max(w, h)
        if longest > long_edge:
            scale = long_edge / float(longest)
            image = image.resize(
                (max(1, round(w * scale)), max(1, round(h * scale))),
                Image.Resampling.BILINEAR,
            )
        return image.copy()


def source_frame_metrics(paths: list[Path]) -> tuple[float, float]:
    """Return normalized motion and edge/detail metrics from a few source frames."""
    existing = [path for path in paths if path.exists()]
    if not existing:
        return 0.0, 0.0
    proxies = [_image_proxy(path) for path in existing]
    details: list[float] = []
    for image in proxies:
        edges = image.filter(ImageFilter.FIND_EDGES)
        stat = ImageStat.Stat(edges)
        raw = float(stat.mean[0]) / 255.0 + float(stat.stddev[0]) / 255.0
        details.append(_clamp(raw / 0.42))
    motions: list[float] = []
    for previous, current in zip(proxies, proxies[1:]):
        if current.size != previous.size:
            current = current.resize(previous.size, Image.Resampling.BILINEAR)
        raw = float(ImageStat.Stat(ImageChops.difference(previous, current)).mean[0]) / 255.0
        motions.append(_clamp(raw / 0.24))
    return (
        sum(motions) / len(motions) if motions else 0.0,
        sum(details) / len(details) if details else 0.0,
    )


class RenderIntelligenceMixin:
    """Spend GPU/CPU work per shot instead of treating every frame identically."""

    def _build_ui(self):
        self.performance_mode_var = tk.StringVar(value=DEFAULT_PERFORMANCE)
        self.efficiency_status_var = tk.StringVar(value="Render Intelligence · plan not built")
        self.efficiency_flow_status_var = tk.StringVar(value="Flow cache · 0 hit / 0 miss")
        self.efficiency_oom_retry_var = tk.BooleanVar(value=True)
        self._efficiency_plan_dirty = True
        self._efficiency_active_directive: dict[str, Any] | None = None
        self._transport_cache_mem: dict[str, tuple[Any, Any]] = {}
        self._transport_cache_order: list[str] = []
        self._flow_cache_hits = 0
        self._flow_cache_misses = 0
        self._efficiency_retry_count = 0
        super()._build_ui()
        self._augment_efficiency_workspace()
        try:
            self.after(0, self._refresh_efficiency_status)
        except Exception:
            pass

    # ---------- paths / UI ----------

    def project_paths(self):
        paths = super().project_paths()
        root = paths["root"]
        paths.update({
            "efficiency": root / "cache" / "render_intelligence",
            "flow_cache": root / "cache" / "flow",
            "analysis_cache": root / "cache" / "analysis",
            "render_plan": root / "cache" / "render_intelligence" / "render_plan.json",
            "shot_features": root / "cache" / "analysis" / "shot_features.json",
        })
        return paths

    def _augment_efficiency_workspace(self) -> None:
        card = getattr(self, "workspace_card", None)
        if card is None:
            return
        box = ttk.LabelFrame(card, text="Performance · v2.5", padding=8)
        box.pack(fill="x", pady=(8, 0))
        row = ttk.Frame(box, style="Panel.TFrame")
        row.pack(fill="x")
        ttk.Label(row, text="Performance", style="Panel.TLabel").pack(side="left")
        combo = ttk.Combobox(
            row,
            textvariable=self.performance_mode_var,
            values=PERFORMANCE_MODES,
            state="readonly",
            width=12,
        )
        combo.pack(side="left", padx=6)
        combo.bind("<<ComboboxSelected>>", lambda _event: self._efficiency_mode_changed())
        ttk.Label(row, textvariable=self.efficiency_status_var, style="Muted.TLabel").pack(side="left", padx=8)
        ttk.Checkbutton(
            row,
            text="Retry OOM at 768",
            variable=self.efficiency_oom_retry_var,
        ).pack(side="right")
        ttk.Label(box, textvariable=self.efficiency_flow_status_var, style="Muted.TLabel").pack(anchor="w", pady=(4, 0))
        ttk.Label(
            box,
            text=(
                "Fast favors 768 and fewer steps. Balanced spends 1024 only on moderate/hard shots. "
                "Quality favors 1024. Optical-flow transport is cached and reused by both Shot Memory and temporal stabilization."
            ),
            style="Muted.TLabel",
            wraplength=740,
        ).pack(anchor="w", pady=(4, 0))

    def _efficiency_mode_changed(self) -> None:
        old_rendered = None
        try:
            old_rendered = self._rendered_timeline_for_workspace()
        except Exception:
            old_rendered = None
        self._efficiency_plan_dirty = True
        try:
            self._ensure_efficiency_plan(force=True)
            if old_rendered:
                invalidated = self._invalidate_changed_timeline_frames(old_rendered, self._director_timeline)
                if invalidated:
                    self._log(f"Render Intelligence: performance mode invalidated {invalidated} affected frame(s).")
            self._workspace_refresh_all()
        except Exception as exc:
            self._log(f"Render Intelligence plan refresh skipped: {exc}")
        self._refresh_efficiency_status()

    def _save_director_timeline(self) -> None:
        result = super()._save_director_timeline()
        self._efficiency_plan_dirty = True
        return result

    # ---------- source analysis ----------

    def _source_fingerprint(self) -> str:
        video_text = self.video_var.get().strip() if hasattr(self, "video_var") else ""
        video = Path(video_text).expanduser() if video_text else None
        payload: dict[str, Any] = {"video": str(video or "")}
        if video and video.exists():
            stat = video.stat()
            payload.update({"size": int(stat.st_size), "mtime_ns": int(stat.st_mtime_ns)})
        timeline = getattr(self, "_director_timeline", {}) or {}
        payload["total_frames"] = int(timeline.get("total_frames") or 0)
        payload["shots"] = [
            [int(s.get("id", 0)), int(s.get("start", 0)), int(s.get("end", 0))]
            for s in timeline.get("shots", [])
            if isinstance(s, dict)
        ]
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

    @staticmethod
    def _sample_shot_numbers(shot: dict[str, Any], count: int = 5) -> list[int]:
        start, end = int(shot["start"]), int(shot["end"])
        if end <= start:
            return [start]
        count = max(2, min(count, end - start + 1))
        return sorted({int(round(start + i * (end - start) / float(count - 1))) for i in range(count)})

    def _load_feature_cache(self) -> dict[str, Any]:
        path = self.project_paths()["shot_features"]
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_feature_cache(self, data: dict[str, Any]) -> None:
        path = self.project_paths()["shot_features"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _source_features_for_shots(self) -> dict[int, dict[str, float]]:
        timeline = self._director_timeline
        fingerprint = self._source_fingerprint()
        cached = self._load_feature_cache()
        if cached.get("source_fingerprint") == fingerprint and isinstance(cached.get("shots"), dict):
            out: dict[int, dict[str, float]] = {}
            for key, value in cached["shots"].items():
                if isinstance(value, dict):
                    out[int(key)] = {
                        "motion": float(value.get("motion") or 0.0),
                        "detail": float(value.get("detail") or 0.0),
                    }
            if out:
                return out

        frames_dir = self.project_paths()["frames"]
        out: dict[int, dict[str, float]] = {}
        for shot in timeline.get("shots", []):
            numbers = self._sample_shot_numbers(shot)
            paths = [frames_dir / f"frame_{number:06d}.png" for number in numbers]
            motion, detail = source_frame_metrics(paths)
            out[int(shot["id"])] = {"motion": round(motion, 6), "detail": round(detail, 6)}
        self._save_feature_cache({
            "version": "2.5",
            "source_fingerprint": fingerprint,
            "shots": {str(key): value for key, value in out.items()},
        })
        return out

    def _build_efficiency_plan(self) -> dict[str, Any]:
        timeline = self._director_timeline
        mode = self.performance_mode_var.get() if self.performance_mode_var.get() in PERFORMANCE_MODES else DEFAULT_PERFORMANCE
        features = self._source_features_for_shots()
        counts = {"easy": 0, "moderate": 0, "hard": 0, "bypass": 0}
        plan_shots: list[dict[str, Any]] = []

        for shot in timeline.get("shots", []):
            shot_id = int(shot["id"])
            style = str(shot.get("style") or "")
            original = style == ORIGINAL
            metrics = features.get(shot_id, {"motion": 0.0, "detail": 0.0})
            intensity = max(
                float(shot.get("intensity_start") or 0.0),
                float(shot.get("intensity_end") or 0.0),
            )
            score = 0.0 if original else difficulty_score(
                metrics["motion"], metrics["detail"], intensity, str(shot.get("subject_lock") or "Normal")
            )
            tier = "bypass" if original else difficulty_tier(score)
            directive = policy_for(mode, tier if tier != "bypass" else "easy", original=original)
            directive.update({
                "shot": shot_id,
                "score": round(score, 4),
                "motion": round(float(metrics["motion"]), 4),
                "detail": round(float(metrics["detail"]), 4),
                "intensity": round(float(intensity), 4),
            })
            shot["render_intelligence"] = copy.deepcopy(directive)
            plan_shots.append(copy.deepcopy(directive))
            counts[directive["tier"]] = counts.get(directive["tier"], 0) + 1

        root_plan = {
            "version": "2.5",
            "mode": mode,
            "source_fingerprint": self._source_fingerprint(),
            "flow_cache": "raw transport, confidence floor applied on read",
            "oom_retry": bool(self.efficiency_oom_retry_var.get()),
            "counts": counts,
            "shots": plan_shots,
        }
        timeline["render_intelligence"] = {
            "version": "2.5",
            "mode": mode,
            "source_fingerprint": root_plan["source_fingerprint"],
        }
        path = self.project_paths()["render_plan"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(root_plan, indent=2), encoding="utf-8")
        # Auto-generated metadata should not pollute Undo history.
        try:
            timeline_path = self._timeline_path()
            timeline_path.parent.mkdir(parents=True, exist_ok=True)
            timeline_path.write_text(json.dumps(timeline, indent=2), encoding="utf-8")
        except Exception:
            pass
        self._efficiency_plan_dirty = False
        return root_plan

    def _ensure_efficiency_plan(self, force: bool = False) -> dict[str, Any]:
        timeline = self._director_timeline if getattr(self, "_director_timeline", {}).get("shots") else self._load_director_timeline(silent=True)
        if not timeline.get("shots"):
            return {"version": "2.5", "mode": self.performance_mode_var.get(), "counts": {}}
        existing = timeline.get("render_intelligence") if isinstance(timeline, dict) else None
        mode = self.performance_mode_var.get()
        if force or self._efficiency_plan_dirty or not isinstance(existing, dict) or existing.get("mode") != mode:
            return self._build_efficiency_plan()
        path = self.project_paths()["render_plan"]
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("mode") == mode:
                    return data
            except Exception:
                pass
        return self._build_efficiency_plan()

    def _directive_for_frame(self, frame_number: int) -> dict[str, Any] | None:
        self._ensure_efficiency_plan()
        shot = resolve_shot(self._director_timeline, int(frame_number))
        if not shot:
            return None
        directive = shot.get("render_intelligence")
        return copy.deepcopy(directive) if isinstance(directive, dict) else None

    # ---------- raw optical-flow cache ----------

    @staticmethod
    def _transport_key(prev_gray, cur_gray, quality: bool) -> str:
        digest = hashlib.sha256()
        digest.update(b"quality" if quality else b"fast")
        digest.update(str(prev_gray.shape).encode("ascii"))
        digest.update(str(cur_gray.shape).encode("ascii"))
        digest.update(prev_gray.tobytes(order="C"))
        digest.update(cur_gray.tobytes(order="C"))
        return digest.hexdigest()

    def _transport_cache_path(self, key: str) -> Path | None:
        try:
            path = self.project_paths()["flow_cache"] / f"{key}.npz"
            path.parent.mkdir(parents=True, exist_ok=True)
            return path
        except Exception:
            return None

    def _remember_transport(self, key: str, flow_backward, confidence_raw) -> None:
        self._transport_cache_mem[key] = (flow_backward, confidence_raw)
        if key in self._transport_cache_order:
            self._transport_cache_order.remove(key)
        self._transport_cache_order.append(key)
        while len(self._transport_cache_order) > 12:
            stale = self._transport_cache_order.pop(0)
            self._transport_cache_mem.pop(stale, None)

    def _raw_transport(self, prev_gray, cur_gray, quality: bool):
        cv2, np = flow.cv2, flow.np
        key = self._transport_key(prev_gray, cur_gray, quality)
        cached = self._transport_cache_mem.get(key)
        if cached is not None:
            self._flow_cache_hits += 1
            return cached

        cache_path = self._transport_cache_path(key)
        if cache_path is not None and cache_path.exists():
            try:
                with np.load(cache_path, allow_pickle=False) as data:
                    flow_backward = data["flow"].astype(np.float32)
                    confidence_raw = data["confidence"].astype(np.float32)
                self._remember_transport(key, flow_backward, confidence_raw)
                self._flow_cache_hits += 1
                return flow_backward, confidence_raw
            except Exception:
                try:
                    cache_path.unlink()
                except Exception:
                    pass

        self._flow_cache_misses += 1
        flow_forward = flow.OpticalFlowTemporalMixin._farneback(prev_gray, cur_gray, quality)
        flow_backward = flow.OpticalFlowTemporalMixin._farneback(cur_gray, prev_gray, quality)
        h, w = cur_gray.shape[:2]
        gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
        map_x = gx + flow_backward[..., 0]
        map_y = gy + flow_backward[..., 1]
        valid = (
            (map_x >= 0.0)
            & (map_x <= float(w - 1))
            & (map_y >= 0.0)
            & (map_y <= float(h - 1))
        ).astype(np.float32)
        sampled_fx = cv2.remap(
            flow_forward[..., 0], map_x, map_y, cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT, borderValue=0,
        )
        sampled_fy = cv2.remap(
            flow_forward[..., 1], map_x, map_y, cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT, borderValue=0,
        )
        fb_error = np.sqrt(
            (flow_backward[..., 0] + sampled_fx) ** 2
            + (flow_backward[..., 1] + sampled_fy) ** 2
        )
        motion = np.sqrt(flow_backward[..., 0] ** 2 + flow_backward[..., 1] ** 2)
        tolerance = (1.0 if quality else 1.5) + 0.06 * motion
        confidence_fb = np.exp(-((fb_error / np.maximum(tolerance, 1e-3)) ** 2))
        warped_prev_gray = cv2.remap(
            prev_gray, map_x, map_y, cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REFLECT101,
        )
        photo_error = cv2.absdiff(cur_gray, warped_prev_gray).astype(np.float32)
        photo_sigma = 24.0 if quality else 30.0
        confidence_photo = np.exp(-((photo_error / photo_sigma) ** 2))
        confidence_raw = np.sqrt(np.clip(confidence_fb * confidence_photo, 0.0, 1.0)) * valid
        confidence_raw = cv2.GaussianBlur(
            confidence_raw, (0, 0), sigmaX=1.1 if quality else 1.4
        ).astype(np.float32)
        flow_backward = flow_backward.astype(np.float32)
        self._remember_transport(key, flow_backward, confidence_raw)

        if cache_path is not None:
            tmp = cache_path.with_suffix(".npz.part")
            try:
                with tmp.open("wb") as handle:
                    np.savez(handle, flow=flow_backward, confidence=confidence_raw)
                tmp.replace(cache_path)
            except Exception:
                try:
                    tmp.unlink()
                except Exception:
                    pass
        return flow_backward, confidence_raw

    def _estimate_transport(self, prev_gray, cur_gray, quality: bool, confidence_floor: float):
        if flow.cv2 is None or flow.np is None:
            return super()._estimate_transport(prev_gray, cur_gray, quality, confidence_floor)
        np = flow.np
        flow_backward, confidence_raw = self._raw_transport(prev_gray, cur_gray, quality)
        floor = max(0.0, min(0.9, float(confidence_floor)))
        confidence = np.clip(
            (confidence_raw - floor) / max(1e-6, 1.0 - floor),
            0.0,
            1.0,
        ).astype(np.float32)
        self._refresh_flow_cache_status()
        return flow_backward, confidence

    def _refresh_flow_cache_status(self) -> None:
        text = f"Flow cache · {self._flow_cache_hits} hit / {self._flow_cache_misses} miss"
        try:
            self.after(0, lambda value=text: self.efficiency_flow_status_var.set(value))
        except Exception:
            try:
                self.efficiency_flow_status_var.set(text)
            except Exception:
                pass

    # ---------- adaptive per-frame render ----------

    def _apply_frame_direction(self, style_name: str, intensity: float, settings):
        directed_settings, saved = super()._apply_frame_direction(style_name, intensity, settings)
        directive = self._efficiency_active_directive or {}
        target = int(directive.get("steps") or 0)
        if target > 0:
            mode = str(directive.get("mode") or DEFAULT_PERFORMANCE)
            if mode == "Quality":
                steps = max(int(directed_settings.steps), target)
            else:
                steps = min(int(directed_settings.steps), target)
            directed_settings = replace(directed_settings, steps=max(12, int(steps)))
        return directed_settings, saved

    @staticmethod
    def _is_oom_error(exc: Exception) -> bool:
        low = str(exc).lower()
        return any(token in low for token in (
            "cuda out of memory",
            "outofmemory",
            "out of vram",
            "not enough memory",
            "allocation on device",
        ))

    def _apply_runtime_directive(self, directive: dict[str, Any]) -> dict[str, Any]:
        saved: dict[str, Any] = {}
        for name in ("inference_mode_var", "temporal_engine_var", "control_low_vram_var"):
            var = getattr(self, name, None)
            if var is not None and hasattr(var, "get") and hasattr(var, "set"):
                saved[name] = var.get()
        resolution = str(directive.get("resolution") or "")
        if resolution and hasattr(self, "inference_mode_var"):
            self.inference_mode_var.set(resolution)
        if hasattr(self, "temporal_engine_var"):
            self.temporal_engine_var.set(
                flow.FLOW_QUALITY if bool(directive.get("flow_quality")) else flow.FLOW_FAST
            )
        return saved

    @staticmethod
    def _restore_runtime_vars(obj, saved: dict[str, Any]) -> None:
        for name, value in saved.items():
            var = getattr(obj, name, None)
            try:
                var.set(value)
            except Exception:
                pass

    def _render_one(self, frame_path, out_path, settings, width, height, frame_number):
        directive = self._directive_for_frame(int(frame_number))
        if not directive:
            return super()._render_one(frame_path, out_path, settings, width, height, frame_number)
        saved = self._apply_runtime_directive(directive)
        self._efficiency_active_directive = directive
        try:
            try:
                return super()._render_one(frame_path, out_path, settings, width, height, frame_number)
            except Exception as exc:
                should_retry = (
                    bool(self.efficiency_oom_retry_var.get())
                    and self._is_oom_error(exc)
                    and bool(directive.get("gpu", True))
                    and int(directive.get("long_edge") or 0) != 768
                )
                if not should_retry:
                    raise
                retry = dict(directive)
                retry.update({
                    "long_edge": 768,
                    "resolution": RESOLUTION_LABELS[768],
                    "steps": max(14, int(directive.get("steps") or 22) - 4),
                    "flow_quality": False,
                    "oom_retry": True,
                })
                self._efficiency_retry_count += 1
                self._log(
                    f"Render Intelligence: frame {frame_number} hit VRAM limit at "
                    f"{directive.get('long_edge')} · retrying once at 768 / {retry['steps']} steps."
                )
                try:
                    path = Path(out_path)
                    if path.exists():
                        path.unlink()
                except Exception:
                    pass
                self._restore_runtime_vars(self, saved)
                retry_saved = self._apply_runtime_directive(retry)
                if hasattr(self, "control_low_vram_var"):
                    self.control_low_vram_var.set(True)
                self._efficiency_active_directive = retry
                try:
                    return super()._render_one(frame_path, out_path, settings, width, height, frame_number)
                finally:
                    self._restore_runtime_vars(self, retry_saved)
        finally:
            self._restore_runtime_vars(self, saved)
            self._efficiency_active_directive = None

    # ---------- lifecycle / invalidation / status ----------

    def _analyze_shots(self):
        timeline = super()._analyze_shots()
        self._efficiency_plan_dirty = True
        self._ensure_efficiency_plan(force=True)
        self._refresh_efficiency_status()
        return timeline

    def _invalidate_changed_timeline_frames(self, old: dict[str, Any], new: dict[str, Any]) -> int:
        # v2.4 and older rendered timelines have no efficiency plan. Preserve
        # those already-completed frames; their old settings were at least as
        # expensive as the new adaptive path, and future v2.5 changes will be
        # tracked once the rendered timeline is updated.
        if not isinstance(old.get("render_intelligence"), dict):
            return super()._invalidate_changed_timeline_frames(old, new)

        total = max(int(old.get("total_frames") or 0), int(new.get("total_frames") or 0))
        styled = self.project_paths()["styled"]
        changed = 0
        for frame_number in range(1, total + 1):
            if efficiency_frame_signature(old, frame_number) == efficiency_frame_signature(new, frame_number):
                continue
            candidate = styled / f"frame_{frame_number:06d}.png"
            if candidate.exists():
                candidate.unlink()
                changed += 1
        if changed:
            memory_root = self.project_paths()["root"] / "shot_memory" / "full"
            if memory_root.exists():
                import shutil
                shutil.rmtree(memory_root)
        return changed

    def _render_range(self, start, count, test_only):
        self._ensure_efficiency_plan()
        mode = self.performance_mode_var.get()
        self._log(f"Render Intelligence v2.5: mode={mode} · adaptive resolution/steps · persistent raw-flow cache")
        return super()._render_range(start, count, test_only)

    def _refresh_efficiency_status(self) -> None:
        try:
            plan = self._ensure_efficiency_plan() if getattr(self, "_director_timeline", {}).get("shots") else None
        except Exception:
            plan = None
        if not plan:
            text = f"{self.performance_mode_var.get()} · analyze shots to build plan"
        else:
            counts = plan.get("counts") or {}
            text = (
                f"{plan.get('mode', self.performance_mode_var.get())} · "
                f"{counts.get('easy', 0)} easy / {counts.get('moderate', 0)} moderate / "
                f"{counts.get('hard', 0)} hard / {counts.get('bypass', 0)} bypass"
            )
        try:
            self.efficiency_status_var.set(text)
        except Exception:
            pass

    def _workspace_refresh_all(self) -> None:
        result = super()._workspace_refresh_all()
        self._refresh_efficiency_status()
        return result

    def _workspace_runtime_health_text(self) -> str:
        base = super()._workspace_runtime_health_text()
        return f"{base} · Performance {self.performance_mode_var.get()}"

    def _render_profile(self) -> dict:
        profile = super()._render_profile()
        timeline = getattr(self, "_director_timeline", {}) or {}
        profile["render_intelligence"] = {
            "version": "2.5",
            "mode": self.performance_mode_var.get(),
            "adaptive_steps": True,
            "adaptive_resolution": True,
            "raw_flow_cache": True,
            "oom_retry_768": bool(self.efficiency_oom_retry_var.get()),
            "plan_mode": str((timeline.get("render_intelligence") or {}).get("mode") or ""),
        }
        return profile
