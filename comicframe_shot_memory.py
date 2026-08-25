#!/usr/bin/env python3
"""Shot-level style memory for ComicFrame Studio v2.0.

v1.9 transports style after diffusion.  v2.0 closes the loop by also transporting
trusted parts of the prior stylized frame into the next img2img init image before
diffusion, while leaving the ControlNet source image untouched.  The result is a
source-faithful current frame whose diffusion starting point already remembers how
the shot was being drawn.
"""
from __future__ import annotations

import base64
import json
import shutil
from io import BytesIO
from pathlib import Path

import tkinter as tk
from tkinter import ttk
from PIL import Image

import comicframe_optical_flow as flow


class ShotMemoryMixin:
    """Pre-diffusion temporal memory plus persistent per-shot reference anchors."""

    def _build_ui(self):
        self.shot_memory_enabled_var = tk.BooleanVar(value=True)
        self.shot_memory_strength_var = tk.DoubleVar(value=0.22)
        self.shot_palette_strength_var = tk.DoubleVar(value=0.10)
        self.shot_anchor_interval_var = tk.IntVar(value=24)
        self.shot_memory_confidence_var = tk.DoubleVar(value=0.45)
        self.shot_memory_status_var = tk.StringVar(
            value=(
                "Pre-diffusion shot memory ready"
                if flow.cv2 is not None and flow.np is not None
                else "OpenCV unavailable · shot memory disabled, normal render path remains usable"
            )
        )
        self._shot_memory_scope = "full"
        self._shot_memory_outdir: Path | None = None
        self._shot_memory_start_frame = 1
        self._shot_memory_manifest: dict = {"version": "2.0", "anchors": []}
        self._shot_memory_cut_frames: set[int] = set()
        self._shot_memory_last_applied_frame: int | None = None
        super()._build_ui()

    def _build_continuity_card(self):
        result = super()._build_continuity_card()
        card = self._panel(self.left, "4C · Shot memory · v2.0")
        card.pack(fill="x", pady=(0, 8))

        top = ttk.Frame(card, style="Panel.TFrame")
        top.pack(fill="x")
        ttk.Checkbutton(
            top,
            text="Feed transported style memory into the next diffusion frame",
            variable=self.shot_memory_enabled_var,
        ).pack(side="left")
        ttk.Label(top, text="Memory", style="Panel.TLabel").pack(side="left", padx=(14, 3))
        ttk.Spinbox(
            top,
            textvariable=self.shot_memory_strength_var,
            from_=0.0,
            to=0.60,
            increment=0.02,
            width=7,
        ).pack(side="left")
        ttk.Label(top, text="Palette", style="Panel.TLabel").pack(side="left", padx=(12, 3))
        ttk.Spinbox(
            top,
            textvariable=self.shot_palette_strength_var,
            from_=0.0,
            to=0.40,
            increment=0.02,
            width=7,
        ).pack(side="left")

        lower = ttk.Frame(card, style="Panel.TFrame")
        lower.pack(fill="x", pady=(6, 0))
        ttk.Label(lower, text="Anchor every", style="Panel.TLabel").pack(side="left")
        ttk.Spinbox(
            lower,
            textvariable=self.shot_anchor_interval_var,
            from_=1,
            to=300,
            increment=1,
            width=7,
        ).pack(side="left", padx=(4, 2))
        ttk.Label(lower, text="frames", style="Muted.TLabel").pack(side="left")
        ttk.Label(lower, text="Confidence floor", style="Panel.TLabel").pack(side="left", padx=(14, 3))
        ttk.Spinbox(
            lower,
            textvariable=self.shot_memory_confidence_var,
            from_=0.0,
            to=0.90,
            increment=0.05,
            width=7,
        ).pack(side="left")

        ttk.Label(
            card,
            text=(
                "Shot Memory is different from the v1.9 temporal lock: it acts before Stable Diffusion. "
                "The previous stylized frame is optical-flow warped into the current source geometry and blended only in "
                "high-confidence regions. Canny ControlNet still receives the untouched current source frame. Scene cuts reset "
                "memory automatically, while periodic shot anchors preserve longer-lived palette/style identity."
            ),
            style="Muted.TLabel",
            wraplength=760,
        ).pack(anchor="w", pady=(6, 3))
        ttk.Label(card, textvariable=self.shot_memory_status_var, style="Muted.TLabel").pack(anchor="w")
        return result

    # ---------- Persistent shot state ----------

    def _shot_memory_root(self) -> Path:
        return self.project_paths()["root"] / "shot_memory" / self._shot_memory_scope

    def _shot_memory_manifest_path(self) -> Path:
        return self._shot_memory_root() / "manifest.json"

    def _load_shot_memory_manifest(self) -> None:
        path = self._shot_memory_manifest_path()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and isinstance(data.get("anchors"), list):
                    self._shot_memory_manifest = data
                    return
            except Exception as exc:
                self._log(f"Shot Memory manifest ignored: {exc}")
        self._shot_memory_manifest = {"version": "2.0", "anchors": []}

    def _save_shot_memory_manifest(self) -> None:
        root = self._shot_memory_root()
        root.mkdir(parents=True, exist_ok=True)
        self._shot_memory_manifest["version"] = "2.0"
        self._shot_memory_manifest_path().write_text(
            json.dumps(self._shot_memory_manifest, indent=2), encoding="utf-8"
        )

    def _latest_anchor(self, frame_number: int) -> dict | None:
        anchors = self._shot_memory_manifest.get("anchors", [])
        candidates = [a for a in anchors if isinstance(a, dict) and int(a.get("frame", -1)) < frame_number]
        if not candidates:
            return None
        return max(candidates, key=lambda a: int(a.get("frame", -1)))

    def _current_shot_number(self) -> int:
        anchors = self._shot_memory_manifest.get("anchors", [])
        if not anchors:
            return 1
        return max(int(a.get("shot", 1)) for a in anchors if isinstance(a, dict))

    def _anchor_path(self, entry: dict) -> Path | None:
        name = str(entry.get("file") or "").strip()
        if not name:
            return None
        path = self._shot_memory_root() / "references" / name
        return path if path.exists() else None

    # ---------- Image helpers ----------

    @staticmethod
    def _encode_rgb_png(array) -> str:
        image = Image.fromarray(array.astype("uint8"), mode="RGB")
        buffer = BytesIO()
        image.save(buffer, format="PNG", optimize=False)
        return base64.b64encode(buffer.getvalue()).decode("ascii")

    @staticmethod
    def _palette_match(source_rgb, anchor_rgb, strength: float):
        """Soft LAB mean/std transfer; geometry is untouched, only shot-level color statistics move."""
        cv2, np = flow.cv2, flow.np
        strength = max(0.0, min(0.40, float(strength)))
        if strength <= 0.0:
            return source_rgb

        anchor = cv2.resize(anchor_rgb, (source_rgb.shape[1], source_rgb.shape[0]), interpolation=cv2.INTER_AREA)
        src_lab = cv2.cvtColor(source_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
        anc_lab = cv2.cvtColor(anchor, cv2.COLOR_RGB2LAB).astype(np.float32)
        matched = src_lab.copy()
        for channel in range(3):
            src_ch = src_lab[..., channel]
            anc_ch = anc_lab[..., channel]
            src_mean, src_std = float(src_ch.mean()), float(src_ch.std())
            anc_mean, anc_std = float(anc_ch.mean()), float(anc_ch.std())
            ratio = anc_std / max(src_std, 1.0)
            ratio = max(0.50, min(1.75, ratio))
            matched[..., channel] = (src_ch - src_mean) * ratio + anc_mean
        matched = cv2.cvtColor(np.clip(matched, 0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB)
        return np.clip(
            source_rgb.astype(np.float32) * (1.0 - strength) + matched.astype(np.float32) * strength,
            0,
            255,
        ).astype(np.uint8)

    def _flow_quality_for_memory(self) -> bool:
        try:
            return self.temporal_engine_var.get() == flow.FLOW_QUALITY
        except Exception:
            return False

    def _source_cut(self, previous_source: Path, current_source: Path) -> tuple[bool, float, float]:
        cv2 = flow.cv2
        with Image.open(previous_source) as prev_im, Image.open(current_source) as cur_im:
            prev = cv2.cvtColor(flow.np.asarray(prev_im.convert("RGB")), cv2.COLOR_RGB2GRAY)
            cur = cv2.cvtColor(flow.np.asarray(cur_im.convert("RGB")), cv2.COLOR_RGB2GRAY)
        long_edge = 768 if self._flow_quality_for_memory() else 512
        prev = self._flow_proxy(prev, long_edge)
        cur = self._flow_proxy(cur, long_edge)
        if prev.shape != cur.shape:
            prev = cv2.resize(prev, (cur.shape[1], cur.shape[0]), interpolation=cv2.INTER_AREA)
        return self._scene_cut(prev, cur, max(0.01, min(0.95, float(self.temporal_cut_var.get()))))

    # ---------- Pre-diffusion conditioning ----------

    def _build_payload(self, frame_path, settings, width, height, frame_number):
        payload = super()._build_payload(frame_path, settings, width, height, frame_number)
        if not bool(self.shot_memory_enabled_var.get()):
            return payload
        if flow.cv2 is None or flow.np is None or self._shot_memory_outdir is None:
            return payload
        if frame_number <= max(1, int(self._shot_memory_start_frame)):
            return payload

        previous_out = self._shot_memory_outdir / f"frame_{frame_number - 1:06d}.png"
        previous_source = Path(frame_path).parent / f"frame_{frame_number - 1:06d}.png"
        current_source = Path(frame_path)
        if not previous_out.exists() or not previous_source.exists():
            return payload

        try:
            cv2, np = flow.cv2, flow.np
            with Image.open(current_source) as cur_im, Image.open(previous_source) as prev_im:
                cur_rgb_full = np.asarray(cur_im.convert("RGB"))
                prev_rgb_full = np.asarray(prev_im.convert("RGB"))

            cur_gray_full = cv2.cvtColor(cur_rgb_full, cv2.COLOR_RGB2GRAY)
            prev_gray_full = cv2.cvtColor(prev_rgb_full, cv2.COLOR_RGB2GRAY)
            quality = self._flow_quality_for_memory()
            flow_edge = 768 if quality else 512
            cur_gray = self._flow_proxy(cur_gray_full, flow_edge)
            prev_gray = self._flow_proxy(prev_gray_full, flow_edge)
            if prev_gray.shape != cur_gray.shape:
                prev_gray = cv2.resize(prev_gray, (cur_gray.shape[1], cur_gray.shape[0]), interpolation=cv2.INTER_AREA)

            is_cut, mean_change, hist_corr = self._scene_cut(
                prev_gray,
                cur_gray,
                max(0.01, min(0.95, float(self.temporal_cut_var.get()))),
            )
            if is_cut:
                self._shot_memory_cut_frames.add(int(frame_number))
                self.shot_memory_status_var.set(
                    f"Shot boundary at frame {frame_number} · memory reset"
                )
                return payload

            flow_backward, confidence = self._estimate_transport(
                prev_gray,
                cur_gray,
                quality=quality,
                confidence_floor=max(0.0, min(0.90, float(self.shot_memory_confidence_var.get()))),
            )

            target_w = int(payload.get("width") or width)
            target_h = int(payload.get("height") or height)
            current_resized = cv2.resize(cur_rgb_full, (target_w, target_h), interpolation=cv2.INTER_AREA)

            latest_anchor = self._latest_anchor(frame_number)
            anchor_path = self._anchor_path(latest_anchor) if latest_anchor else None
            if anchor_path is not None:
                with Image.open(anchor_path) as anchor_im:
                    anchor_rgb = np.asarray(anchor_im.convert("RGB"))
                current_resized = self._palette_match(
                    current_resized,
                    anchor_rgb,
                    float(self.shot_palette_strength_var.get()),
                )

            with Image.open(previous_out) as prev_styled_im:
                previous_styled = np.asarray(prev_styled_im.convert("RGB"), dtype=np.uint8)
            warped_previous, confidence_full = self._warp_previous(
                previous_styled,
                flow_backward,
                confidence,
                (target_w, target_h),
            )

            memory_strength = max(0.0, min(0.60, float(self.shot_memory_strength_var.get())))
            alpha = np.clip(confidence_full * memory_strength, 0.0, 0.60)[..., None].astype(np.float32)
            conditioned = (
                current_resized.astype(np.float32) * (1.0 - alpha)
                + warped_previous.astype(np.float32) * alpha
            )
            conditioned = np.clip(conditioned, 0, 255).astype(np.uint8)

            # Only init_images changes. ControlNet's unit image was already built by
            # lower layers from the untouched current source, preserving geometry.
            payload["init_images"] = [self._encode_rgb_png(conditioned)]
            self._shot_memory_last_applied_frame = int(frame_number)
            self.shot_memory_status_var.set(
                f"Shot memory active · frame {frame_number} · {memory_strength:.2f} transported style"
            )
            return payload
        except Exception as exc:
            self._log(f"Shot Memory skipped on frame {frame_number}: {exc}")
            return payload

    # ---------- Anchor creation after the final stabilized frame ----------

    def _record_shot_anchor(self, frame_path: Path, out_path: Path, frame_number: int) -> None:
        if not bool(self.shot_memory_enabled_var.get()) or self._shot_memory_outdir is None:
            return
        anchors = self._shot_memory_manifest.setdefault("anchors", [])
        if any(int(a.get("frame", -1)) == frame_number for a in anchors if isinstance(a, dict)):
            return

        cut = frame_number in self._shot_memory_cut_frames
        last = self._latest_anchor(frame_number)
        interval = max(1, int(self.shot_anchor_interval_var.get()))
        needs_anchor = last is None or cut or (frame_number - int(last.get("frame", frame_number))) >= interval
        if not needs_anchor:
            return

        if last is None:
            shot_number = 1
            reason = "start"
        elif cut:
            shot_number = int(last.get("shot", self._current_shot_number())) + 1
            reason = "scene-cut"
        else:
            shot_number = int(last.get("shot", self._current_shot_number()))
            reason = "refresh"

        refs = self._shot_memory_root() / "references"
        refs.mkdir(parents=True, exist_ok=True)
        name = f"shot_{shot_number:04d}_anchor_{frame_number:06d}.png"
        target = refs / name
        shutil.copy2(out_path, target)
        anchors.append(
            {
                "frame": int(frame_number),
                "shot": int(shot_number),
                "reason": reason,
                "file": name,
                "style": self.preset_var.get() if hasattr(self, "preset_var") else "",
            }
        )
        anchors.sort(key=lambda a: int(a.get("frame", 0)))
        self._save_shot_memory_manifest()
        self._log(f"Shot Memory anchor: shot {shot_number} frame {frame_number} ({reason})")

    def _render_one(self, frame_path, out_path, settings, width, height, frame_number):
        result = super()._render_one(frame_path, out_path, settings, width, height, frame_number)
        try:
            self._record_shot_anchor(Path(frame_path), Path(out_path), int(frame_number))
        except Exception as exc:
            self._log(f"Shot Memory anchor skipped on frame {frame_number}: {exc}")
        return result

    # ---------- Render lifecycle / resume safety ----------

    def _render_range(self, start, count, test_only):
        self._shot_memory_scope = "test" if test_only else "full"
        self._shot_memory_start_frame = int(start)
        paths = self.project_paths()
        self._shot_memory_outdir = paths["test"] if test_only else paths["styled"]
        self._shot_memory_cut_frames = set()

        if test_only:
            root = self._shot_memory_root()
            if root.exists():
                shutil.rmtree(root)
        self._load_shot_memory_manifest()

        if bool(self.shot_memory_enabled_var.get()):
            self._log(
                "Shot Memory v2.0: "
                f"pre-diffusion={float(self.shot_memory_strength_var.get()):.2f}, "
                f"palette={float(self.shot_palette_strength_var.get()):.2f}, "
                f"anchor every {int(self.shot_anchor_interval_var.get())} frames"
            )

        try:
            return super()._render_range(start, count, test_only)
        finally:
            self._shot_memory_outdir = None

    def _render_profile(self) -> dict:
        profile = super()._render_profile()
        profile["app_version"] = "2.0"
        profile["shot_memory"] = {
            "enabled": bool(self.shot_memory_enabled_var.get()),
            "transport_strength": float(self.shot_memory_strength_var.get()),
            "palette_strength": float(self.shot_palette_strength_var.get()),
            "anchor_interval": int(self.shot_anchor_interval_var.get()),
            "confidence_floor": float(self.shot_memory_confidence_var.get()),
            "conditioning": "flow-warped prior style into img2img init; untouched source retained for ControlNet",
            "anchor_format": "periodic stabilized PNG + scene-cut reset",
        }
        return profile
