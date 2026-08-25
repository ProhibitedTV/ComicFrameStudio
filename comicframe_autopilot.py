#!/usr/bin/env python3
"""AutoPilot orchestration for ComicFrame Studio v2.7.

The default product contract is intentionally small:

    choose video -> choose treatment/performance -> ANALYZE + RENDER -> final MP4

AutoPilot coordinates the existing Director, Subject Library, Render Intelligence,
Reference Lock, Shot Memory and ControlNet layers. It does not replace them.
"""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Callable

import tkinter as tk
from tkinter import messagebox, ttk
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps, ImageStat

from comicframe_director import ORIGINAL, TREATMENTS, apply_treatment, resolve_shot
from comicframe_reference_lock import BACKEND_MEMORY, reference_plan_signature
from comicframe_subjects import subject_dependency_signature

AUTOPILOT_VERSION = "2.7"
AUTOPILOT_MODES = ("Safe", "Balanced", "Wild")
DEFAULT_AUTOPILOT_MODE = "Balanced"


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def autopilot_subject_threshold(mode: str) -> float:
    # Full-frame similarity is intentionally conservative. AutoPilot only
    # promotes a recurring subject when representative shots are genuinely close.
    return {"Safe": 0.95, "Balanced": 0.92, "Wild": 0.88}.get(mode, 0.92)


def autopilot_style_guard(intensity: float, motion: float, mode: str) -> float:
    """Reduce artistic strength only when source motion makes it risky."""
    value = _clamp(intensity)
    motion = _clamp(motion)
    if mode == "Wild":
        return value
    pressure = max(0.0, motion - 0.55)
    factor = 0.90 if mode == "Safe" else 0.68
    return _clamp(value - pressure * factor * 0.30)


def _proxy(path: Path, edge: int = 192) -> Image.Image | None:
    if not path.exists():
        return None
    with Image.open(path) as image:
        image = image.convert("RGB")
        w, h = image.size
        longest = max(w, h)
        if longest > edge:
            scale = edge / float(longest)
            image = image.resize(
                (max(1, round(w * scale)), max(1, round(h * scale))),
                Image.Resampling.BILINEAR,
            )
        return image.copy()


def representative_similarity(a: Path, b: Path) -> float:
    """Cheap deterministic similarity for high-confidence recurring-subject hints."""
    one = _proxy(a)
    two = _proxy(b)
    if one is None or two is None:
        return 0.0
    two = two.resize(one.size, Image.Resampling.BILINEAR)
    gray_a = one.convert("L")
    gray_b = two.convert("L")
    diff = float(ImageStat.Stat(ImageChops.difference(gray_a, gray_b)).mean[0]) / 255.0
    edge_a = gray_a.filter(ImageFilter.FIND_EDGES)
    edge_b = gray_b.filter(ImageFilter.FIND_EDGES)
    edge_diff = float(ImageStat.Stat(ImageChops.difference(edge_a, edge_b)).mean[0]) / 255.0
    mean_a = sum(ImageStat.Stat(one).mean) / (3.0 * 255.0)
    mean_b = sum(ImageStat.Stat(two).mean) / (3.0 * 255.0)
    brightness = abs(mean_a - mean_b)
    return _clamp(1.0 - (0.58 * diff + 0.28 * edge_diff + 0.14 * brightness))


def cluster_representatives(items: list[tuple[int, Path]], threshold: float) -> list[list[int]]:
    """Greedy deterministic clustering; singletons remain shot-local."""
    clusters: list[dict[str, Any]] = []
    for shot_id, path in sorted(items, key=lambda item: int(item[0])):
        best_index = -1
        best_score = 0.0
        for index, cluster in enumerate(clusters):
            score = representative_similarity(Path(cluster["anchor"]), path)
            if score >= threshold and score > best_score:
                best_index, best_score = index, score
        if best_index < 0:
            clusters.append({"anchor": path, "shots": [int(shot_id)]})
        else:
            clusters[best_index]["shots"].append(int(shot_id))
    return [list(cluster["shots"]) for cluster in clusters if len(cluster["shots"]) >= 2]


