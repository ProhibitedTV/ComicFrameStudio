#!/usr/bin/env python3
"""Project Workspace / UX layer for ComicFrame Studio v2.4.

v2.4 makes the existing v2 renderer feel like one coherent application instead
of exposing every subsystem at once. Easy Mode becomes a project workspace with
clickable shot thumbnails, selected-shot controls, project health, workload,
one-click preview/rerender actions, autosave, undo/redo, and simple errors.

The v2.1-v2.3 engine remains underneath unchanged and Advanced Mode can reveal
it at any time.
"""
from __future__ import annotations

import copy
import json
import math
import re
import shutil
from pathlib import Path
from typing import Any

import requests
import tkinter as tk
from tkinter import messagebox, ttk
from PIL import Image, ImageDraw, ImageOps, ImageTk

from comicframe_director import (
    INTENSITY_LEVELS,
    LOOKS,
    ORIGINAL,
    STYLE_TO_LOOK,
    apply_treatment,
    resolve_frame_plan,
    resolve_shot,
)
from comicframe_reference_lock import BACKEND_MEMORY, reference_plan_signature


WORKSPACE_VERSION = "2.4"
COMPARE_LOOKS = ("Clean Comic", "Dark / Noir", "Dream / Surreal", "Glitch")


def thumbnail_frame_number(shot: dict[str, Any]) -> int:
    """Prefer the shot's reference frame; otherwise use its midpoint."""
    start = int(shot.get("start") or 1)
    end = int(shot.get("end") or start)
    reference = int(shot.get("reference_frame") or 0)
    if start <= reference <= end:
        return reference
    return (start + end) // 2


