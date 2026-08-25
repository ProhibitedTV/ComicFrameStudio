#!/usr/bin/env python3
"""Project-level recurring subject library for ComicFrame Studio v2.6.

v2.3 keeps a subject coherent inside one shot. v2.6 lets an explicitly assigned
person, product, prop, or other recurring subject survive scene cuts without
letting temporal memory leak across those cuts.

Easy Mode stays small: choose a subject, assign/clear it, create/add a reference,
and run a cross-shot subject check. The existing Reference Lock backend still
owns IP-Adapter/reference-only/Shot-Memory fallback behavior.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import shutil
import uuid
from pathlib import Path
from typing import Any

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps, ImageStat

from comicframe_director import ORIGINAL, STYLE_TO_LOOK, resolve_shot
from comicframe_efficiency import difficulty_tier, efficiency_frame_signature, policy_for


SUBJECT_TYPES = ("Person", "Product", "Prop", "Other")
NONE_SUBJECT = "(none)"
SUBJECT_VERSION = "2.6"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_name(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in value.strip())
    cleaned = cleaned.strip("_")
    return cleaned[:48] or "subject"


def _image_features(path: Path) -> dict[str, float]:
    """Cheap deterministic CPU features for choosing among subject references."""
    with Image.open(path) as source:
        rgb = source.convert("RGB")
        w, h = rgb.size
        gray = ImageOps.contain(rgb.convert("L"), (320, 320), Image.Resampling.BILINEAR)
        stat = ImageStat.Stat(gray)
        edges = gray.filter(ImageFilter.FIND_EDGES)
        edge_stat = ImageStat.Stat(edges)
        # Simple left/right and top/bottom energy gives a weak framing/orientation cue.
        left = gray.crop((0, 0, max(1, gray.width // 2), gray.height))
        right = gray.crop((gray.width // 2, 0, gray.width, gray.height))
        top = gray.crop((0, 0, gray.width, max(1, gray.height // 2)))
        bottom = gray.crop((0, gray.height // 2, gray.width, gray.height))
        lr = (ImageStat.Stat(right).mean[0] - ImageStat.Stat(left).mean[0]) / 255.0
        tb = (ImageStat.Stat(bottom).mean[0] - ImageStat.Stat(top).mean[0]) / 255.0
        return {
            "aspect": float(w) / max(1.0, float(h)),
            "mean": float(stat.mean[0]) / 255.0,
            "contrast": float(stat.stddev[0]) / 128.0,
            "edge": (float(edge_stat.mean[0]) + float(edge_stat.stddev[0])) / 255.0,
            "lr": lr,
            "tb": tb,
        }


def reference_match_score(source: Path, reference: Path) -> float:
    """Lower-cost similarity score used only to select an already-approved reference."""
    a = _image_features(source)
    b = _image_features(reference)
    aspect = min(1.0, abs(math.log(max(a["aspect"], 1e-6) / max(b["aspect"], 1e-6))))
    distance = (
        0.18 * aspect
        + 0.15 * abs(a["mean"] - b["mean"])
        + 0.17 * min(1.0, abs(a["contrast"] - b["contrast"]))
        + 0.30 * min(1.0, abs(a["edge"] - b["edge"]))
        + 0.10 * min(1.0, abs(a["lr"] - b["lr"]))
        + 0.10 * min(1.0, abs(a["tb"] - b["tb"]))
    )
    return max(0.0, 1.0 - distance)


def subject_dependency_signature(timeline: dict[str, Any], frame_number: int) -> str:
    """Render dependency signature that deliberately ignores subject display names."""
    shot = resolve_shot(timeline, int(frame_number)) or {}
    compact = {
        "base": efficiency_frame_signature(timeline, int(frame_number)),
        "subject_id": str(shot.get("subject_id") or ""),
        "reference_id": str(shot.get("subject_reference_id") or ""),
        "reference_hash": str(shot.get("subject_reference_hash") or ""),
        "subject_type": str(shot.get("subject_type_resolved") or ""),
    }
    return hashlib.sha256(json.dumps(compact, sort_keys=True).encode("utf-8")).hexdigest()


class SubjectLibraryMixin:
    """Cross-shot project subjects routed through the existing Reference Lock pipeline."""

    def _build_ui(self):
        self.subject_var = tk.StringVar(value=NONE_SUBJECT)
        self.subject_type_var = tk.StringVar(value="Person")
        self.subject_status_var = tk.StringVar(value="No recurring subject assigned")
        self._subjects: dict[str, Any] = {"version": SUBJECT_VERSION, "subjects": []}
        self._subject_loaded_root: str | None = None
        super()._build_ui()
        self._augment_subject_workspace()
        try:
            self.after(0, self._subject_refresh_ui)
        except Exception:
            pass

    # ---------- storage ----------

    def project_paths(self):
        paths = super().project_paths()
        root = paths["root"]
        paths.update({
            "subjects_root": root / "subjects",
            "subjects_registry": root / "subjects" / "subjects.json",
            "subject_preview": root / "previews" / "subjects",
            "subject_scores": root / "cache" / "subjects" / "reference_scores.json",
        })
        return paths

    def _subject_registry_path(self) -> Path:
        return self.project_paths()["subjects_registry"]

    def _subject_root(self, subject_id: str) -> Path:
        return self.project_paths()["subjects_root"] / str(subject_id)

    def _load_subjects(self, force: bool = False) -> dict[str, Any]:
        path = self._subject_registry_path()
        root_key = str(path.parent.resolve())
        if not force and self._subject_loaded_root == root_key:
            return self._subjects
        data: dict[str, Any] = {"version": SUBJECT_VERSION, "subjects": []}
        if path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict) and isinstance(loaded.get("subjects"), list):
                    data = loaded
            except Exception as exc:
                self._log(f"Subject Library registry ignored: {exc}")
        changed = False
        clean_subjects: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for raw in data.get("subjects", []):
            if not isinstance(raw, dict):
                continue
            sid = str(raw.get("id") or "").strip()
            if not sid or sid in seen_ids:
                continue
            seen_ids.add(sid)
            subject = {
                "id": sid,
                "name": str(raw.get("name") or "Subject").strip() or "Subject",
                "type": str(raw.get("type") or "Other") if str(raw.get("type") or "Other") in SUBJECT_TYPES else "Other",
                "references": [],
            }
            for ref in raw.get("references", []):
                if not isinstance(ref, dict):
                    continue
                rid = str(ref.get("id") or "").strip()
                filename = str(ref.get("file") or "").strip()
                if not rid or not filename:
                    continue
                ref_path = self._subject_root(sid) / filename
                if not ref_path.exists():
                    continue
                current_hash = _sha256_file(ref_path)
                if current_hash != str(ref.get("sha256") or ""):
                    changed = True
                subject["references"].append({
                    "id": rid,
                    "file": filename,
                    "sha256": current_hash,
                    "source_shot": int(ref.get("source_shot") or 0),
                    "source_frame": int(ref.get("source_frame") or 0),
                })
            clean_subjects.append(subject)
        data = {"version": SUBJECT_VERSION, "subjects": clean_subjects}
        self._subjects = data
        self._subject_loaded_root = root_key
        if changed:
            self._save_subjects()
        return data

    def _save_subjects(self) -> None:
        path = self._subject_registry_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._subjects["version"] = SUBJECT_VERSION
        temp = path.with_suffix(".json.part")
        temp.write_text(json.dumps(self._subjects, indent=2), encoding="utf-8")
        temp.replace(path)

    def _subjects_list(self) -> list[dict[str, Any]]:
        return list(self._load_subjects().get("subjects", []))

    def _subject_by_id(self, subject_id: str) -> dict[str, Any] | None:
        return next((s for s in self._subjects_list() if str(s.get("id")) == str(subject_id)), None)

    def _subject_display(self, subject: dict[str, Any]) -> str:
        return str(subject.get("name") or "Subject")

    def _subject_id_from_display(self, display: str) -> str:
        if not display or display == NONE_SUBJECT:
            return ""
        matches = [s for s in self._subjects_list() if self._subject_display(s) == display]
        return str(matches[0]["id"]) if matches else ""

    def _subject_reference_entry(self, subject: dict[str, Any], reference_id: str) -> dict[str, Any] | None:
        return next((r for r in subject.get("references", []) if str(r.get("id")) == str(reference_id)), None)

    def _subject_reference_path(self, subject: dict[str, Any], reference: dict[str, Any]) -> Path | None:
        path = self._subject_root(str(subject["id"])) / str(reference.get("file") or "")
        return path if path.exists() else None

    # ---------- Easy Mode UI ----------

    def _augment_subject_workspace(self) -> None:
        card = getattr(self, "workspace_card", None)
        if card is None:
            return
        box = ttk.LabelFrame(card, text="Recurring Subject · v2.6", padding=8)
        box.pack(fill="x", pady=(8, 0))
        self.subject_card = box

        row = ttk.Frame(box, style="Panel.TFrame")
        row.pack(fill="x")
        ttk.Label(row, text="Subject", style="Panel.TLabel").pack(side="left")
        self.subject_combo = ttk.Combobox(row, textvariable=self.subject_var, values=[NONE_SUBJECT], state="readonly", width=22)
        self.subject_combo.pack(side="left", padx=5)
        self.subject_combo.bind("<<ComboboxSelected>>", lambda _e: self._subject_assign_selected())
        ttk.Label(row, text="New type", style="Panel.TLabel").pack(side="left", padx=(10, 3))
        ttk.Combobox(row, textvariable=self.subject_type_var, values=SUBJECT_TYPES, state="readonly", width=9).pack(side="left")
        ttk.Label(row, textvariable=self.subject_status_var, style="Muted.TLabel").pack(side="left", padx=8)

        actions = ttk.Frame(box, style="Panel.TFrame")
        actions.pack(fill="x", pady=(6, 0))
        ttk.Button(actions, text="Create from Shot", command=self._subject_create_clicked).pack(side="left")
        ttk.Button(actions, text="Add Reference", command=self._subject_add_reference_clicked).pack(side="left", padx=4)
        ttk.Button(actions, text="Assign Through…", command=self._subject_assign_through_clicked).pack(side="left", padx=4)
        ttk.Button(actions, text="Clear", command=self._subject_clear_selected).pack(side="left", padx=4)
        ttk.Button(actions, text="Rename", command=self._subject_rename_clicked).pack(side="left", padx=(12, 4))
        ttk.Button(actions, text="Check Subject", command=self._subject_check_clicked).pack(side="right")
        ttk.Label(
            box,
            text=(
                "Subjects intentionally survive cuts; Shot Memory does not. References remain project-local and are routed through the existing "
                "IP-Adapter → reference-only → Shot Memory capability ladder."
            ),
            style="Muted.TLabel",
            wraplength=740,
        ).pack(anchor="w", pady=(5, 0))

    def _subject_refresh_ui(self) -> None:
        try:
            subjects = self._subjects_list()
            values = [NONE_SUBJECT] + [self._subject_display(subject) for subject in subjects]
            self.subject_combo["values"] = values
            shot = self._selected_shot()
            sid = str((shot or {}).get("subject_id") or "")
            subject = self._subject_by_id(sid) if sid else None
            self.subject_var.set(self._subject_display(subject) if subject else NONE_SUBJECT)
            if subject:
                rid = str(shot.get("subject_reference_id") or "")
                ref = self._subject_reference_entry(subject, rid)
                self.subject_status_var.set(
                    f"{subject['type']} · {len(subject.get('references', []))} ref(s) · "
                    f"using {str((ref or {}).get('id') or 'auto')[:8]}"
                )
            else:
                self.subject_status_var.set("No recurring subject assigned")
        except Exception:
            pass

    # ---------- references / deterministic selection ----------

    def _local_source_reference_for_shot(self, shot: dict[str, Any]) -> tuple[Path | None, int]:
        start, end = int(shot["start"]), int(shot["end"])
        number = int(shot.get("reference_frame") or 0)
        if number < start or number > end:
            number = (start + end) // 2
        path = self.project_paths()["frames"] / f"frame_{number:06d}.png"
        return (path if path.exists() else None), number

    def _store_subject_reference(self, subject: dict[str, Any], source: Path, shot_id: int, frame_number: int) -> dict[str, Any]:
        digest = _sha256_file(source)
        for existing in subject.get("references", []):
            if str(existing.get("sha256")) == digest:
                return existing
        rid = uuid.uuid4().hex
        root = self._subject_root(str(subject["id"]))
        root.mkdir(parents=True, exist_ok=True)
        target = root / f"ref_{rid[:12]}.png"
        with Image.open(source) as image:
            image.convert("RGB").save(target, format="PNG", optimize=False)
        entry = {
            "id": rid,
            "file": target.name,
            "sha256": _sha256_file(target),
            "source_shot": int(shot_id),
            "source_frame": int(frame_number),
        }
        subject.setdefault("references", []).append(entry)
        self._save_subjects()
        return entry

    def _best_subject_reference(self, subject: dict[str, Any], shot: dict[str, Any]) -> dict[str, Any] | None:
        refs = [ref for ref in subject.get("references", []) if self._subject_reference_path(subject, ref)]
        if not refs:
            return None
        source, _ = self._local_source_reference_for_shot(shot)
        if source is None:
            return refs[0]
        scored: list[tuple[float, str, dict[str, Any]]] = []
        for ref in refs:
            path = self._subject_reference_path(subject, ref)
            try:
                score = reference_match_score(source, path) if path else -1.0
            except Exception:
                score = -1.0
            scored.append((score, str(ref.get("id") or ""), ref))
        # Stable ID tie-break keeps selection deterministic across machines.
        scored.sort(key=lambda item: (-item[0], item[1]))
        return scored[0][2]

    def _resolve_subject_for_shot(self, shot: dict[str, Any], choose_if_missing: bool = True) -> dict[str, Any] | None:
        sid = str(shot.get("subject_id") or "")
        subject = self._subject_by_id(sid) if sid else None
        if not subject:
            shot.pop("subject_reference_id", None)
            shot.pop("subject_reference_hash", None)
            shot.pop("subject_type_resolved", None)
            return None
        refs = subject.get("references", [])
        current = self._subject_reference_entry(subject, str(shot.get("subject_reference_id") or ""))
        if current is None and choose_if_missing:
            current = self._best_subject_reference(subject, shot)
            if current:
                shot["subject_reference_id"] = str(current["id"])
        if current:
            shot["subject_reference_hash"] = str(current.get("sha256") or "")
        else:
            shot.pop("subject_reference_hash", None)
        shot["subject_type_resolved"] = str(subject.get("type") or "Other")
        if str(shot.get("style") or "") != ORIGINAL and str(shot.get("subject_lock") or "Normal") == "Normal":
            shot["subject_lock"] = "Strong"
        return subject

    def _ensure_subject_assignments(self, persist: bool = True) -> None:
        timeline = getattr(self, "_director_timeline", {}) or {}
        changed = False
        before = json.dumps(timeline.get("shots", []), sort_keys=True, default=str)
        for shot in timeline.get("shots", []):
            if isinstance(shot, dict):
                self._resolve_subject_for_shot(shot, choose_if_missing=True)
        after = json.dumps(timeline.get("shots", []), sort_keys=True, default=str)
        changed = before != after
        timeline["subject_library"] = {"version": SUBJECT_VERSION}
        if changed and persist:
            try:
                path = self._timeline_path()
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(timeline, indent=2), encoding="utf-8")
            except Exception:
                pass

    def _reference_path_for_shot(self, shot: dict[str, Any]) -> Path | None:
        subject = self._resolve_subject_for_shot(shot, choose_if_missing=True)
        if subject:
            ref = self._subject_reference_entry(subject, str(shot.get("subject_reference_id") or ""))
            path = self._subject_reference_path(subject, ref) if ref else None
            if path:
                return path
        return super()._reference_path_for_shot(shot)

    def _reference_next_clicked(self) -> None:
        shot = self._selected_shot()
        if shot and shot.get("subject_id"):
            subject = self._subject_by_id(str(shot.get("subject_id")))
            refs = list((subject or {}).get("references", []))
            if refs:
                ids = [str(ref["id"]) for ref in refs]
                current = str(shot.get("subject_reference_id") or "")
                try:
                    index = ids.index(current)
                except ValueError:
                    index = -1
                selected = refs[(index + 1) % len(refs)]
                shot["subject_reference_id"] = str(selected["id"])
                shot["subject_reference_hash"] = str(selected.get("sha256") or "")
                self._save_director_timeline()
                self._director_load_selected_shot()
                return
        return super()._reference_next_clicked()

    # ---------- subject edit actions ----------

    def _subject_create_clicked(self) -> None:
        try:
            shot = self._selected_shot()
            if not shot:
                raise RuntimeError("Select a shot first.")
            source, frame_number = self._local_source_reference_for_shot(shot)
            if source is None:
                raise RuntimeError("Extract/analyze the source frames first.")
            name = simpledialog.askstring("Create Subject", "Subject name:", parent=self)
            if not name or not name.strip():
                return
            name = name.strip()
            if any(self._subject_display(s).lower() == name.lower() for s in self._subjects_list()):
                raise RuntimeError("A subject with that name already exists.")
            subject = {
                "id": uuid.uuid4().hex,
                "name": name,
                "type": self.subject_type_var.get() if self.subject_type_var.get() in SUBJECT_TYPES else "Other",
                "references": [],
            }
            self._subjects.setdefault("subjects", []).append(subject)
            self._save_subjects()
            ref = self._store_subject_reference(subject, source, int(shot["id"]), frame_number)
            shot["subject_id"] = str(subject["id"])
            shot["subject_reference_id"] = str(ref["id"])
            shot["subject_reference_hash"] = str(ref["sha256"])
            shot["subject_type_resolved"] = str(subject["type"])
            if str(shot.get("style") or "") != ORIGINAL and str(shot.get("subject_lock") or "Normal") == "Normal":
                shot["subject_lock"] = "Strong"
            self._save_director_timeline()
            self._efficiency_plan_dirty = True
            self._subject_refresh_ui()
            self._workspace_refresh_all()
            self._log(f"Subject Library: created '{name}' from shot {shot['id']} frame {frame_number}")
        except Exception as exc:
            messagebox.showerror("Subject Library", str(exc))

    def _subject_add_reference_clicked(self) -> None:
        try:
            shot = self._selected_shot()
            if not shot:
                raise RuntimeError("Select a shot first.")
            sid = str(shot.get("subject_id") or self._subject_id_from_display(self.subject_var.get()))
            subject = self._subject_by_id(sid)
            if not subject:
                raise RuntimeError("Assign or select a subject first.")
            source, frame_number = self._local_source_reference_for_shot(shot)
            if source is None:
                raise RuntimeError("Source reference frame is unavailable.")
            before = len(subject.get("references", []))
            self._store_subject_reference(subject, source, int(shot["id"]), frame_number)
            after = len(subject.get("references", []))
            self._subject_refresh_ui()
            self.subject_status_var.set(f"{subject['name']} · {after} ref(s)")
            self._log(f"Subject Library: {'added' if after > before else 'reused'} reference for '{subject['name']}'")
            # Existing shot selections stay pinned; adding an unused reference invalidates nothing.
        except Exception as exc:
            messagebox.showerror("Subject Library", str(exc))

    def _subject_assign_selected(self) -> None:
        shot = self._selected_shot()
        if not shot:
            return
        sid = self._subject_id_from_display(self.subject_var.get())
        if not sid:
            return self._subject_clear_selected()
        subject = self._subject_by_id(sid)
        if not subject:
            return
        old_rendered = self._rendered_timeline_for_workspace() if hasattr(self, "_rendered_timeline_for_workspace") else None
        shot["subject_id"] = sid
        shot.pop("subject_reference_id", None)
        shot.pop("subject_reference_hash", None)
        self._resolve_subject_for_shot(shot, choose_if_missing=True)
        self._save_director_timeline()
        self._efficiency_plan_dirty = True
        try:
            self._ensure_efficiency_plan(force=True)
        except Exception:
            pass
        if old_rendered:
            self._invalidate_changed_timeline_frames(old_rendered, self._director_timeline)
        self._director_load_selected_shot()
        self._workspace_refresh_all()

    def _subject_clear_selected(self) -> None:
        shot = self._selected_shot()
        if not shot:
            return
        for key in ("subject_id", "subject_reference_id", "subject_reference_hash", "subject_type_resolved"):
            shot.pop(key, None)
        self._save_director_timeline()
        self._efficiency_plan_dirty = True
        self._subject_refresh_ui()
        self._workspace_refresh_all()

    def _subject_assign_through_clicked(self) -> None:
        sid = self._subject_id_from_display(self.subject_var.get())
        subject = self._subject_by_id(sid)
        if not subject:
            messagebox.showwarning("Subject Library", "Choose a subject first.")
            return
        text = simpledialog.askstring("Assign Subject Through Shots", "Shot range (example: 3-9):", parent=self)
        if not text:
            return
        try:
            pieces = text.replace(" ", "").split("-", 1)
            start = int(pieces[0])
            end = int(pieces[1]) if len(pieces) > 1 else start
            if end < start:
                start, end = end, start
        except Exception:
            messagebox.showerror("Subject Library", "Use a range like 3-9.")
            return
        changed = 0
        for shot in self._director_timeline.get("shots", []):
            shot_id = int(shot.get("id", 0))
            if start <= shot_id <= end:
                shot["subject_id"] = sid
                shot.pop("subject_reference_id", None)
                shot.pop("subject_reference_hash", None)
                self._resolve_subject_for_shot(shot, choose_if_missing=True)
                changed += 1
        if changed:
            self._save_director_timeline()
            self._efficiency_plan_dirty = True
            self._workspace_refresh_all()
            self._log(f"Subject Library: assigned '{subject['name']}' to {changed} shot(s)")

    def _subject_rename_clicked(self) -> None:
        sid = self._subject_id_from_display(self.subject_var.get())
        subject = self._subject_by_id(sid)
        if not subject:
            return
        name = simpledialog.askstring("Rename Subject", "New name:", initialvalue=str(subject["name"]), parent=self)
        if not name or not name.strip():
            return
        name = name.strip()
        if any(str(s["id"]) != sid and self._subject_display(s).lower() == name.lower() for s in self._subjects_list()):
            messagebox.showerror("Subject Library", "That subject name is already in use.")
            return
        subject["name"] = name
        self._save_subjects()
        self._subject_refresh_ui()
        self._workspace_rebuild_shot_strip()
        # Stable subject/reference IDs mean rename is UI-only and invalidates nothing.

    # ---------- integration with workspace / render intelligence ----------

    def _director_load_selected_shot(self) -> None:
        result = super()._director_load_selected_shot()
        try:
            self.after(0, self._subject_refresh_ui)
        except Exception:
            pass
        return result

    def _workspace_rebuild_shot_strip(self) -> None:
        result = super()._workspace_rebuild_shot_strip()
        try:
            for shot in self._director_timeline.get("shots", []):
                sid = str(shot.get("subject_id") or "")
                if not sid:
                    continue
                subject = self._subject_by_id(sid)
                button = self._workspace_thumb_buttons.get(int(shot["id"]))
                if subject and button is not None:
                    current = str(button.cget("text"))
                    label = _safe_name(str(subject["name"]))[:12]
                    if f"SUBJ {label}" not in current:
                        button.configure(text=current + f"\nSUBJ {label}")
        except Exception:
            pass
        return result

    def _workspace_refresh_all(self) -> None:
        self._load_subjects()
        self._ensure_subject_assignments(persist=False)
        result = super()._workspace_refresh_all()
        self._subject_refresh_ui()
        return result

    def _build_efficiency_plan(self) -> dict[str, Any]:
        plan = super()._build_efficiency_plan()
        mode = str(plan.get("mode") or self.performance_mode_var.get())
        counts = {"easy": 0, "moderate": 0, "hard": 0, "bypass": 0}
        by_shot = {int(item.get("shot", 0)): item for item in plan.get("shots", []) if isinstance(item, dict)}
        for shot in self._director_timeline.get("shots", []):
            directive = shot.get("render_intelligence") if isinstance(shot, dict) else None
            if not isinstance(directive, dict):
                continue
            subject = self._resolve_subject_for_shot(shot, choose_if_missing=True)
            if subject and str(shot.get("style") or "") != ORIGINAL:
                # Cross-shot reference conditioning is extra work. Product/prop locks
                # get a small additional pressure because shape fidelity matters.
                type_bonus = 0.07 if subject.get("type") in {"Product", "Prop"} else 0.05
                score = min(1.0, float(directive.get("score") or 0.0) + type_bonus)
                tier = difficulty_tier(score)
                adjusted = policy_for(mode, tier, original=False)
                adjusted.update({
                    "shot": int(shot["id"]),
                    "score": round(score, 4),
                    "motion": float(directive.get("motion") or 0.0),
                    "detail": float(directive.get("detail") or 0.0),
                    "intensity": float(directive.get("intensity") or 0.0),
                    "subject_pressure": round(type_bonus, 4),
                })
                shot["render_intelligence"] = adjusted
                directive = adjusted
                by_shot[int(shot["id"])] = copy.deepcopy(adjusted)
            counts[str(directive.get("tier") or "moderate")] = counts.get(str(directive.get("tier") or "moderate"), 0) + 1
        plan["shots"] = [by_shot[key] for key in sorted(by_shot)]
        plan["counts"] = counts
        plan["subject_aware"] = True
        try:
            path = self.project_paths()["render_plan"]
            path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
            self._timeline_path().write_text(json.dumps(self._director_timeline, indent=2), encoding="utf-8")
        except Exception:
            pass
        return plan

    def _invalidate_changed_timeline_frames(self, old: dict[str, Any], new: dict[str, Any]) -> int:
        # Preserve all lower-layer invalidation behavior first.
        changed = super()._invalidate_changed_timeline_frames(old, new)
        styled = self.project_paths()["styled"]
        total = max(int(old.get("total_frames") or 0), int(new.get("total_frames") or 0))
        extra = 0
        for frame_number in range(1, total + 1):
            old_shot = resolve_shot(old, frame_number) or {}
            new_shot = resolve_shot(new, frame_number) or {}
            subject_fields_changed = any(
                str(old_shot.get(key) or "") != str(new_shot.get(key) or "")
                for key in ("subject_id", "subject_reference_id", "subject_reference_hash", "subject_type_resolved")
            )
            if not subject_fields_changed:
                continue
            candidate = styled / f"frame_{frame_number:06d}.png"
            if candidate.exists():
                candidate.unlink()
                extra += 1
        if extra:
            memory_root = self.project_paths()["root"] / "shot_memory" / "full"
            if memory_root.exists():
                shutil.rmtree(memory_root)
        return changed + extra

    def _director_preflight(self) -> None:
        self._load_subjects(force=True)
        self._ensure_subject_assignments(persist=True)
        return super()._director_preflight()

    def _render_range(self, start, count, test_only):
        self._load_subjects(force=True)
        self._ensure_subject_assignments(persist=True)
        assigned = sum(1 for shot in self._director_timeline.get("shots", []) if shot.get("subject_id"))
        self._log(f"Subject Library v2.6: {assigned} shot(s) with recurring project subjects")
        return super()._render_range(start, count, test_only)

    # ---------- cross-shot subject preview ----------

    def _subject_check_clicked(self) -> None:
        self._run_worker(self._subject_check_job)

    def _subject_check_job(self) -> None:
        try:
            sid = self._subject_id_from_display(self.subject_var.get())
            if not sid:
                shot = self._selected_shot()
                sid = str((shot or {}).get("subject_id") or "")
            subject = self._subject_by_id(sid)
            if not subject:
                raise RuntimeError("Choose an assigned subject first.")
            assigned = [shot for shot in self._director_timeline.get("shots", []) if str(shot.get("subject_id") or "") == sid]
            if not assigned:
                raise RuntimeError("That subject is not assigned to any shots.")
            root = self.project_paths()["subject_preview"] / sid
            if root.exists():
                shutil.rmtree(root)
            root.mkdir(parents=True, exist_ok=True)
            rows: list[tuple[Path, Path, Path, str]] = []
            total = len(assigned)
            for index, shot in enumerate(assigned, 1):
                self._resolve_subject_for_shot(shot, choose_if_missing=True)
                source, frame_number = self._local_source_reference_for_shot(shot)
                ref = self._reference_path_for_shot(shot)
                if source is None or ref is None:
                    continue
                self._render_range(frame_number, 1, True)
                rendered = self.project_paths()["test"] / f"frame_{frame_number:06d}.png"
                dest = root / f"shot_{int(shot['id']):04d}.png"
                shutil.copy2(rendered, dest)
                rows.append((source, ref, dest, f"Shot {shot['id']} · {STYLE_TO_LOOK.get(str(shot.get('style') or ''), str(shot.get('style') or ''))}"))
                self._set_progress(10 + index / max(1, total) * 80, f"Subject check {index}/{total}")
            if not rows:
                raise RuntimeError("No subject-check frames could be rendered.")
            thumb_w, thumb_h, header_h, label_h = 260, 150, 28, 28
            sheet = Image.new("RGB", (thumb_w * 3, header_h + len(rows) * (thumb_h + label_h)), (18, 19, 24))
            draw = ImageDraw.Draw(sheet)
            for col, title in enumerate(("SOURCE", "SUBJECT REF", "RESULT")):
                draw.text((col * thumb_w + 7, 7), title, fill=(238, 241, 247))
            for row_index, (source, ref, result, label) in enumerate(rows):
                y = header_h + row_index * (thumb_h + label_h)
                for col, path in enumerate((source, ref, result)):
                    with Image.open(path) as image:
                        thumb = ImageOps.fit(image.convert("RGB"), (thumb_w, thumb_h), Image.Resampling.LANCZOS)
                    sheet.paste(thumb, (col * thumb_w, y))
                draw.text((7, y + thumb_h + 6), label[:100], fill=(238, 241, 247))
            target = root / "SUBJECT_CHECK.jpg"
            sheet.save(target, format="JPEG", quality=92)
            self.after(0, lambda p=target: self._show_image(p, self.output_preview, "output"))
            self.after(0, lambda: self.output_preview_status.set(f"Subject Check · {subject['name']}"))
            self._set_progress(100, f"Subject check ready · {subject['name']}")
            self._log(f"Subject Library cross-shot preview: {target}")
        except Exception as exc:
            self._workspace_show_error(exc)

    def _render_profile(self) -> dict:
        profile = super()._render_profile()
        subjects = self._subjects_list()
        profile["subject_library"] = {
            "version": SUBJECT_VERSION,
            "subjects": len(subjects),
            "stable_ids": True,
            "multi_reference": True,
            "cross_shot": True,
            "temporal_memory_crosses_cuts": False,
        }
        return profile