def verify_image_sanity(path: Path) -> tuple[bool, str]:
    if not path.exists() or path.stat().st_size < 4096:
        return False, "missing or tiny output"
    try:
        with Image.open(path) as image:
            gray = image.convert("L")
            stat = ImageStat.Stat(gray)
            mean = float(stat.mean[0])
            std = float(stat.stddev[0])
            if mean < 3 or mean > 252:
                return False, "nearly blank/solid output"
            if std < 2.0:
                return False, "pathologically flat output"
        return True, "ok"
    except Exception as exc:
        return False, str(exc)


def autopilot_frame_signature(timeline: dict[str, Any], frame_number: int) -> str:
    shot = resolve_shot(timeline, int(frame_number)) or {}
    auto = shot.get("autopilot") if isinstance(shot, dict) else {}
    compact = {
        "reference": reference_plan_signature(timeline, int(frame_number)),
        "subject": subject_dependency_signature(timeline, int(frame_number)),
        "subject_group": str((auto or {}).get("subject_group") or ""),
        "guarded_intensity": round(float((auto or {}).get("guarded_intensity") or 0.0), 4),
        "mode": str((timeline.get("autopilot") or {}).get("mode") or ""),
    }
    return hashlib.sha256(json.dumps(compact, sort_keys=True).encode("utf-8")).hexdigest()