def sequence_frame_numbers(
    shots: list[dict[str, Any]],
    selected_id: int,
    per_side: int = 6,
) -> list[int]:
    """Return a short contiguous transition preview around a selected shot."""
    if not shots:
        return []
    index = next((i for i, s in enumerate(shots) if int(s.get("id", 0)) == int(selected_id)), 0)
    shot = shots[index]
    start, end = int(shot["start"]), int(shot["end"])
    next_shot = shots[index + 1] if index + 1 < len(shots) else None
    if next_shot:
        left = max(start, end - max(1, per_side) + 1)
        right = min(int(next_shot["end"]), int(next_shot["start"]) + max(1, per_side) - 1)
        return list(range(left, right + 1))
    count = max(4, per_side * 2)
    middle = (start + end) // 2
    left = max(start, middle - count // 2)
    right = min(end, left + count - 1)
    left = max(start, right - count + 1)
    return list(range(left, right + 1))


def friendly_error_text(exc: Exception | str) -> tuple[str, str]:
    text = str(exc)
    low = text.lower()
    if "outofmemory" in low or "cuda out of memory" in low or "out of vram" in low:
        return (
            "Stable Diffusion ran out of VRAM",
            "ComicFrame could not finish the current shot. Switch inference to 768 and retry the shot.",
        )
    if "controlnet" in low and ("missing" in low or "required" in low or "no usable" in low):
        return (
            "ControlNet needs attention",
            "Sync WebUI and make sure a checkpoint-compatible Canny ControlNet model is installed.",
        )
    if "connection" in low or "failed to establish" in low or "connection refused" in low:
        return (
            "Stable Diffusion WebUI is not connected",
            "Start Forge/A1111 with its API enabled, then click Check Setup or Sync WebUI.",
        )
    if "nan" in low:
        return (
            "Stable Diffusion produced invalid values",
            "Try 1024 or 768 inference, or switch sampler/checkpoint for this shot.",
        )
    if "checkpoint" in low and ("active" in low or "load" in low):
        return (
            "Checkpoint did not load",
            "ComicFrame asked the WebUI to switch models but the backend did not confirm the requested checkpoint.",
        )
    return ("ComicFrame could not finish that action", text[:700])


def shot_cache_state(
    timeline: dict[str, Any],
    rendered_timeline: dict[str, Any] | None,
    styled_dir: Path,
    shot: dict[str, Any],
) -> dict[str, Any]:
    start, end = int(shot["start"]), int(shot["end"])
    total = max(0, end - start + 1)
    present = 0
    valid = 0
    for frame_number in range(start, end + 1):
        path = styled_dir / f"frame_{frame_number:06d}.png"
        exists = path.exists() and path.stat().st_size > 10000
        if exists:
            present += 1
        signature_ok = False
        if rendered_timeline:
            try:
                signature_ok = (
                    reference_plan_signature(timeline, frame_number)
                    == reference_plan_signature(rendered_timeline, frame_number)
                )
            except Exception:
                signature_ok = False
        if exists and signature_ok:
            valid += 1

    style = str(shot.get("style") or "")
    if style == ORIGINAL and present == total and total:
        status = "source"
    elif valid == total and total:
        status = "rendered"
    elif present:
        status = "dirty" if valid < present or valid < total else "partial"
    else:
        status = "needs-render"
    return {"status": status, "total": total, "present": present, "valid": valid}


def workload_snapshot(
    timeline: dict[str, Any],
    rendered_timeline: dict[str, Any] | None,
    styled_dir: Path,
) -> dict[str, int]:
    total = int(timeline.get("total_frames") or 0)
    valid = 0
    dirty_shots = 0
    for shot in timeline.get("shots", []):
        state = shot_cache_state(timeline, rendered_timeline, styled_dir, shot)
        valid += int(state["valid"])
        if state["status"] not in {"rendered", "source"}:
            dirty_shots += 1
    return {
        "total": total,
        "cached": min(total, valid),
        "remaining": max(0, total - valid),
        "dirty_shots": dirty_shots,
    }


class ProjectWorkspaceMixin:
    """Make the shot workspace the default product surface in Easy Mode."""

    def _build_ui(self):
        self.workspace_status_var = tk.StringVar(value="PROJECT · choose a video and analyze shots")
        self.workspace_health_var = tk.StringVar(value="Setup not checked")
        self.workspace_workload_var = tk.StringVar(value="No render plan yet")
        self.workspace_saved_var = tk.StringVar(value="")
        self.workspace_selected_var = tk.StringVar(value="No shot selected")
        self._workspace_history: list[dict[str, Any]] = []
        self._workspace_redo: list[dict[str, Any]] = []
        self._workspace_suppress_history = False
        self._workspace_clipboard: dict[str, Any] | None = None
        self._workspace_thumb_images: dict[int, Any] = {}
        self._workspace_thumb_buttons: dict[int, Any] = {}
        self._workspace_partial_render = False
        super()._build_ui()
        self._build_project_workspace()
        self._bind_workspace_shortcuts()
        self.after(0, self._workspace_refresh_all)

    # ---------- Paths / project organization ----------

    def project_paths(self):
        paths = super().project_paths()
        root = paths["root"]
        paths.update({
            "previews": root / "previews",
            "workspace_cache": root / "cache",
            "thumbs": root / "cache" / "shot_thumbnails",
            "compare": root / "previews" / "look_compare",
            "sequence": root / "previews" / "sequence",
        })
        return paths

    def _ensure_workspace_dirs(self) -> None:
        paths = self.project_paths()
        for key in ("previews", "workspace_cache", "thumbs", "compare", "sequence"):
            paths[key].mkdir(parents=True, exist_ok=True)

    # ---------- Primary workspace UI ----------

    def _build_project_workspace(self) -> None:
        card = self._panel(self.left, "3 · Project Workspace · v2.4")
        try:
            card.pack(fill="x", pady=8, before=self.director_card)
        except Exception:
            card.pack(fill="x", pady=8)
        self.workspace_card = card

        header = ttk.Frame(card, style="Panel.TFrame")
        header.pack(fill="x")
        ttk.Label(header, textvariable=self.workspace_status_var, style="Panel.TLabel").pack(side="left")
        ttk.Label(header, textvariable=self.workspace_saved_var, style="Muted.TLabel").pack(side="right", padx=(8, 0))
        ttk.Button(header, text="Check Setup", command=self._workspace_check_setup_clicked).pack(side="right")
        ttk.Button(header, text="Advanced", command=self._workspace_toggle_advanced).pack(side="right", padx=5)

        ttk.Label(card, textvariable=self.workspace_health_var, style="Muted.TLabel", wraplength=760).pack(anchor="w", pady=(5, 1))
        ttk.Label(card, textvariable=self.workspace_workload_var, style="Muted.TLabel", wraplength=760).pack(anchor="w", pady=(0, 8))

        commands = ttk.Frame(card, style="Panel.TFrame")
        commands.pack(fill="x", pady=(0, 8))
        ttk.Button(commands, text="Analyze Shots", style="Accent.TButton", command=self._director_analyze_clicked).pack(side="left")
        ttk.Button(commands, text="Quick Look", command=self._workspace_quick_look_clicked).pack(side="left", padx=4)
        ttk.Button(commands, text="Preview Project", command=self._director_preview_clicked).pack(side="left", padx=4)
        ttk.Button(commands, text="RENDER VIDEO", style="Accent.TButton", command=self._workspace_render_clicked).pack(side="left", padx=(12, 4))
        ttk.Button(commands, text="STOP", style="Danger.TButton", command=self._stop_clicked).pack(side="right")

        strip_box = ttk.LabelFrame(card, text="Shots", padding=6)
        strip_box.pack(fill="x", pady=(0, 8))
        self.workspace_shot_canvas = tk.Canvas(strip_box, height=148, highlightthickness=0)
        scroll = ttk.Scrollbar(strip_box, orient="horizontal", command=self.workspace_shot_canvas.xview)
        self.workspace_shot_canvas.configure(xscrollcommand=scroll.set)
        self.workspace_shot_canvas.pack(fill="x", expand=True)
        scroll.pack(fill="x")
        self.workspace_shot_strip = ttk.Frame(self.workspace_shot_canvas)
        self._workspace_strip_window = self.workspace_shot_canvas.create_window((0, 0), window=self.workspace_shot_strip, anchor="nw")
        self.workspace_shot_strip.bind(
            "<Configure>",
            lambda _e: self.workspace_shot_canvas.configure(scrollregion=self.workspace_shot_canvas.bbox("all")),
        )

        inspector = ttk.LabelFrame(card, text="Selected shot", padding=8)
        inspector.pack(fill="x")
        ttk.Label(inspector, textvariable=self.workspace_selected_var, style="Panel.TLabel").pack(anchor="w", pady=(0, 6))

        row = ttk.Frame(inspector, style="Panel.TFrame")
        row.pack(fill="x")
        ttk.Label(row, text="Look", style="Panel.TLabel").pack(side="left")
        ttk.Combobox(row, textvariable=self.director_look_var, values=list(LOOKS.keys()), state="readonly", width=18).pack(side="left", padx=4)
        ttk.Label(row, text="Intensity", style="Panel.TLabel").pack(side="left", padx=(10, 3))
        ttk.Combobox(row, textvariable=self.director_intensity_var, values=list(INTENSITY_LEVELS.keys()), state="readonly", width=9).pack(side="left")
        ttk.Label(row, text="Motion", style="Panel.TLabel").pack(side="left", padx=(10, 3))
        ttk.Combobox(row, textvariable=self.director_direction_var, values=("Stay", "Build", "Fade"), state="readonly", width=8).pack(side="left")
        ttk.Label(row, text="Subject", style="Panel.TLabel").pack(side="left", padx=(10, 3))
        ttk.Combobox(row, textvariable=self.reference_level_var, values=("Normal", "Strong", "Locked"), state="readonly", width=9).pack(side="left")
        ttk.Button(row, text="Apply", style="Accent.TButton", command=self._director_apply_selected_shot).pack(side="right")

        actions = ttk.Frame(inspector, style="Panel.TFrame")
        actions.pack(fill="x", pady=(8, 0))
        ttk.Button(actions, text="Preview Shot", command=self._workspace_preview_shot_clicked).pack(side="left")
        ttk.Button(actions, text="Sequence Preview", command=self._workspace_sequence_clicked).pack(side="left", padx=4)
        ttk.Button(actions, text="Rerender Shot", command=self._workspace_rerender_shot_clicked).pack(side="left", padx=4)
        ttk.Button(actions, text="Use Original", command=self._workspace_use_original).pack(side="left", padx=4)
        ttk.Button(actions, text="Compare Looks", command=self._workspace_compare_looks_clicked).pack(side="left", padx=(12, 4))

        edit = ttk.Frame(inspector, style="Panel.TFrame")
        edit.pack(fill="x", pady=(6, 0))
        ttk.Button(edit, text="Copy Look", command=self._workspace_copy_look).pack(side="left")
        ttk.Button(edit, text="Paste Look", command=self._workspace_paste_look).pack(side="left", padx=4)
        ttk.Button(edit, text="Reset Shot", command=self._workspace_reset_shot).pack(side="left", padx=4)
        ttk.Button(edit, text="Another Reference", command=self._reference_next_clicked).pack(side="left", padx=(12, 4))
        ttk.Button(edit, text="Undo", command=self._workspace_undo).pack(side="right", padx=4)
        ttk.Button(edit, text="Redo", command=self._workspace_redo_action).pack(side="right")

        ttk.Progressbar(card, variable=self.progress, maximum=100).pack(fill="x", pady=(10, 3))
        ttk.Label(card, textvariable=self.progress_label_var, style="Muted.TLabel").pack(anchor="w")

    def _bind_workspace_shortcuts(self) -> None:
        self.bind("<Left>", lambda _e: self._workspace_move_selection(-1))
        self.bind("<Right>", lambda _e: self._workspace_move_selection(1))
        self.bind("<Control-z>", lambda _e: self._workspace_undo())
        self.bind("<Control-y>", lambda _e: self._workspace_redo_action())
        self.bind("<Key-p>", lambda _e: self._workspace_preview_shot_clicked())
        self.bind("<Key-r>", lambda _e: self._workspace_rerender_shot_clicked())
        self.bind("<Key-o>", lambda _e: self._workspace_use_original())

    def _workspace_toggle_advanced(self) -> None:
        self.director_easy_var.set(not bool(self.director_easy_var.get()))
        self._apply_easy_mode_visibility()

    def _apply_easy_mode_visibility(self) -> None:
        super()._apply_easy_mode_visibility()
        easy = bool(self.director_easy_var.get())
        director = getattr(self, "director_card", None)
        workspace = getattr(self, "workspace_card", None)
        if director is None:
            return
        try:
            if easy:
                director.pack_forget()
            elif not director.winfo_manager():
                if workspace is not None and workspace.winfo_manager():
                    director.pack(fill="x", pady=8, before=workspace)
                else:
                    director.pack(fill="x", pady=8)
        except Exception:
            pass

    # ---------- Timeline autosave / history ----------

    def _save_director_timeline(self) -> None:
        path = self._timeline_path()
        if not self._workspace_suppress_history and path.exists():
            try:
                old = json.loads(path.read_text(encoding="utf-8"))
                current = copy.deepcopy(self._director_timeline)
                if old != current:
                    self._workspace_history.append(old)
                    self._workspace_history = self._workspace_history[-30:]
                    self._workspace_redo.clear()
            except Exception:
                pass
        super()._save_director_timeline()
        try:
            self._director_timeline["version"] = WORKSPACE_VERSION
            path.write_text(json.dumps(self._director_timeline, indent=2), encoding="utf-8")
        except Exception:
            pass
        self.after(0, self._workspace_after_save)

    def _workspace_after_save(self) -> None:
        self.workspace_saved_var.set("Saved ✓")
        self._workspace_refresh_all()
        self.after(1400, lambda: self.workspace_saved_var.set(""))

    def _workspace_apply_snapshot(self, snapshot: dict[str, Any]) -> None:
        self._workspace_suppress_history = True
        try:
            self._director_timeline = copy.deepcopy(snapshot)
            super()._save_director_timeline()
        finally:
            self._workspace_suppress_history = False
        self._refresh_director_ui()
        self._director_load_selected_shot()
        self._workspace_refresh_all()

    def _workspace_undo(self) -> None:
        if not self._workspace_history:
            self.workspace_saved_var.set("Nothing to undo")
            return
        current = copy.deepcopy(self._director_timeline)
        snapshot = self._workspace_history.pop()
        self._workspace_redo.append(current)
        self._workspace_apply_snapshot(snapshot)
        self.workspace_saved_var.set("Undone")

    def _workspace_redo_action(self) -> None:
        if not self._workspace_redo:
            self.workspace_saved_var.set("Nothing to redo")
            return
        current = copy.deepcopy(self._director_timeline)
        snapshot = self._workspace_redo.pop()
        self._workspace_history.append(current)
        self._workspace_apply_snapshot(snapshot)
        self.workspace_saved_var.set("Redone")

    # ---------- Thumbnail strip / state ----------

    def _rendered_timeline_for_workspace(self) -> dict[str, Any] | None:
        path = self._rendered_timeline_path()
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def _thumbnail_path(self, shot: dict[str, Any]) -> Path:
        return self.project_paths()["thumbs"] / f"shot_{int(shot['id']):04d}.jpg"

    def _ensure_shot_thumbnail(self, shot: dict[str, Any]) -> Path | None:
        self._ensure_workspace_dirs()
        target = self._thumbnail_path(shot)
        frame_number = thumbnail_frame_number(shot)
        source = self.project_paths()["frames"] / f"frame_{frame_number:06d}.png"
        if not source.exists():
            return None
        if target.exists() and target.stat().st_mtime >= source.stat().st_mtime:
            return target
        with Image.open(source) as image:
            thumb = ImageOps.fit(image.convert("RGB"), (160, 90), Image.Resampling.LANCZOS)
            thumb.save(target, format="JPEG", quality=86)
        return target

    def _workspace_rebuild_shot_strip(self) -> None:
        strip = getattr(self, "workspace_shot_strip", None)
        if strip is None:
            return
        for child in strip.winfo_children():
            child.destroy()
        self._workspace_thumb_images.clear()
        self._workspace_thumb_buttons.clear()

        timeline = self._director_timeline if self._director_timeline.get("shots") else self._load_director_timeline(silent=True)
        shots = timeline.get("shots", []) if timeline else []
        rendered = self._rendered_timeline_for_workspace()
        styled = self.project_paths()["styled"]
        selected = self._selected_shot()
        selected_id = int(selected.get("id", 0)) if selected else 0

        for col, shot in enumerate(shots):
            shot_id = int(shot["id"])
            state = shot_cache_state(timeline, rendered, styled, shot)
            thumb_path = self._ensure_shot_thumbnail(shot)
            image = None
            if thumb_path:
                try:
                    with Image.open(thumb_path) as source:
                        image = ImageTk.PhotoImage(source.copy())
                    self._workspace_thumb_images[shot_id] = image
                except Exception:
                    image = None
            icon = {
                "rendered": "✓",
                "source": "SRC",
                "dirty": "↻",
                "partial": "◐",
                "needs-render": "○",
            }.get(state["status"], "○")
            lock = str(shot.get("subject_lock") or "Normal")
            lock_text = " · LOCK" if lock == "Locked" else ""
            text = f"{icon}  Shot {shot_id}{lock_text}\n{STYLE_TO_LOOK.get(str(shot.get('style') or ''), str(shot.get('style') or ''))[:20]}"
            button = ttk.Button(
                strip,
                text=text,
                image=image,
                compound="top",
                command=lambda sid=shot_id: self._workspace_select_shot(sid),
            )
            button.grid(row=0, column=col, padx=3, pady=2, sticky="n")
            self._workspace_thumb_buttons[shot_id] = button
            if shot_id == selected_id:
                try:
                    button.state(["focus"])
                except Exception:
                    pass

    def _workspace_select_shot(self, shot_id: int) -> None:
        timeline = self._director_timeline
        fps = float(timeline.get("fps") or 30.0)
        shot = next((s for s in timeline.get("shots", []) if int(s.get("id", 0)) == int(shot_id)), None)
        if not shot:
            return
        value = f"{shot_id:02d} · {int(shot['start']) / fps:.1f}s–{int(shot['end']) / fps:.1f}s"
        self.director_shot_var.set(value)
        self._director_load_selected_shot()
        self._workspace_refresh_selected()

    def _workspace_move_selection(self, delta: int) -> None:
        shots = self._director_timeline.get("shots", [])
        if not shots:
            return
        selected = self._selected_shot()
        current = int(selected.get("id", 1)) if selected else 1
        ids = [int(s["id"]) for s in shots]
        try:
            index = ids.index(current)
        except ValueError:
            index = 0
        index = max(0, min(len(ids) - 1, index + int(delta)))
        self._workspace_select_shot(ids[index])

    def _director_load_selected_shot(self) -> None:
        result = super()._director_load_selected_shot()
        self.after(0, self._workspace_refresh_selected)
        return result

    def _workspace_refresh_selected(self) -> None:
        if not hasattr(self, "workspace_selected_var"):
            return
        shot = self._selected_shot()
        if not shot:
            self.workspace_selected_var.set("No shot selected")
            return
        timeline = self._director_timeline
        rendered = self._rendered_timeline_for_workspace()
        state = shot_cache_state(timeline, rendered, self.project_paths()["styled"], shot)
        fps = float(timeline.get("fps") or 30.0)
        start, end = int(shot["start"]), int(shot["end"])
        look = STYLE_TO_LOOK.get(str(shot.get("style") or ""), str(shot.get("style") or ""))
        ref = int(shot.get("reference_frame") or 0)
        backend = str(shot.get("reference_backend_resolved") or BACKEND_MEMORY)
        self.workspace_selected_var.set(
            f"Shot {int(shot['id'])} · {start / fps:.1f}s–{end / fps:.1f}s · {look} · "
            f"{str(shot.get('subject_lock') or 'Normal')} · {state['status']} · ref {ref or 'auto'} / {backend}"
        )

    def _workspace_refresh_all(self) -> None:
        if not hasattr(self, "workspace_status_var"):
            return
        timeline = self._director_timeline if getattr(self, "_director_timeline", {}).get("shots") else self._load_director_timeline(silent=True)
        video = Path(self.video_var.get().strip()).name if self.video_var.get().strip() else "No video"
        shots = timeline.get("shots", []) if timeline else []
        treatment = str(timeline.get("treatment") or "No treatment") if timeline else "No treatment"
        self.workspace_status_var.set(f"PROJECT · {video} · {len(shots)} shot(s) · {treatment}")
        if shots:
            rendered = self._rendered_timeline_for_workspace()
            work = workload_snapshot(timeline, rendered, self.project_paths()["styled"])
            self.workspace_workload_var.set(
                f"Render work · {work['total']} frames total · {work['cached']} reusable · "
                f"{work['remaining']} need work · {work['dirty_shots']} shot(s) changed"
            )
        else:
            self.workspace_workload_var.set("No render plan yet · Analyze Shots")
        self._workspace_rebuild_shot_strip()
        self._workspace_refresh_selected()

    # ---------- Simple shot editing ----------

    def _workspace_copy_look(self) -> None:
        shot = self._selected_shot()
        if not shot:
            return
        self._workspace_clipboard = {
            key: copy.deepcopy(shot.get(key))
            for key in ("style", "intensity_start", "intensity_end", "curve", "subject_lock")
        }
        self.workspace_saved_var.set("Look copied")

    def _workspace_paste_look(self) -> None:
        shot = self._selected_shot()
        if not shot or not self._workspace_clipboard:
            self.workspace_saved_var.set("Copy a look first")
            return
        for key, value in self._workspace_clipboard.items():
            shot[key] = copy.deepcopy(value)
        self._save_director_timeline()
        self._director_load_selected_shot()

    def _workspace_use_original(self) -> None:
        shot = self._selected_shot()
        if not shot:
            return
        shot.update({
            "style": ORIGINAL,
            "intensity_start": 0.0,
            "intensity_end": 0.0,
            "curve": "linear",
            "subject_lock": "Normal",
        })
        self._save_director_timeline()
        self._director_load_selected_shot()

    def _workspace_reset_shot(self) -> None:
        shot = self._selected_shot()
        if not shot:
            return
        clone = copy.deepcopy(self._director_timeline)
        apply_treatment(clone, str(clone.get("treatment") or "Clean Comic"))
        reset = next((s for s in clone.get("shots", []) if int(s.get("id", 0)) == int(shot["id"])), None)
        if reset:
            for key in ("style", "intensity_start", "intensity_end", "curve"):
                shot[key] = copy.deepcopy(reset.get(key))
        shot["subject_lock"] = "Strong" if str(shot.get("style") or "") != ORIGINAL else "Normal"
        self._save_director_timeline()
        self._director_load_selected_shot()

    # ---------- Setup health ----------

    def _workspace_runtime_health_text(self) -> str:
        connected = bool(getattr(self, "_webui_capabilities", {}).get("img2img"))
        checkpoint = self.checkpoint_var.get().strip() if hasattr(self, "checkpoint_var") else ""
        cn = bool(getattr(self, "_controlnet_available", False))
        caps = getattr(self, "_reference_caps", {}) or {}
        ref = "IP-Adapter" if caps.get("ip_adapter") else "reference-only" if caps.get("reference_only") else "Shot Memory"
        gpu = getattr(self, "_detected_vram_gb", None)
        gpu_text = f"{gpu:.1f} GB" if isinstance(gpu, (int, float)) else "unknown GPU"
        return (
            f"{'READY' if connected and cn else 'ACTION NEEDED'} · "
            f"WebUI {'✓' if connected else '—'} · ControlNet {'✓' if cn else '—'} · "
            f"{checkpoint or 'checkpoint unknown'} · {ref} · {gpu_text}"
        )

    def _workspace_check_setup_clicked(self) -> None:
        self._run_worker(self._workspace_check_setup_job)

    def _workspace_check_setup_job(self) -> None:
        try:
            missing = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]
            if missing:
                raise RuntimeError("Missing from PATH: " + ", ".join(missing))
            response = requests.get(f"{self.api_url()}/sdapi/v1/options", timeout=10)
            response.raise_for_status()
            data = response.json() if response.content else {}
            checkpoint = str(data.get("sd_model_checkpoint") or "").strip()
            if checkpoint and hasattr(self, "checkpoint_var"):
                self.after(0, lambda value=checkpoint: self.checkpoint_var.set(value))
            try:
                self._detect_controlnet()
            except Exception:
                pass
            try:
                self._probe_gpu_memory()
            except Exception:
                pass
            try:
                self._refresh_reference_capabilities()
            except Exception:
                pass
            self._webui_capabilities = dict(getattr(self, "_webui_capabilities", {}) or {})
            self._webui_capabilities["img2img"] = True
            self.after(0, lambda: self.workspace_health_var.set(self._workspace_runtime_health_text()))
            self._log("Project Workspace setup check complete.")
        except Exception as exc:
            title, detail = friendly_error_text(exc)
            self.after(0, lambda: self.workspace_health_var.set(f"ACTION NEEDED · {title} · {detail}"))
            self._log(f"Workspace setup check: {exc}")

    def _sync_webui(self):
        result = super()._sync_webui()
        try:
            self.after(0, lambda: self.workspace_health_var.set(self._workspace_runtime_health_text()))
        except Exception:
            pass
        return result

    # ---------- Preview / comparison ----------

    def _workspace_show_error(self, exc: Exception) -> None:
        title, detail = friendly_error_text(exc)
        self._log(f"ERROR: {exc}")
        self._set_progress(0, title)
        try:
            self.after(0, lambda: messagebox.showerror(title, detail))
        except Exception:
            pass

    def _workspace_preview_shot_clicked(self) -> None:
        self._run_worker(self._workspace_preview_shot_job)

    def _workspace_preview_shot_job(self) -> None:
        try:
            shot = self._selected_shot()
            if not shot:
                raise RuntimeError("Select a shot first.")
            frame_number = thumbnail_frame_number(shot)
            self._render_range(frame_number, 1, True)
            out = self.project_paths()["test"] / f"frame_{frame_number:06d}.png"
            if out.exists():
                self.after(0, lambda p=out: self._show_image(p, self.output_preview, "output"))
                self.after(0, lambda: self.output_preview_status.set(f"Shot {shot['id']} preview"))
            self._set_progress(100, f"Shot {shot['id']} preview ready")
        except Exception as exc:
            self._workspace_show_error(exc)

    def _workspace_quick_look_clicked(self) -> None:
        try:
            timeline = self._ensure_director_timeline()
            shots = list(timeline.get("shots", []))
            if not shots:
                return
            self._ensure_workspace_dirs()
            thumb_w, thumb_h, label_h = 240, 135, 30
            cols = 3
            rows = math.ceil(len(shots) / cols)
            sheet = Image.new("RGB", (cols * thumb_w, rows * (thumb_h + label_h)), (18, 19, 24))
            draw = ImageDraw.Draw(sheet)
            rendered = self._rendered_timeline_for_workspace()
            for index, shot in enumerate(shots):
                state = shot_cache_state(timeline, rendered, self.project_paths()["styled"], shot)
                source_num = thumbnail_frame_number(shot)
                styled = self.project_paths()["styled"] / f"frame_{source_num:06d}.png"
                source = self.project_paths()["frames"] / f"frame_{source_num:06d}.png"
                path = styled if styled.exists() and styled.stat().st_size > 10000 else source
                if not path.exists():
                    continue
                with Image.open(path) as image:
                    thumb = ImageOps.fit(image.convert("RGB"), (thumb_w, thumb_h), Image.Resampling.LANCZOS)
                x = (index % cols) * thumb_w
                y = (index // cols) * (thumb_h + label_h)
                sheet.paste(thumb, (x, y))
                look = STYLE_TO_LOOK.get(str(shot.get("style") or ""), str(shot.get("style") or ""))
                draw.text((x + 6, y + thumb_h + 7), f"Shot {shot['id']} · {look} · {state['status']}", fill=(238, 241, 247))
            target = self.project_paths()["previews"] / "QUICK_LOOK.jpg"
            target.parent.mkdir(parents=True, exist_ok=True)
            sheet.save(target, format="JPEG", quality=91)
            self._show_image(target, self.output_preview, "output")
            self.output_preview_status.set("Quick Look")
            self._log(f"Workspace Quick Look: {target}")
        except Exception as exc:
            self._workspace_show_error(exc)

    def _workspace_sequence_clicked(self) -> None:
        self._run_worker(self._workspace_sequence_job)

    def _workspace_sequence_job(self) -> None:
        try:
            timeline = self._ensure_director_timeline()
            shot = self._selected_shot()
            if not shot:
                raise RuntimeError("Select a shot first.")
            numbers = sequence_frame_numbers(list(timeline.get("shots", [])), int(shot["id"]), per_side=6)
            if not numbers:
                raise RuntimeError("Could not choose frames for sequence preview.")
            start, count = numbers[0], len(numbers)
            self._render_range(start, count, True)
            self._ensure_workspace_dirs()
            output = self.project_paths()["sequence"] / f"SHOT_{int(shot['id']):02d}_SEQUENCE.mp4"
            fps = float(timeline.get("fps") or 30.0)
            self._run([
                "ffmpeg", "-y", "-framerate", f"{fps:.8f}", "-start_number", str(start),
                "-i", str(self.project_paths()["test"] / "frame_%06d.png"), "-frames:v", str(count),
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", str(output),
            ])
            last = self.project_paths()["test"] / f"frame_{numbers[-1]:06d}.png"
            if last.exists():
                self.after(0, lambda p=last: self._show_image(p, self.output_preview, "output"))
            self._set_progress(100, f"Sequence preview ready · {output.name}")
            self._log(f"Sequence preview: {output}")
        except Exception as exc:
            self._workspace_show_error(exc)

    def _workspace_compare_looks_clicked(self) -> None:
        self._run_worker(self._workspace_compare_looks_job)

    def _workspace_compare_looks_job(self) -> None:
        shot = self._selected_shot()
        if not shot:
            return
        original = copy.deepcopy(shot)
        try:
            self._ensure_workspace_dirs()
            target_dir = self.project_paths()["compare"] / f"shot_{int(shot['id']):04d}"
            if target_dir.exists():
                shutil.rmtree(target_dir)
            target_dir.mkdir(parents=True, exist_ok=True)
            frame_number = thumbnail_frame_number(shot)
            results: list[tuple[str, Path]] = []
            for index, look in enumerate(COMPARE_LOOKS, 1):
                style = LOOKS[look]
                level = 0.72
                shot["style"] = style
                shot["intensity_start"] = level
                shot["intensity_end"] = level
                shot["curve"] = "linear"
                self._render_range(frame_number, 1, True)
                source = self.project_paths()["test"] / f"frame_{frame_number:06d}.png"
                dest = target_dir / f"{index:02d}_{re.sub(r'[^A-Za-z0-9_-]+', '_', look)}.png"
                shutil.copy2(source, dest)
                results.append((look, dest))
                self._set_progress(10 + index / len(COMPARE_LOOKS) * 80, f"Compare {index}/{len(COMPARE_LOOKS)}")

            thumb_w, thumb_h, label_h = 320, 190, 34
            sheet = Image.new("RGB", (thumb_w * 2, (thumb_h + label_h) * 2), (18, 19, 24))
            draw = ImageDraw.Draw(sheet)
            for index, (look, path) in enumerate(results):
                with Image.open(path) as image:
                    thumb = ImageOps.fit(image.convert("RGB"), (thumb_w, thumb_h), Image.Resampling.LANCZOS)
                x = (index % 2) * thumb_w
                y = (index // 2) * (thumb_h + label_h)
                sheet.paste(thumb, (x, y))
                draw.text((x + 8, y + thumb_h + 8), look, fill=(238, 241, 247))
            target = target_dir / "COMPARE_LOOKS.jpg"
            sheet.save(target, format="JPEG", quality=92)
            self.after(0, lambda p=target: self._show_image(p, self.output_preview, "output"))
            self.after(0, lambda: self.output_preview_status.set(f"Shot {shot['id']} · Compare Looks"))
            self._set_progress(100, "Look comparison ready")
        except Exception as exc:
            self._workspace_show_error(exc)
        finally:
            shot.clear()
            shot.update(original)
            self.after(0, self._director_load_selected_shot)

    # ---------- Rerender / full render ----------

    def _workspace_rerender_shot_clicked(self) -> None:
        self._run_worker(self._workspace_rerender_shot_job)

    def _workspace_rerender_shot_job(self) -> None:
        try:
            shot = self._selected_shot()
            if not shot:
                raise RuntimeError("Select a shot first.")
            start, end = int(shot["start"]), int(shot["end"])
            styled = self.project_paths()["styled"]
            for number in range(start, end + 1):
                candidate = styled / f"frame_{number:06d}.png"
                if candidate.exists():
                    candidate.unlink()
            self._workspace_partial_render = True
            try:
                self._render_range(start, end - start + 1, False)
            finally:
                self._workspace_partial_render = False
            self._set_progress(100, f"Shot {shot['id']} rerendered")
            self.after(0, self._workspace_refresh_all)
        except Exception as exc:
            self._workspace_partial_render = False
            self._workspace_show_error(exc)

    def _assemble(self, info):
        if self._workspace_partial_render:
            self._log("Workspace: selected-shot render complete; final assembly intentionally skipped.")
            return None
        return super()._assemble(info)

    def _workspace_render_clicked(self) -> None:
        if not self.video_var.get().strip():
            messagebox.showwarning("ComicFrame Studio", "Choose a source video first.")
            return
        if not messagebox.askyesno(
            "ComicFrame Studio",
            "Render/resume the full project?\n\nReusable completed shots will be kept.",
        ):
            return
        self._run_worker(self._workspace_full_render_job)

    def _workspace_full_render_job(self) -> None:
        try:
            self._ensure_director_timeline()
            self._render_range(1, None, False)
            self.after(0, self._workspace_refresh_all)
        except Exception as exc:
            self._workspace_show_error(exc)

    # ---------- Profile ----------

    def _render_profile(self) -> dict:
        profile = super()._render_profile()
        profile["workspace"] = {
            "version": WORKSPACE_VERSION,
            "easy_mode": bool(self.director_easy_var.get()) if hasattr(self, "director_easy_var") else True,
            "autosave": True,
            "timeline_history": "session undo/redo",
            "thumbnail_cache": "cache/shot_thumbnails",
            "previews": "previews/",
        }
        return profile
