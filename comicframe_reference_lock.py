#!/usr/bin/env python3
"""Reference / identity conditioning for ComicFrame Studio v2.3.

Easy Mode exposes only Normal / Strong / Locked. The runtime capability-detects
what the connected ControlNet installation can actually do and chooses the best
safe backend in this order:

    compatible IP-Adapter -> reference-only -> Shot Memory fallback

References are strictly shot-local. Geometry remains owned by the existing
Canny ControlNet unit; reference conditioning is appended as a separate unit.
"""
from __future__ import annotations

import hashlib
import json
import math
import shutil
from pathlib import Path
from typing import Any

import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps, ImageStat

from comicframe_director import (
    ORIGINAL,
    STYLE_TO_LOOK,
    frame_plan_signature,
    resolve_frame_plan,
    resolve_shot,
)


SUBJECT_LEVELS = ("Normal", "Strong", "Locked")
BACKEND_AUTO = "Auto"
BACKEND_IP = "IP-Adapter"
BACKEND_REFERENCE = "Reference only"
BACKEND_MEMORY = "Shot Memory"
BACKEND_CHOICES = (BACKEND_AUTO, BACKEND_IP, BACKEND_REFERENCE, BACKEND_MEMORY)


def reference_plan_signature(timeline: dict[str, Any], frame_number: int) -> str:
    """Frame signature including v2.3 identity/reference state."""
    shot = resolve_shot(timeline, frame_number) or {}
    compact = {
        "director": frame_plan_signature(timeline, frame_number),
        "subject_lock": str(shot.get("subject_lock") or "Normal"),
        "reference_frame": int(shot.get("reference_frame") or 0),
        "reference_backend": str(shot.get("reference_backend_resolved") or ""),
        "reference_model": str(shot.get("reference_model") or ""),
    }
    return hashlib.sha256(json.dumps(compact, sort_keys=True).encode("utf-8")).hexdigest()


