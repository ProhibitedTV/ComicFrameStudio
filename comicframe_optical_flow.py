#!/usr/bin/env python3
"""Optical-flow temporal transport for ComicFrame Studio v1.9.

The existing temporal lock can only reuse a prior stylized frame where source
pixels remain in place.  This layer estimates source motion, warps the previous
stylized frame into current-frame coordinates, rejects low-confidence/occluded
regions, and blends only the trustworthy transported style back into the new
render.  The legacy lock remains available as a fallback.
"""
from __future__ import annotations

from pathlib import Path

import tkinter as tk
from tkinter import ttk
from PIL import Image

try:
    import cv2  # type: ignore
    import numpy as np
except Exception:  # pragma: no cover - exercised by runtime fallback, not CI
    cv2 = None
    np = None


FLOW_OFF = "Off"
FLOW_BASIC = "Basic"
FLOW_FAST = "Optical Flow · Fast"
FLOW_QUALITY = "Optical Flow · Quality"
FLOW_ENGINES = [FLOW_OFF, FLOW_BASIC, FLOW_FAST, FLOW_QUALITY]


class OpticalFlowTemporalMixin:
    """Warp prior stylization along source motion before temporal blending."""

    def _build_ui(self):
        self.temporal_engine_var = tk.StringVar(value=FLOW_FAST)
        self.flow_confidence_var = tk.DoubleVar(value=0.35)
        self.flow_status_var = tk.StringVar(
            value=(
                "OpenCV optical flow ready"
                if cv2 is not None and np is not None
                else "OpenCV unavailable · optical modes fall back to Basic"
            )
        )
        self._flow_fallback_logged = False
        super()._build_ui()

    def _build_continuity_card(self):
        result = super()._build_continuity_card()
        card = self._panel(self.left, "4B · Temporal transport · v1.9")
        card.pack(fill="x", pady=(0, 8))

        row = ttk.Frame(card, style="Panel.TFrame")
        row.pack(fill="x")
        ttk.Label(row, text="Engine", width=12, style="Panel.TLabel").pack(side="left")
        combo = ttk.Combobox(
            row,
            textvariable=self.temporal_engine_var,
            values=FLOW_ENGINES,
            state="readonly",
            width=24,
        )
        combo.pack(side="left", padx=5)
        combo.bind("<<ComboboxSelected>>", lambda _event: self._on_temporal_engine_changed())

        ttk.Label(row, text="Confidence floor", style="Panel.TLabel").pack(side="left", padx=(14, 4))
        ttk.Spinbox(
            row,
            textvariable=self.flow_confidence_var,
            from_=0.0,
            to=0.9,
            increment=0.05,
            width=7,
        ).pack(side="left")

        ttk.Label(
            card,
            text=(
                "Optical Flow transports the previous stylized frame along measured source motion before blending. "
                "Forward/backward flow agreement plus a photometric check reject occlusions and newly revealed pixels. "
                "Fast computes flow near a 512px long edge; Quality uses a larger 768px flow proxy and a heavier solve."
            ),
            style="Muted.TLabel",
            wraplength=760,
        ).pack(anchor="w", pady=(6, 3))
        ttk.Label(card, textvariable=self.flow_status_var, style="Muted.TLabel").pack(anchor="w")
        return result

    def _on_temporal_engine_changed(self):
        engine = self.temporal_engine_var.get()
        if engine == FLOW_OFF:
            self.temporal_enabled_var.set(False)
        elif float(self.temporal_strength_var.get()) > 0:
            self.temporal_enabled_var.set(True)

    @staticmethod
    def _flow_proxy(gray, long_edge: int):
        h, w = gray.shape[:2]
        if max(h, w) <= long_edge:
            return gray
        scale = long_edge / float(max(h, w))
        nw = max(32, int(round(w * scale)))
        nh = max(32, int(round(h * scale)))
        return cv2.resize(gray, (nw, nh), interpolation=cv2.INTER_AREA)

    @staticmethod
    def _farneback(prev_gray, cur_gray, quality: bool):
        if quality:
            return cv2.calcOpticalFlowFarneback(
                prev_gray,
                cur_gray,
                None,
                pyr_scale=0.5,
                levels=4,
                winsize=21,
                iterations=5,
                poly_n=7,
                poly_sigma=1.5,
                flags=cv2.OPTFLOW_FARNEBACK_GAUSSIAN,
            )
        return cv2.calcOpticalFlowFarneback(
            prev_gray,
            cur_gray,
            None,
            pyr_scale=0.5,
            levels=3,
            winsize=15,
            iterations=3,
            poly_n=5,
            poly_sigma=1.2,
            flags=0,
        )

    @staticmethod
    def _scene_cut(prev_gray, cur_gray, cut_threshold: float) -> tuple[bool, float, float]:
        """Use both gross pixel change and histogram disagreement to avoid pan-as-cut errors."""
        mean_change = float(np.mean(cv2.absdiff(prev_gray, cur_gray))) / 255.0
        hist_prev = cv2.calcHist([prev_gray], [0], None, [32], [0, 256])
        hist_cur = cv2.calcHist([cur_gray], [0], None, [32], [0, 256])
        cv2.normalize(hist_prev, hist_prev)
        cv2.normalize(hist_cur, hist_cur)
        hist_corr = float(cv2.compareHist(hist_prev, hist_cur, cv2.HISTCMP_CORREL))
        is_cut = mean_change >= cut_threshold and hist_corr < 0.55
        return is_cut, mean_change, hist_corr

    @classmethod
    def _estimate_transport(cls, prev_gray, cur_gray, quality: bool, confidence_floor: float):
        """Return backward flow (current->previous) and confidence in current coordinates."""
        flow_forward = cls._farneback(prev_gray, cur_gray, quality)
        flow_backward = cls._farneback(cur_gray, prev_gray, quality)

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
            flow_forward[..., 0], map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0
        )
        sampled_fy = cv2.remap(
            flow_forward[..., 1], map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0
        )
        fb_error = np.sqrt(
            (flow_backward[..., 0] + sampled_fx) ** 2 + (flow_backward[..., 1] + sampled_fy) ** 2
        )
        motion = np.sqrt(flow_backward[..., 0] ** 2 + flow_backward[..., 1] ** 2)
        tolerance = (1.0 if quality else 1.5) + 0.06 * motion
        confidence_fb = np.exp(-((fb_error / np.maximum(tolerance, 1e-3)) ** 2))

        warped_prev_gray = cv2.remap(
            prev_gray, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT101
        )
        photo_error = cv2.absdiff(cur_gray, warped_prev_gray).astype(np.float32)
        photo_sigma = 24.0 if quality else 30.0
        confidence_photo = np.exp(-((photo_error / photo_sigma) ** 2))

        confidence = np.sqrt(np.clip(confidence_fb * confidence_photo, 0.0, 1.0)) * valid
        confidence = cv2.GaussianBlur(confidence, (0, 0), sigmaX=1.1 if quality else 1.4)

        floor = max(0.0, min(0.9, float(confidence_floor)))
        confidence = np.clip((confidence - floor) / max(1e-6, 1.0 - floor), 0.0, 1.0)
        return flow_backward.astype(np.float32), confidence.astype(np.float32)

    @staticmethod
    def _warp_previous(previous_rgb, flow_backward, confidence, out_size: tuple[int, int]):
        out_w, out_h = out_size
        flow_h, flow_w = flow_backward.shape[:2]
        sx = out_w / float(flow_w)
        sy = out_h / float(flow_h)

        fx = cv2.resize(flow_backward[..., 0], (out_w, out_h), interpolation=cv2.INTER_LINEAR) * sx
        fy = cv2.resize(flow_backward[..., 1], (out_w, out_h), interpolation=cv2.INTER_LINEAR) * sy
        gx, gy = np.meshgrid(np.arange(out_w, dtype=np.float32), np.arange(out_h, dtype=np.float32))
        map_x = gx + fx.astype(np.float32)
        map_y = gy + fy.astype(np.float32)

        warped = cv2.remap(
            previous_rgb,
            map_x,
            map_y,
            interpolation=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REFLECT101,
        )
        confidence_full = cv2.resize(confidence, (out_w, out_h), interpolation=cv2.INTER_LINEAR)
        return warped, np.clip(confidence_full, 0.0, 1.0)

    def _optical_flow_lock(self, frame_path: Path, out_path: Path, frame_number: int, quality: bool):
        if not self.temporal_enabled_var.get() or frame_number <= 1:
            return

        previous_out = out_path.parent / f"frame_{frame_number - 1:06d}.png"
        previous_source = frame_path.parent / f"frame_{frame_number - 1:06d}.png"
        if not previous_out.exists() or not previous_source.exists():
            return

        strength = max(0.0, min(0.75, float(self.temporal_strength_var.get())))
        if strength <= 0:
            return
        cut_threshold = max(0.01, min(0.95, float(self.temporal_cut_var.get())))
        confidence_floor = max(0.0, min(0.9, float(self.flow_confidence_var.get())))

        with Image.open(frame_path) as cur_src_im, Image.open(previous_source) as prev_src_im:
            cur_src = np.asarray(cur_src_im.convert("RGB"))
            prev_src = np.asarray(prev_src_im.convert("RGB"))

        cur_gray_full = cv2.cvtColor(cur_src, cv2.COLOR_RGB2GRAY)
        prev_gray_full = cv2.cvtColor(prev_src, cv2.COLOR_RGB2GRAY)
        flow_edge = 768 if quality else 512
        cur_gray = self._flow_proxy(cur_gray_full, flow_edge)
        prev_gray = self._flow_proxy(prev_gray_full, flow_edge)
        if prev_gray.shape != cur_gray.shape:
            prev_gray = cv2.resize(prev_gray, (cur_gray.shape[1], cur_gray.shape[0]), interpolation=cv2.INTER_AREA)

        is_cut, mean_change, hist_corr = self._scene_cut(prev_gray, cur_gray, cut_threshold)
        if is_cut:
            self._log(
                f"Optical flow: frame {frame_number} scene cut "
                f"(change={mean_change:.3f}, hist={hist_corr:.3f})"
            )
            return

        flow_backward, confidence = self._estimate_transport(
            prev_gray,
            cur_gray,
            quality=quality,
            confidence_floor=confidence_floor,
        )

        with Image.open(out_path) as cur_im, Image.open(previous_out) as prev_im:
            current = np.asarray(cur_im.convert("RGB"), dtype=np.float32)
            previous_pil = prev_im.convert("RGB")
            if previous_pil.size != cur_im.size:
                previous_pil = previous_pil.resize(cur_im.size, Image.Resampling.LANCZOS)
            previous = np.asarray(previous_pil, dtype=np.uint8)

        out_h, out_w = current.shape[:2]
        warped_previous, confidence_full = self._warp_previous(
            previous,
            flow_backward,
            confidence,
            (out_w, out_h),
        )
        alpha = np.clip(confidence_full * strength, 0.0, 0.75)[..., None].astype(np.float32)
        stabilized = current * (1.0 - alpha) + warped_previous.astype(np.float32) * alpha
        stabilized = np.clip(stabilized, 0, 255).astype(np.uint8)
        Image.fromarray(stabilized, mode="RGB").save(out_path, format="PNG", optimize=False)

    def _temporal_lock(self, frame_path: Path, out_path: Path, frame_number: int):
        engine = self.temporal_engine_var.get() if hasattr(self, "temporal_engine_var") else FLOW_BASIC
        if engine == FLOW_OFF:
            return
        if engine == FLOW_BASIC:
            return super()._temporal_lock(frame_path, out_path, frame_number)
        if cv2 is None or np is None:
            if not self._flow_fallback_logged:
                self._log("OpenCV optical flow unavailable; falling back to Basic temporal lock.")
                self._flow_fallback_logged = True
            return super()._temporal_lock(frame_path, out_path, frame_number)

        try:
            return self._optical_flow_lock(
                Path(frame_path),
                Path(out_path),
                frame_number,
                quality=(engine == FLOW_QUALITY),
            )
        except Exception as exc:
            self._log(f"Optical flow failed on frame {frame_number}; Basic fallback: {exc}")
            return super()._temporal_lock(frame_path, out_path, frame_number)

    def _render_profile(self) -> dict:
        profile = super()._render_profile()
        profile["app_version"] = "1.9"
        profile["optical_flow"] = {
            "engine": self.temporal_engine_var.get(),
            "confidence_floor": float(self.flow_confidence_var.get()),
            "fast_flow_long_edge": 512,
            "quality_flow_long_edge": 768,
            "transport": "backward-remap + forward/backward confidence + photometric confidence",
        }
        return profile