class AutoPilotMixin:
    """One-click plan/probe/render/verify orchestration over the v2 stack."""

    def _build_ui(self):
        self.autopilot_mode_var = tk.StringVar(value=DEFAULT_AUTOPILOT_MODE)
        self.autopilot_status_var = tk.StringVar(value="AutoPilot · ready")
        self.autopilot_probe_var = tk.BooleanVar(value=True)
        self._autopilot_active = False
        super()._build_ui()
        self._augment_autopilot_workspace()

    def project_paths(self):
        paths = super().project_paths()
        root = paths["root"]
        paths.update({
            "autopilot": root / "cache" / "autopilot",
            "autopilot_plan": root / "cache" / "autopilot" / "autopilot_plan.json",
            "autopilot_groups": root / "cache" / "autopilot" / "subject_groups.json",
            "autopilot_probe": root / "cache" / "autopilot" / "quality_probe.json",
            "autopilot_preview": root / "previews" / "AUTOPILOT_PROBE.jpg",
            "autopilot_verify": root / "cache" / "autopilot" / "final_verification.json",
        })
        return paths

    def _augment_autopilot_workspace(self) -> None:
        card = getattr(self, "workspace_card", None)
        if card is None:
            return
        box = ttk.LabelFrame(card, text="AutoPilot · v2.7", padding=8)
        box.pack(fill="x", pady=(8, 0))
        self.autopilot_card = box

        first = ttk.Frame(box, style="Panel.TFrame")
        first.pack(fill="x")
        ttk.Label(first, text="Treatment", style="Panel.TLabel").pack(side="left")
        ttk.Combobox(
            first,
            textvariable=self.director_treatment_var,
            values=TREATMENTS,
            state="readonly",
            width=18,
        ).pack(side="left", padx=6)
        ttk.Label(first, text="Performance", style="Panel.TLabel").pack(side="left", padx=(10, 3))
        ttk.Combobox(
            first,
            textvariable=self.performance_mode_var,
            values=("Fast", "Balanced", "Quality"),
            state="readonly",
            width=11,
        ).pack(side="left", padx=4)
        ttk.Label(first, text="Creative", style="Panel.TLabel").pack(side="left", padx=(10, 3))
        ttk.Combobox(
            first,
            textvariable=self.autopilot_mode_var,
            values=AUTOPILOT_MODES,
            state="readonly",
            width=10,
        ).pack(side="left", padx=4)

        actions = ttk.Frame(box, style="Panel.TFrame")
        actions.pack(fill="x", pady=(7, 0))
        ttk.Checkbutton(actions, text="Probe first", variable=self.autopilot_probe_var).pack(side="left")
        ttk.Button(actions, text="PREVIEW FIRST", command=self._autopilot_preview_clicked).pack(side="right", padx=(5, 0))
        ttk.Button(actions, text="ANALYZE + RENDER", style="Accent.TButton", command=self._autopilot_render_clicked).pack(side="right")
        ttk.Label(box, textvariable=self.autopilot_status_var, style="Muted.TLabel").pack(anchor="w", pady=(5, 0))
        ttk.Label(
            box,
            text="Normal workflow: choose video → treatment/performance → Analyze + Render. Shot, subject and backend controls remain optional overrides.",
            style="Muted.TLabel",
            wraplength=740,
        ).pack(anchor="w", pady=(3, 0))

    # ---------- planning ----------

    def _autopilot_representatives(self, timeline: dict[str, Any]) -> list[tuple[int, Path]]:
        frames = self.project_paths()["frames"]
        out: list[tuple[int, Path]] = []
        for shot in timeline.get("shots", []):
            number = int(shot.get("reference_frame") or 0)
            if number <= 0:
                number = (int(shot["start"]) + int(shot["end"])) // 2
            path = frames / f"frame_{number:06d}.png"
            if path.exists():
                out.append((int(shot["id"]), path))
        return out

    def _autopilot_subject_groups(self, timeline: dict[str, Any]) -> list[list[int]]:
        threshold = autopilot_subject_threshold(self.autopilot_mode_var.get())
        groups = cluster_representatives(self._autopilot_representatives(timeline), threshold)
        target = self.project_paths()["autopilot_groups"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps({"version": AUTOPILOT_VERSION, "threshold": threshold, "groups": groups}, indent=2),
            encoding="utf-8",
        )
        return groups

    def _autopilot_clear_previous_auto_assignments(self, timeline: dict[str, Any]) -> None:
        for shot in timeline.get("shots", []):
            sid = str(shot.get("subject_id") or "")
            if not sid.startswith("auto_"):
                continue
            for key in ("subject_id", "subject_reference_id", "subject_reference_hash", "subject_type_resolved"):
                shot.pop(key, None)
            auto = dict(shot.get("autopilot") or {})
            auto.pop("subject_group", None)
            shot["autopilot"] = auto

    def _autopilot_group_subject_id(self, ids: list[int]) -> str:
        fingerprint = self._source_fingerprint() if hasattr(self, "_source_fingerprint") else "source"
        payload = f"{fingerprint}|{','.join(str(int(i)) for i in sorted(ids))}"
        return "auto_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]

    def _autopilot_reference_shot(self, candidates: list[dict[str, Any]], features: dict[int, dict[str, float]]) -> dict[str, Any]:
        def key(shot: dict[str, Any]):
            metrics = features.get(int(shot["id"]), {})
            motion = float(metrics.get("motion") or 0.0)
            detail = float(metrics.get("detail") or 0.0)
            return (motion, -detail, int(shot["id"]))
        return sorted(candidates, key=key)[0]

    def _autopilot_promote_subject_groups(
        self,
        timeline: dict[str, Any],
        groups: list[list[int]],
        features: dict[int, dict[str, float]],
    ) -> int:
        """Create deterministic hidden project subjects for high-confidence groups.

        Manual assignments always win. Each auto group intentionally uses one
        strong project reference so cross-shot consistency is meaningful rather
        than selecting each shot as its own reference.
        """
        self._load_subjects(force=True)
        shots_by_id = {int(s["id"]): s for s in timeline.get("shots", [])}
        promoted = 0
        for index, ids in enumerate(groups, 1):
            candidates = [shots_by_id[i] for i in ids if i in shots_by_id and not str(shots_by_id[i].get("subject_id") or "")]
            if len(candidates) < 2:
                continue
            sid = self._autopilot_group_subject_id(ids)
            subject = self._subject_by_id(sid)
            if subject is None:
                subject = {"id": sid, "name": f"Auto Subject {index:02d}", "type": "Other", "references": []}
                self._subjects.setdefault("subjects", []).append(subject)
                self._save_subjects()
            reference_shot = self._autopilot_reference_shot(candidates, features)
            source, frame_number = self._local_source_reference_for_shot(reference_shot)
            if source is None:
                continue
            ref = self._store_subject_reference(subject, source, int(reference_shot["id"]), int(frame_number))
            for shot in candidates:
                shot["subject_id"] = sid
                shot["subject_reference_id"] = str(ref["id"])
                shot["subject_reference_hash"] = str(ref.get("sha256") or "")
                shot["subject_type_resolved"] = "Other"
                if str(shot.get("style") or "") != ORIGINAL and str(shot.get("subject_lock") or "Normal") == "Normal":
                    shot["subject_lock"] = "Strong"
                shot.setdefault("autopilot", {})["subject_group"] = sid
            promoted += 1
        self._save_subjects()
        return promoted

    def _autopilot_plan(self, timeline: dict[str, Any]) -> dict[str, Any]:
        mode = self.autopilot_mode_var.get() if self.autopilot_mode_var.get() in AUTOPILOT_MODES else DEFAULT_AUTOPILOT_MODE
        treatment = str(self.director_treatment_var.get() or timeline.get("treatment") or "Clean Comic")
        self._autopilot_clear_previous_auto_assignments(timeline)
        apply_treatment(timeline, treatment)
        timeline["treatment"] = treatment

        features = self._source_features_for_shots() if hasattr(self, "_source_features_for_shots") else {}
        groups = self._autopilot_subject_groups(timeline)
        promoted = self._autopilot_promote_subject_groups(timeline, groups, features)
        shots_out: list[dict[str, Any]] = []

        for shot in timeline.get("shots", []):
            metrics = features.get(int(shot["id"]), {})
            motion = float(metrics.get("motion") or 0.0)
            requested = max(
                float(shot.get("intensity_start") or 0.0),
                float(shot.get("intensity_end") or 0.0),
            )
            guarded = autopilot_style_guard(requested, motion, mode)
            if requested > 0 and guarded < requested:
                ratio = guarded / requested
                shot["intensity_start"] = round(float(shot.get("intensity_start") or 0.0) * ratio, 4)
                shot["intensity_end"] = round(float(shot.get("intensity_end") or 0.0) * ratio, 4)
            shot_auto = dict(shot.get("autopilot") or {})
            shot_auto.update({
                "version": AUTOPILOT_VERSION,
                "motion": round(motion, 4),
                "requested_intensity": round(requested, 4),
                "guarded_intensity": round(guarded, 4),
                "confidence": round(1.0 - min(1.0, abs(requested - guarded)), 4),
            })
            shot["autopilot"] = shot_auto
            shots_out.append({"shot": int(shot["id"]), **copy.deepcopy(shot_auto)})

        timeline["autopilot"] = {
            "version": AUTOPILOT_VERSION,
            "mode": mode,
            "treatment": treatment,
            "auto_subjects": promoted,
        }
        self._efficiency_plan_dirty = True
        try:
            self._ensure_efficiency_plan(force=True)
        except Exception as exc:
            self._log(f"AutoPilot efficiency plan fallback: {exc}")

        plan = {
            "version": AUTOPILOT_VERSION,
            "mode": mode,
            "treatment": treatment,
            "groups": groups,
            "auto_subjects": promoted,
            "shots": shots_out,
        }
        target = self.project_paths()["autopilot_plan"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(plan, indent=2), encoding="utf-8")
        self._save_director_timeline()
        return plan

    # ---------- cheap preflight probe ----------

    def _autopilot_probe_frames(self, timeline: dict[str, Any]) -> list[int]:
        shots = list(timeline.get("shots", []))
        if not shots:
            return []
        def rep(shot: dict[str, Any]) -> int:
            return int(shot.get("reference_frame") or ((int(shot["start"]) + int(shot["end"])) // 2))
        difficult = sorted(shots, key=lambda s: float((s.get("render_intelligence") or {}).get("score") or 0.0), reverse=True)
        intense = sorted(shots, key=lambda s: max(float(s.get("intensity_start") or 0), float(s.get("intensity_end") or 0)), reverse=True)
        chosen = [rep(shots[0])]
        if difficult:
            chosen.append(rep(difficult[0]))
        if intense:
            chosen.append(rep(intense[0]))
        subject_shot = next((s for s in shots if str(s.get("subject_id") or "")), None)
        if subject_shot:
            chosen.append(rep(subject_shot))
        return sorted(set(chosen))[:4]

    @staticmethod
    def _optional_reference_error(exc: Exception) -> bool:
        low = str(exc).lower()
        return any(token in low for token in (
            "ip-adapter", "ip_adapter", "reference-only", "reference only", "reference unit"
        ))

    def _with_reference_fallback(self, action: Callable[[], Any]) -> Any:
        try:
            return action()
        except Exception as exc:
            if not self._optional_reference_error(exc) or not hasattr(self, "reference_backend_override_var"):
                raise
            previous = self.reference_backend_override_var.get()
            self._log(f"AutoPilot: optional reference backend failed; retrying with Shot Memory. {exc}")
            self.reference_backend_override_var.set(BACKEND_MEMORY)
            try:
                return action()
            finally:
                self.reference_backend_override_var.set(previous)

    def _autopilot_probe_sheet(self, numbers: list[int]) -> Path | None:
        if not numbers:
            return None
        source_dir = self.project_paths()["frames"]
        test_dir = self.project_paths()["test"]
        width, height, label = 320, 180, 28
        sheet = Image.new("RGB", (width * 2, (height + label) * len(numbers)), (18, 19, 24))
        draw = ImageDraw.Draw(sheet)
        for row, number in enumerate(numbers):
            for col, path in enumerate((source_dir / f"frame_{number:06d}.png", test_dir / f"frame_{number:06d}.png")):
                if not path.exists():
                    continue
                with Image.open(path) as image:
                    thumb = ImageOps.fit(image.convert("RGB"), (width, height), Image.Resampling.LANCZOS)
                sheet.paste(thumb, (col * width, row * (height + label)))
            draw.text((8, row * (height + label) + height + 6), f"Frame {number} · SOURCE", fill=(238, 241, 247))
            draw.text((width + 8, row * (height + label) + height + 6), "AUTOPILOT RESULT", fill=(238, 241, 247))
        target = self.project_paths()["autopilot_preview"]
        target.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(target, format="JPEG", quality=91)
        return target

    def _autopilot_quality_probe(self, timeline: dict[str, Any]) -> dict[str, Any]:
        numbers = self._autopilot_probe_frames(timeline)
        results: list[dict[str, Any]] = []
        for number in numbers:
            self._with_reference_fallback(lambda n=number: self._render_range(n, 1, True))
            path = self.project_paths()["test"] / f"frame_{number:06d}.png"
            ok, reason = verify_image_sanity(path)
            results.append({"frame": number, "ok": ok, "reason": reason})
            if not ok:
                raise RuntimeError(f"AutoPilot quality probe failed on frame {number}: {reason}")
        preview = self._autopilot_probe_sheet(numbers)
        report = {
            "version": AUTOPILOT_VERSION,
            "frames": results,
            "passed": all(r["ok"] for r in results),
            "preview": str(preview or ""),
        }
        target = self.project_paths()["autopilot_probe"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report

    # ---------- final verification ----------

    @staticmethod
    def _ffprobe_json(path: Path) -> dict[str, Any]:
        cp = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration", "-of", "json", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        data = json.loads(cp.stdout or "{}")
        return data if isinstance(data, dict) else {}

    def _autopilot_verify_final(self) -> dict[str, Any]:
        paths = self.project_paths()
        final = Path(paths["final"])
        source = Path(self.video_var.get().strip()).expanduser().resolve()
        if not final.exists() or final.stat().st_size < 8192:
            raise RuntimeError("AutoPilot render finished but FINAL_STYLED.mp4 is missing or unexpectedly small.")
        source_probe = self._ffprobe_json(source)
        final_probe = self._ffprobe_json(final)
        source_duration = float((source_probe.get("format") or {}).get("duration") or 0.0)
        final_duration = float((final_probe.get("format") or {}).get("duration") or 0.0)
        if source_duration > 0 and abs(final_duration - source_duration) > max(1.0, source_duration * 0.06):
            raise RuntimeError(f"Final duration looks wrong: source {source_duration:.2f}s vs output {final_duration:.2f}s")
        source_streams = list(source_probe.get("streams") or [])
        final_streams = list(final_probe.get("streams") or [])
        source_has_audio = any(str(s.get("codec_type")) == "audio" for s in source_streams)
        final_has_audio = any(str(s.get("codec_type")) == "audio" for s in final_streams)
        if source_has_audio and not final_has_audio:
            raise RuntimeError("Source has audio but final video does not.")
        final_video = next((s for s in final_streams if str(s.get("codec_type")) == "video"), {})
        report = {
            "version": AUTOPILOT_VERSION,
            "file": str(final),
            "bytes": int(final.stat().st_size),
            "duration": final_duration,
            "width": int(final_video.get("width") or 0),
            "height": int(final_video.get("height") or 0),
            "audio_restored": bool(final_has_audio),
            "verified": True,
        }
        target = paths["autopilot_verify"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report

    # ---------- one-click jobs ----------

    def _autopilot_prepare(self) -> tuple[dict[str, Any], dict[str, Any]]:
        self._set_progress(2, "AutoPilot · extracting/analyzing")
        self._extract_frames()
        timeline = self._analyze_shots()
        plan = self._autopilot_plan(timeline)
        self._set_progress(8, "AutoPilot · plan ready")
        return timeline, plan

    def _autopilot_preview_clicked(self) -> None:
        if not self.video_var.get().strip():
            messagebox.showwarning("ComicFrame Studio", "Choose a source video first.")
            return
        self._run_worker(self._autopilot_preview_job)

    def _autopilot_preview_job(self) -> None:
        try:
            timeline, plan = self._autopilot_prepare()
            probe = self._autopilot_quality_probe(timeline)
            preview = Path(str(probe.get("preview") or ""))
            if preview.exists():
                self.after(0, lambda p=preview: self._show_image(p, self.output_preview, "output"))
                self.after(0, lambda: self.output_preview_status.set("AutoPilot Probe"))
            self.autopilot_status_var.set(
                f"READY · {len(timeline.get('shots', []))} shots · {plan.get('auto_subjects', 0)} auto continuity group(s)"
            )
            self._set_progress(100, "AutoPilot preview ready")
            self.after(0, self._workspace_refresh_all)
        except Exception as exc:
            self._workspace_show_error(exc)

    def _autopilot_render_clicked(self) -> None:
        if not self.video_var.get().strip():
            messagebox.showwarning("ComicFrame Studio", "Choose a source video first.")
            return
        self._run_worker(self._autopilot_render_job)

    def _autopilot_render_job(self) -> None:
        self._autopilot_active = True
        try:
            timeline, plan = self._autopilot_prepare()
            if bool(self.autopilot_probe_var.get()):
                self._set_progress(10, "AutoPilot · quality probe")
                self._autopilot_quality_probe(timeline)
            self.autopilot_status_var.set(
                f"RENDERING · {len(timeline.get('shots', []))} shots · {plan.get('auto_subjects', 0)} auto continuity group(s)"
            )
            self._with_reference_fallback(lambda: self._render_range(1, None, False))
            verified = self._autopilot_verify_final()
            self.autopilot_status_var.set(
                f"RENDER COMPLETE ✓ · {Path(verified['file']).name} · {verified.get('width', 0)}×{verified.get('height', 0)}"
            )
            self._set_progress(100, "AutoPilot render complete")
            self.after(0, self._workspace_refresh_all)
        except Exception as exc:
            self.autopilot_status_var.set("ACTION NEEDED")
            self._workspace_show_error(exc)
        finally:
            self._autopilot_active = False

    # ---------- compatibility / profile ----------

    def _invalidate_changed_timeline_frames(self, old: dict[str, Any], new: dict[str, Any]) -> int:
        changed = super()._invalidate_changed_timeline_frames(old, new)
        # v2.6 timelines have no AutoPilot metadata; preserve them on upgrade.
        if not isinstance(old.get("autopilot"), dict):
            return changed
        styled = self.project_paths()["styled"]
        total = max(int(old.get("total_frames") or 0), int(new.get("total_frames") or 0))
        extra = 0
        for frame_number in range(1, total + 1):
            if autopilot_frame_signature(old, frame_number) == autopilot_frame_signature(new, frame_number):
                continue
            candidate = styled / f"frame_{frame_number:06d}.png"
            if candidate.exists():
                candidate.unlink()
                extra += 1
        return changed + extra

    def _render_profile(self) -> dict:
        profile = super()._render_profile()
        profile["autopilot"] = {
            "version": AUTOPILOT_VERSION,
            "mode": self.autopilot_mode_var.get(),
            "probe_first": bool(self.autopilot_probe_var.get()),
            "orchestration": "analyze -> plan -> optional probe -> render -> verify",
        }
        return profile