class ReferenceLockMixin:
    """Add shot-local reference conditioning without complicating Easy Mode."""

    def _build_ui(self):
        # These exist before the v2.2 Director builds and potentially loads a
        # project timeline, so selected-shot refreshes can safely update them.
        self.reference_level_var = tk.StringVar(value="Strong")
        self.reference_backend_override_var = tk.StringVar(value=BACKEND_AUTO)
        self.reference_status_var = tk.StringVar(value="Subject Lock · probing local capabilities…")
        self.reference_shot_status_var = tk.StringVar(value="Reference · analyze shots first")
        self._reference_caps: dict[str, Any] = {}
        self._reference_last_backend = BACKEND_MEMORY
        super()._build_ui()
        try:
            self.director_card.configure(text="3 · Easy Shot Director · v2.3")
        except Exception:
            pass
        self._augment_easy_reference_controls()
        self.after(0, lambda: self._director_load_selected_shot())

    def _build_continuity_card(self):
        super()._build_continuity_card()
        card = self._panel(self.left, "4 · Reference Lock · v2.3 advanced")
        card.pack(fill="x", pady=8)
        row = ttk.Frame(card, style="Panel.TFrame")
        row.pack(fill="x")
        ttk.Label(row, text="Backend", style="Panel.TLabel").pack(side="left")
        ttk.Combobox(
            row,
            textvariable=self.reference_backend_override_var,
            values=BACKEND_CHOICES,
            state="readonly",
            width=18,
        ).pack(side="left", padx=6)
        ttk.Button(row, text="Probe", command=lambda: self._run_worker(self._refresh_reference_capabilities)).pack(side="left")
        ttk.Label(row, textvariable=self.reference_status_var, style="Muted.TLabel").pack(side="left", padx=10)
        ttk.Label(
            card,
            text=(
                "Auto prefers a compatible IP-Adapter model, then ControlNet reference-only, then the built-in Shot Memory fallback. "
                "The normal Canny unit always keeps the current source frame as its geometry input."
            ),
            style="Muted.TLabel",
            wraplength=760,
        ).pack(anchor="w", pady=(6, 0))

    def _augment_easy_reference_controls(self) -> None:
        card = getattr(self, "director_card", None)
        if card is None:
            return
        box = ttk.LabelFrame(card, text="Subject consistency", padding=8)
        box.pack(fill="x", pady=(10, 0))
        row = ttk.Frame(box, style="Panel.TFrame")
        row.pack(fill="x")
        ttk.Label(row, text="Keep person / product", style="Panel.TLabel").pack(side="left")
        combo = ttk.Combobox(
            row,
            textvariable=self.reference_level_var,
            values=SUBJECT_LEVELS,
            state="readonly",
            width=10,
        )
        combo.pack(side="left", padx=6)
        combo.bind("<<ComboboxSelected>>", lambda _event: self._reference_level_changed())
        ttk.Label(row, textvariable=self.reference_shot_status_var, style="Muted.TLabel").pack(side="left", padx=8)
        ttk.Button(row, text="Try another reference", command=self._reference_next_clicked).pack(side="right")
        ttk.Label(
            box,
            text="Normal = maximum freedom · Strong = recommended · Locked = prioritize recognizable subject and product shape.",
            style="Muted.TLabel",
            wraplength=740,
        ).pack(anchor="w", pady=(5, 0))

    # ---------- Capability detection ----------

    @staticmethod
    def _clean_model_name(name: str) -> str:
        return (name or "").split("[")[0].strip()

    def _ip_model_score(self, name: str, wants_xl: bool) -> int:
        low = self._clean_model_name(name).lower()
        if "ip-adapter" not in low and "ip_adapter" not in low:
            return -10000
        is_xl = "sdxl" in low or "_xl" in low or "xl_" in low
        is_15 = "sd15" in low or "sd1.5" in low
        if wants_xl and not is_xl:
            return -10000
        if not wants_xl and is_xl:
            return -10000
        # FaceID/PuLID variants may require auxiliary LoRAs/InsightFace. Do not
        # silently auto-select them; generic CLIP IP-Adapter is the safe path.
        if "faceid" in low or "face-id" in low or "pulid" in low:
            return -10000
        score = 10
        if "plus-face" in low or "plus_face" in low:
            score += 50
        elif "plus" in low and "composition" not in low:
            score += 40
        elif "full-face" in low or "full_face" in low:
            score += 35
        elif "vit-h" in low or "vit_h" in low:
            score += 25
        if "composition" in low:
            score -= 20
        if is_15 and not wants_xl:
            score += 10
        if is_xl and wants_xl:
            score += 10
        return score

    @staticmethod
    def _find_reference_module(modules: list[str]) -> str | None:
        for name in modules:
            low = name.lower().replace("-", "_")
            if low == "reference_only" or "reference_only" in low:
                return name
        return None

    def _refresh_reference_capabilities(self) -> dict[str, Any]:
        models: list[str] = []
        modules: list[str] = []
        try:
            if hasattr(self, "_direct_controlnet_inventory"):
                models, modules = self._direct_controlnet_inventory()
        except Exception as exc:
            self._log(f"Reference Lock inventory fallback: {exc}")

        if not models:
            try:
                models = list(self.control_model_combo["values"] or [])
            except Exception:
                models = []
        if not modules:
            try:
                modules = list(self.control_module_combo["values"] or [])
            except Exception:
                modules = []

        checkpoint = self.checkpoint_var.get().strip() if hasattr(self, "checkpoint_var") else ""
        wants_xl = bool(self._looks_sdxl(checkpoint)) if hasattr(self, "_looks_sdxl") else ("xl" in checkpoint.lower())
        auto_module = next((m for m in modules if m.lower() == "ip-adapter-auto"), None)
        ip_models = sorted(
            ((self._ip_model_score(name, wants_xl), name) for name in models),
            reverse=True,
        )
        ip_models = [(score, name) for score, name in ip_models if score > -10000]
        ip_model = ip_models[0][1] if auto_module and ip_models else None
        reference_module = self._find_reference_module(modules)

        caps = {
            "checkpoint": checkpoint,
            "family": "SDXL" if wants_xl else "SD1.x",
            "ip_adapter": bool(auto_module and ip_model),
            "ip_module": auto_module or "",
            "ip_model": ip_model or "",
            "reference_only": bool(reference_module),
            "reference_module": reference_module or "",
            "shot_memory": True,
            "models": len(models),
            "modules": len(modules),
        }
        self._reference_caps = caps

        if caps["ip_adapter"]:
            summary = f"Subject Lock ready · IP-Adapter · {caps['family']}"
        elif caps["reference_only"]:
            summary = f"Subject Lock ready · reference-only · {caps['family']}"
        else:
            summary = "Subject Lock standard · Shot Memory fallback"
        try:
            self.after(0, lambda text=summary: self.reference_status_var.set(text))
        except Exception:
            self.reference_status_var.set(summary)
        self._log(
            "Reference Lock probe: "
            f"family={caps['family']}, ip_adapter={'yes' if caps['ip_adapter'] else 'no'}, "
            f"reference_only={'yes' if caps['reference_only'] else 'no'}, fallback=Shot Memory"
        )
        return caps

    def _choose_reference_backend(self, level: str) -> tuple[str, str, str]:
        if level == "Normal":
            return BACKEND_MEMORY, "", ""
        caps = self._reference_caps or self._refresh_reference_capabilities()
        requested = self.reference_backend_override_var.get().strip() if hasattr(self, "reference_backend_override_var") else BACKEND_AUTO

        def auto_choice() -> tuple[str, str, str]:
            if caps.get("ip_adapter"):
                return BACKEND_IP, str(caps.get("ip_module") or "ip-adapter-auto"), str(caps.get("ip_model") or "")
            if caps.get("reference_only"):
                return BACKEND_REFERENCE, str(caps.get("reference_module") or "reference_only"), "None"
            return BACKEND_MEMORY, "", ""

        if requested == BACKEND_AUTO:
            return auto_choice()
        if requested == BACKEND_IP and caps.get("ip_adapter"):
            return BACKEND_IP, str(caps.get("ip_module") or "ip-adapter-auto"), str(caps.get("ip_model") or "")
        if requested == BACKEND_REFERENCE and caps.get("reference_only"):
            return BACKEND_REFERENCE, str(caps.get("reference_module") or "reference_only"), "None"
        if requested == BACKEND_MEMORY:
            return BACKEND_MEMORY, "", ""
        self._log(f"Reference Lock backend '{requested}' unavailable; falling back automatically.")
        return auto_choice()

    def _sync_webui(self):
        result = super()._sync_webui()
        try:
            self._refresh_reference_capabilities()
        except Exception as exc:
            self._log(f"Reference Lock capability probe skipped: {exc}")
        return result

    # ---------- Reference selection ----------

    @staticmethod
    def _reference_candidate_numbers(start: int, end: int, limit: int = 7) -> list[int]:
        start, end = int(start), int(end)
        if end <= start:
            return [start]
        length = end - start + 1
        if length <= limit:
            return list(range(start, end + 1))
        lo = start + max(1, int(round(length * 0.12)))
        hi = end - max(1, int(round(length * 0.12)))
        if hi < lo:
            lo, hi = start, end
        if limit <= 1:
            return [(lo + hi) // 2]
        values = {int(round(lo + i * (hi - lo) / float(limit - 1))) for i in range(limit)}
        return sorted(values)

    @staticmethod
    def _reference_frame_score(path: Path, shot_start: int, shot_end: int) -> float:
        frame_number = int("".join(ch for ch in path.stem if ch.isdigit()) or 0)
        with Image.open(path) as source:
            gray = ImageOps.contain(source.convert("L"), (320, 320), Image.Resampling.BILINEAR)
            edges = gray.filter(ImageFilter.FIND_EDGES)
            edge_stat = ImageStat.Stat(edges)
            detail = float(edge_stat.mean[0]) / 255.0 + float(edge_stat.stddev[0]) / 255.0

        motion = 0.0
        samples = 0
        for neighbor_number in (frame_number - 1, frame_number + 1):
            if neighbor_number < shot_start or neighbor_number > shot_end:
                continue
            neighbor = path.parent / f"frame_{neighbor_number:06d}.png"
            if not neighbor.exists():
                continue
            with Image.open(path) as a, Image.open(neighbor) as b:
                aa = ImageOps.contain(a.convert("L"), (240, 240), Image.Resampling.BILINEAR)
                bb = ImageOps.contain(b.convert("L"), aa.size, Image.Resampling.BILINEAR)
                if bb.size != aa.size:
                    bb = bb.resize(aa.size, Image.Resampling.BILINEAR)
                motion += float(ImageStat.Stat(ImageChops.difference(aa, bb)).mean[0]) / 255.0
                samples += 1
        motion = motion / samples if samples else 0.0
        half = max(1.0, (shot_end - shot_start) / 2.0)
        boundary = min(frame_number - shot_start, shot_end - frame_number) / half
        return detail + 0.35 * max(0.0, boundary) - 0.85 * motion

    def _score_reference_candidates(self, shot: dict[str, Any]) -> list[int]:
        frames_dir = self.project_paths()["frames"]
        start, end = int(shot["start"]), int(shot["end"])
        candidates = self._reference_candidate_numbers(start, end)
        scored: list[tuple[float, int]] = []
        for number in candidates:
            path = frames_dir / f"frame_{number:06d}.png"
            if not path.exists():
                continue
            try:
                scored.append((self._reference_frame_score(path, start, end), number))
            except Exception:
                scored.append((0.0, number))
        scored.sort(key=lambda item: (item[0], -abs(item[1] - (start + end) / 2.0)), reverse=True)
        return [number for _score, number in scored] or [(start + end) // 2]

    def _ensure_reference_metadata(self, save: bool = True) -> bool:
        timeline = self._director_timeline if getattr(self, "_director_timeline", {}).get("shots") else self._load_director_timeline(silent=True)
        changed = False
        for shot in timeline.get("shots", []):
            if str(shot.get("style") or "") == ORIGINAL:
                if shot.get("subject_lock") != "Normal":
                    shot["subject_lock"] = "Normal"
                    changed = True
            elif str(shot.get("subject_lock") or "") not in SUBJECT_LEVELS:
                shot["subject_lock"] = "Strong"
                changed = True

            candidates = shot.get("reference_candidates")
            valid_candidates = [int(x) for x in candidates] if isinstance(candidates, list) and candidates else []
            start, end = int(shot["start"]), int(shot["end"])
            valid_candidates = [x for x in valid_candidates if start <= x <= end]
            if not valid_candidates:
                valid_candidates = self._score_reference_candidates(shot)
                shot["reference_candidates"] = valid_candidates
                changed = True
            reference = int(shot.get("reference_frame") or 0)
            if reference not in valid_candidates:
                shot["reference_frame"] = int(valid_candidates[0])
                changed = True

        if changed and save:
            self._save_director_timeline()
        return changed

    def _resolve_timeline_reference_backends(self, save: bool = True) -> bool:
        self._ensure_reference_metadata(save=False)
        changed = False
        for shot in self._director_timeline.get("shots", []):
            level = str(shot.get("subject_lock") or "Normal")
            if str(shot.get("style") or "") == ORIGINAL or level == "Normal":
                backend, module, model = BACKEND_MEMORY, "", ""
            else:
                backend, module, model = self._choose_reference_backend(level)
            updates = {
                "reference_backend_resolved": backend,
                "reference_module": module,
                "reference_model": model,
            }
            for key, value in updates.items():
                if shot.get(key) != value:
                    shot[key] = value
                    changed = True
        if changed and save:
            self._save_director_timeline()
        return changed

    def _analyze_shots(self) -> dict[str, Any]:
        timeline = super()._analyze_shots()
        self._ensure_reference_metadata(save=False)
        self._resolve_timeline_reference_backends(save=False)
        self._save_director_timeline()
        self._log("Reference Lock: selected one stable source reference per shot.")
        return timeline

    def _save_director_timeline(self) -> None:
        super()._save_director_timeline()
        # v2.2 owns the base file writer and stamps its own version. Rewrite only
        # the version marker after it finishes so old v2.2 timelines stay readable.
        try:
            self._director_timeline["version"] = "2.3"
            path = self._timeline_path()
            path.write_text(json.dumps(self._director_timeline, indent=2), encoding="utf-8")
        except Exception:
            pass

    # ---------- Easy shot editing ----------

    def _director_load_selected_shot(self) -> None:
        super()._director_load_selected_shot()
        shot = self._selected_shot() if hasattr(self, "_selected_shot") else None
        if not shot:
            if hasattr(self, "reference_shot_status_var"):
                self.reference_shot_status_var.set("Reference · analyze shots first")
            return
        level = str(shot.get("subject_lock") or ("Normal" if str(shot.get("style")) == ORIGINAL else "Strong"))
        if level not in SUBJECT_LEVELS:
            level = "Strong"
        self.reference_level_var.set(level)
        ref = int(shot.get("reference_frame") or 0)
        backend = str(shot.get("reference_backend_resolved") or BACKEND_MEMORY)
        self.reference_shot_status_var.set(f"Reference frame {ref or 'auto'} · {backend}")

    def _reference_level_changed(self) -> None:
        shot = self._selected_shot()
        if not shot:
            return
        shot["subject_lock"] = self.reference_level_var.get()
        self._resolve_timeline_reference_backends(save=False)
        self._save_director_timeline()
        self._director_load_selected_shot()

    def _director_apply_selected_shot(self) -> None:
        shot = self._selected_shot()
        if shot:
            shot["subject_lock"] = self.reference_level_var.get()
            if not shot.get("reference_frame"):
                self._ensure_reference_metadata(save=False)
            self._resolve_timeline_reference_backends(save=False)
        super()._director_apply_selected_shot()
        self._director_load_selected_shot()

    def _reference_next_clicked(self) -> None:
        shot = self._selected_shot()
        if not shot:
            return
        self._ensure_reference_metadata(save=False)
        candidates = [int(x) for x in shot.get("reference_candidates", [])]
        if not candidates:
            return
        current = int(shot.get("reference_frame") or candidates[0])
        try:
            index = candidates.index(current)
        except ValueError:
            index = -1
        shot["reference_frame"] = candidates[(index + 1) % len(candidates)]
        self._save_director_timeline()
        self._director_load_selected_shot()
        self._log(f"Reference Lock: shot {shot['id']} reference -> frame {shot['reference_frame']}")

    # ---------- Request conditioning ----------

    def _reference_path_for_shot(self, shot: dict[str, Any]) -> Path | None:
        frame = int(shot.get("reference_frame") or 0)
        if frame <= 0:
            return None
        path = self.project_paths()["frames"] / f"frame_{frame:06d}.png"
        return path if path.exists() else None

    @staticmethod
    def _reference_weight(level: str, backend: str) -> float:
        if backend == BACKEND_IP:
            return 0.82 if level == "Locked" else 0.62
        if backend == BACKEND_REFERENCE:
            return 0.72 if level == "Locked" else 0.52
        return 0.0

    def _append_reference_unit(
        self,
        payload: dict[str, Any],
        reference_path: Path,
        level: str,
        backend: str,
        module: str,
        model: str,
    ) -> None:
        b64 = self._encode_file(reference_path)
        scripts = payload.setdefault("alwayson_scripts", {})
        if not isinstance(scripts, dict):
            return
        controlnet = scripts.get("controlnet") or scripts.get("ControlNet")
        if not isinstance(controlnet, dict):
            controlnet = {"args": []}
            scripts["controlnet"] = controlnet
        args = controlnet.setdefault("args", [])
        if not isinstance(args, list):
            return
        args.append({
            "enabled": True,
            "module": module,
            "model": model,
            "weight": self._reference_weight(level, backend),
            "image": b64,
            "resize_mode": "Crop and Resize",
            "low_vram": bool(self.control_low_vram_var.get()) if hasattr(self, "control_low_vram_var") else False,
            "processor_res": -1,
            "threshold_a": -1,
            "threshold_b": -1,
            "guidance_start": 0.0,
            "guidance_end": 1.0,
            "control_mode": "Balanced",
            "pixel_perfect": False,
            "save_detected_map": False,
        })

    def _build_payload(self, frame_path, settings, width, height, frame_number):
        timeline = self._director_timeline if getattr(self, "_director_timeline", {}).get("shots") else self._load_director_timeline(silent=True)
        shot = resolve_shot(timeline, int(frame_number)) if timeline else None
        level = str((shot or {}).get("subject_lock") or "Normal")
        style = str((shot or {}).get("style") or "")
        if not shot or style == ORIGINAL or level == "Normal":
            return super()._build_payload(frame_path, settings, width, height, frame_number)

        backend = str(shot.get("reference_backend_resolved") or "")
        module = str(shot.get("reference_module") or "")
        model = str(shot.get("reference_model") or "")
        if not backend:
            backend, module, model = self._choose_reference_backend(level)

        # ReferenceLock sits outside ShotMemory in the canonical MRO. This lets
        # the fallback temporarily strengthen Shot Memory before super() builds
        # its conditioned init image, then restore the user-facing values.
        memory_saved: list[tuple[Any, Any]] = []
        if backend == BACKEND_MEMORY:
            targets = (
                ("shot_memory_strength_var", 0.44 if level == "Locked" else 0.32),
                ("shot_palette_strength_var", 0.22 if level == "Locked" else 0.15),
            )
            for name, minimum in targets:
                var = getattr(self, name, None)
                if var is not None and hasattr(var, "get") and hasattr(var, "set"):
                    old = var.get()
                    memory_saved.append((var, old))
                    var.set(max(float(old), minimum))

        try:
            payload = super()._build_payload(frame_path, settings, width, height, frame_number)
        finally:
            for var, old in memory_saved:
                try:
                    var.set(old)
                except Exception:
                    pass

        reference_path = self._reference_path_for_shot(shot)
        if backend in {BACKEND_IP, BACKEND_REFERENCE} and reference_path is not None and module:
            self._append_reference_unit(payload, reference_path, level, backend, module, model or "None")
            self._reference_last_backend = backend
        else:
            self._reference_last_backend = BACKEND_MEMORY
        return payload

    # ---------- Reference-aware preview ----------

    def _make_reference_contact_sheet(self, rows_data: list[tuple[Path, Path, Path, str]]) -> Path:
        thumb_w, thumb_h = 320, 190
        header_h = 30
        label_h = 34
        columns = ("SOURCE", "REFERENCE", "RESULT")
        sheet = Image.new(
            "RGB",
            (thumb_w * 3, header_h + len(rows_data) * (thumb_h + label_h)),
            (18, 19, 24),
        )
        draw = ImageDraw.Draw(sheet)
        for col, title in enumerate(columns):
            draw.text((col * thumb_w + 8, 8), title, fill=(238, 241, 247))
        for row_index, (source_path, ref_path, result_path, label) in enumerate(rows_data):
            y = header_h + row_index * (thumb_h + label_h)
            for col, path in enumerate((source_path, ref_path, result_path)):
                with Image.open(path) as src:
                    image = ImageOps.contain(src.convert("RGB"), (thumb_w, thumb_h), Image.Resampling.LANCZOS)
                x = col * thumb_w + (thumb_w - image.width) // 2
                py = y + (thumb_h - image.height) // 2
                sheet.paste(image, (x, py))
            draw.text((8, y + thumb_h + 8), label[:100], fill=(238, 241, 247))
        target = self.project_paths()["root"] / "DIRECTOR_PREVIEW.jpg"
        target.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(target, format="JPEG", quality=92)
        return target

    def _director_preflight(self) -> None:
        super()._director_preflight()
        self._refresh_reference_capabilities()
        self._ensure_reference_metadata(save=False)
        self._resolve_timeline_reference_backends(save=True)

    def _preview_director_plan(self) -> None:
        timeline = self._ensure_director_timeline()
        info = self._extract_frames()
        self._director_preflight()
        frames_dir = self.project_paths()["frames"]
        preview_dir = self.project_paths()["root"] / "director_preview_frames"
        if preview_dir.exists():
            shutil.rmtree(preview_dir)
        preview_dir.mkdir(parents=True, exist_ok=True)
        shots = self._representative_shots(list(timeline.get("shots", [])))
        settings = self._settings()
        rendered: list[tuple[Path, Path, Path, str]] = []
        self._director_preview_mode = True
        try:
            for idx, shot in enumerate(shots, 1):
                if self.stop_event.is_set():
                    break
                frame_number = (int(shot["start"]) + int(shot["end"])) // 2
                source = frames_dir / f"frame_{frame_number:06d}.png"
                ref = self._reference_path_for_shot(shot) or source
                out = preview_dir / f"shot_{int(shot['id']):04d}.png"
                self._log(f"Reference preview [{idx}/{len(shots)}] shot {shot['id']} frame {frame_number}")
                self._render_one(source, out, settings, int(info["width"]), int(info["height"]), frame_number)
                plan = resolve_frame_plan(timeline, frame_number)
                look = STYLE_TO_LOOK.get(str(plan["style"]), str(plan["style"]))
                level = str(shot.get("subject_lock") or "Normal")
                backend = str(shot.get("reference_backend_resolved") or BACKEND_MEMORY)
                rendered.append((source, ref, out, f"Shot {shot['id']} · {look} · {level} · {backend}"))
                self._set_progress(10 + (idx / max(1, len(shots))) * 80, f"Preview {idx}/{len(shots)}")
        finally:
            self._director_preview_mode = False
        if not rendered:
            raise RuntimeError("No preview frames were rendered.")
        sheet = self._make_reference_contact_sheet(rendered)
        self.after(0, lambda p=sheet: self._show_image(p, self.output_preview, "output"))
        self.after(0, lambda: self.output_preview_status.set("Source / Reference / Result"))
        self._set_progress(100, f"Preview ready · {sheet.name}")
        self._log(f"Reference Lock preview: {sheet}")

    # ---------- Resume / lifecycle ----------

    def _invalidate_changed_timeline_frames(self, old: dict[str, Any], new: dict[str, Any]) -> int:
        total = max(int(old.get("total_frames") or 0), int(new.get("total_frames") or 0))
        styled = self.project_paths()["styled"]
        changed = 0
        for frame_number in range(1, total + 1):
            if reference_plan_signature(old, frame_number) == reference_plan_signature(new, frame_number):
                continue
            candidate = styled / f"frame_{frame_number:06d}.png"
            if candidate.exists():
                candidate.unlink()
                changed += 1
        if changed:
            memory_root = self.project_paths()["root"] / "shot_memory" / "full"
            if memory_root.exists():
                shutil.rmtree(memory_root)
        return changed

    @staticmethod
    def _profile_without_director(profile: dict[str, Any]) -> dict[str, Any]:
        copy = json.loads(json.dumps(profile))
        copy.pop("shot_director", None)
        copy.pop("reference_lock", None)
        return copy

    def _render_profile(self) -> dict:
        profile = super()._render_profile()
        caps = self._reference_caps or {}
        profile["reference_lock"] = {
            "version": "2.3",
            "backend_policy": "IP-Adapter -> reference-only -> Shot Memory",
            "backend_override": self.reference_backend_override_var.get() if hasattr(self, "reference_backend_override_var") else BACKEND_AUTO,
            "capability_family": str(caps.get("family") or "unknown"),
            "geometry_isolation": "reference unit separate from untouched current-source Canny unit",
            "shot_local": True,
        }
        return profile

    def _render_range(self, start, count, test_only):
        self._ensure_director_timeline()
        self._refresh_reference_capabilities()
        self._ensure_reference_metadata(save=False)
        self._resolve_timeline_reference_backends(save=True)
        locked = sum(
            1 for shot in self._director_timeline.get("shots", [])
            if str(shot.get("subject_lock") or "Normal") in {"Strong", "Locked"}
            and str(shot.get("style") or "") != ORIGINAL
        )
        self._log(
            f"Reference Lock v2.3: {locked} directed shot(s) with subject consistency · "
            f"best backend={self._choose_reference_backend('Strong')[0]}"
        )
        return super()._render_range(start, count, test_only)
