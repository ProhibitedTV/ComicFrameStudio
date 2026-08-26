#!/usr/bin/env python3
"""ComicFrame Studio v3.0 — video in, process, video out.

This module is intentionally an aggressive product boundary over the existing
renderer.  The v2 engine remains intact and audited underneath, but none of its
implementation controls are part of the normal operator experience.

Normal workflow:
    choose video -> choose process -> process video -> open/save result
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageOps, ImageTk

import comicframe_styles as styles
from comicframe_artistic import STYLE_CATEGORIES, STYLE_STABILITY, register_artistic_expansion
from comicframe_director import _set_shot, apply_treatment
from comicframe_usability import (
    ComicFrameStudioApp as UsabilityComicFrameStudioApp,
    default_project_path_for_video,
    source_preview_cache_path,
)
from comicframe_workspace import friendly_error_text


SIMPLE_VERSION = "3.0"

# Sequences are first-class processes alongside single-style passes.  The labels
# are deliberately creative/user-facing; none expose implementation language.
SEQUENCE_PROCESSES: dict[str, str] = {
    "Clean → Chaos · sequence": "Clean → Chaos",
    "Reality Break · sequence": "Reality Break",
    "Dark Video Essay · sequence": "Dark Video Essay",
    "Product Fever Dream · sequence": "Product Promo",
}

# Curated rather than alphabetical: the first screen should emphasize looks that
# are worth actually playing with.  Missing names are simply filtered out, which
# keeps the shell compatible if the style library evolves independently.
STYLE_PROCESS_ORDER = (
    "Graphic Shock · maximum print",
    "Cyberpunk Print",
    "Dream Collapse",
    "Signal Rupture",
    "Glitch Collapse",
    "Analog Decay",
    "VHS Horror",
    "Grindhouse Damage",
    "Underground Flyer",
    "Risograph Zine",
    "Screenprint Poster",
    "Manga Motion",
    "Neo-Noir",
    "Retro 70s Print",
    "Pulp Horror",
    "Pulp Cover",
    "Album Art",
    "Brutalist Dreamstate",
    "Surveillance State",
    "Dystopian Sci-Fi",
    "Liminal Haze",
    "Relic Iconography",
    "Infomercial Fever Dream",
    "Hype Drop",
    "Propaganda Poster",
    "Watercolor Wash",
    "Gouache Storybook",
    "Oil Impasto",
    "Charcoal Study",
    "Pastel Dream",
    "Ink Wash",
    "Dream-Pop Haze",
    "Arthouse Melancholy",
    "Clean Graphic Novel",
    "Luxury Ad",
    "Hero Tech Promo",
)


def simple_process_catalog() -> list[str]:
    """Return the complete public process list without diagnostic engine modes."""
    register_artistic_expansion()
    values = list(SEQUENCE_PROCESSES)
    values.extend(name for name in STYLE_PROCESS_ORDER if name in styles.STYLE_PACKS)
    return values


def process_description(name: str) -> str:
    if name in SEQUENCE_PROCESSES:
        treatment = SEQUENCE_PROCESSES[name]
        descriptions = {
            "Clean → Chaos": "Starts controlled, progressively breaks reality, then snaps back. Designed for escalation.",
            "Reality Break": "Mostly grounded footage with a deliberate surreal rupture through the middle of the video.",
            "Dark Video Essay": "Graphic-noir treatment with restrained cleaner beats for contrast.",
            "Product Promo": "Polished propaganda-style imagery interrupted by harder graphic-print hits.",
        }
        return descriptions.get(treatment, "A multi-shot process that changes visual treatment across the video.")
    pack = styles.STYLE_PACKS.get(name)
    if pack is None:
        return "Visual process."
    category = STYLE_CATEGORIES.get(name, "Style")
    return f"{category} · {pack.description}"


def _style_intensity(style_name: str) -> float:
    """Choose one invisible creative-strength default for a single-style pass."""
    stability = STYLE_STABILITY.get(style_name, "Medium")
    if stability == "Experimental":
        return 1.0
    if stability == "High":
        return 0.88
    return 0.94


def apply_simple_process(timeline: dict[str, Any], process_name: str) -> dict[str, Any]:
    """Mutate a shot timeline into exactly the process selected by the user."""
    if process_name in SEQUENCE_PROCESSES:
        return apply_treatment(timeline, SEQUENCE_PROCESSES[process_name])

    if process_name not in styles.STYLE_PACKS:
        raise ValueError(f"Unknown ComicFrame process: {process_name}")

    intensity = _style_intensity(process_name)
    for shot in timeline.get("shots", []):
        if isinstance(shot, dict):
            _set_shot(shot, process_name, intensity, intensity, "linear")
    timeline["treatment"] = f"Single Style · {process_name}"
    timeline["simple_process"] = process_name
    return timeline


def output_slug(process_name: str) -> str:
    text = process_name.replace("→", " to ")
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return text[:64] or "styled"


def next_output_path(video: Path, process_name: str) -> Path:
    """Return a non-destructive result path beside the source video."""
    video = Path(video).expanduser().resolve()
    stem = f"{video.stem}_comicframe_{output_slug(process_name)}"
    candidate = video.with_name(stem + ".mp4")
    index = 2
    while candidate.exists():
        candidate = video.with_name(f"{stem}_{index}.mp4")
        index += 1
    return candidate


class ComicFrameStudioApp(UsabilityComicFrameStudioApp):
    """The full ComicFrame engine behind a deliberately tiny product surface."""

    def __init__(self):
        register_artistic_expansion()
        super().__init__()
        self.title("ComicFrame Studio 3.0 · Video In / Video Out")
        self.geometry("940x820")
        self.minsize(780, 680)

        self._simple_output_path: Path | None = None
        self._simple_preview_ref = None
        self._simple_busy = False
        self._install_simple_shell()

    # ---------- Product shell ----------

    @staticmethod
    def _forget_widget(widget) -> None:
        try:
            manager = widget.winfo_manager()
            if manager == "pack":
                widget.pack_forget()
            elif manager == "grid":
                widget.grid_remove()
            elif manager == "place":
                widget.place_forget()
        except Exception:
            pass

    def _install_simple_shell(self) -> None:
        # The engine UI is still instantiated so every mature renderer layer keeps
        # its variables and widget references.  It is not the product UI anymore.
        for child in list(self.winfo_children()):
            self._forget_widget(child)

        self.simple_video_var = tk.StringVar(value="No video selected")
        self.simple_process_var = tk.StringVar(value="Graphic Shock · maximum print")
        self.simple_process_info_var = tk.StringVar(value=process_description(self.simple_process_var.get()))
        self.simple_result_var = tk.StringVar(value="")

        shell = ttk.Frame(self, padding=26)
        shell.pack(fill="both", expand=True)
        self.simple_shell = shell

        header = ttk.Frame(shell)
        header.pack(fill="x", pady=(0, 18))
        ttk.Label(header, text="ComicFrame", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Video in. Pick a process. Video out.",
            style="Subtitle.TLabel",
            font=("Segoe UI", 11),
        ).pack(anchor="w", pady=(3, 0))

        source = ttk.LabelFrame(shell, text="VIDEO", padding=14)
        source.pack(fill="x")
        source_row = ttk.Frame(source, style="Panel.TFrame")
        source_row.pack(fill="x")
        ttk.Button(
            source_row,
            text="CHOOSE VIDEO",
            style="Accent.TButton",
            command=self._simple_choose_video,
        ).pack(side="left")
        ttk.Label(
            source_row,
            textvariable=self.simple_video_var,
            style="Panel.TLabel",
        ).pack(side="left", fill="x", expand=True, padx=(12, 0))

        preview_wrap = ttk.Frame(source, style="Panel.TFrame")
        preview_wrap.pack(fill="both", expand=True, pady=(12, 0))
        self.simple_preview = tk.Label(
            preview_wrap,
            text="Choose a video",
            bg="#101116",
            fg="#9da5b4",
            font=("Segoe UI", 12),
            height=19,
            anchor="center",
        )
        self.simple_preview.pack(fill="both", expand=True)

        process = ttk.LabelFrame(shell, text="PROCESS", padding=14)
        process.pack(fill="x", pady=(14, 0))
        process_row = ttk.Frame(process, style="Panel.TFrame")
        process_row.pack(fill="x")
        self.simple_process_combo = ttk.Combobox(
            process_row,
            textvariable=self.simple_process_var,
            values=simple_process_catalog(),
            state="readonly",
            font=("Segoe UI", 11),
            height=18,
        )
        self.simple_process_combo.pack(side="left", fill="x", expand=True)
        self.simple_process_combo.bind("<<ComboboxSelected>>", self._simple_process_changed)
        ttk.Label(
            process,
            textvariable=self.simple_process_info_var,
            style="Muted.TLabel",
            wraplength=820,
        ).pack(anchor="w", pady=(8, 0))

        action = ttk.Frame(shell)
        action.pack(fill="x", pady=(18, 0))
        self.simple_process_button = ttk.Button(
            action,
            text="PROCESS VIDEO",
            style="Accent.TButton",
            command=self._simple_process_clicked,
        )
        self.simple_process_button.pack(side="left", fill="x", expand=True)
        self.simple_cancel_button = ttk.Button(
            action,
            text="CANCEL",
            style="Danger.TButton",
            command=self._stop_clicked,
            state="disabled",
        )
        self.simple_cancel_button.pack(side="left", padx=(8, 0))

        ttk.Progressbar(shell, variable=self.progress, maximum=100).pack(fill="x", pady=(14, 4))
        ttk.Label(shell, textvariable=self.progress_label_var, style="Subtitle.TLabel").pack(anchor="w")

        self.simple_result = ttk.LabelFrame(shell, text="RESULT", padding=14)
        self.simple_result.pack(fill="x", pady=(16, 0))
        ttk.Label(
            self.simple_result,
            textvariable=self.simple_result_var,
            style="Panel.TLabel",
            wraplength=820,
        ).pack(anchor="w")
        result_actions = ttk.Frame(self.simple_result, style="Panel.TFrame")
        result_actions.pack(fill="x", pady=(10, 0))
        self.simple_open_button = ttk.Button(
            result_actions,
            text="OPEN RESULT",
            style="Accent.TButton",
            command=self._simple_open_result,
            state="disabled",
        )
        self.simple_open_button.pack(side="left")
        self.simple_save_button = ttk.Button(
            result_actions,
            text="SAVE A COPY…",
            command=self._simple_save_copy,
            state="disabled",
        )
        self.simple_save_button.pack(side="left", padx=(8, 0))
        self.simple_folder_button = ttk.Button(
            result_actions,
            text="SHOW IN FOLDER",
            command=self._simple_show_result_folder,
            state="disabled",
        )
        self.simple_folder_button.pack(side="left", padx=(8, 0))

        # There is no project selector, checkpoint selector, ControlNet switch,
        # sampler, subject panel, cache panel, advanced toggle, or log console here.
        # Those are implementation details of the process button.
        self.progress_label_var.set("Ready")

    def _simple_process_changed(self, _event=None) -> None:
        self.simple_process_info_var.set(process_description(self.simple_process_var.get()))

    def _simple_choose_video(self) -> None:
        if self._simple_busy:
            return
        path = filedialog.askopenfilename(
            title="Choose a video",
            filetypes=[
                ("Video files", "*.mp4 *.mov *.mkv *.avi *.webm *.m4v"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        video = Path(path).expanduser().resolve()
        self.video_var.set(str(video))
        # Project/cache storage is now an implementation detail, always derived
        # from the source.  The operator never has to name or understand it.
        self.work_var.set(str(default_project_path_for_video(video)))
        self.simple_video_var.set(video.name)
        self.simple_result_var.set("")
        self._simple_output_path = None
        self._simple_set_result_buttons(False)
        self.progress.set(0)
        self.progress_label_var.set("Ready to process")
        threading.Thread(target=self._make_source_preview, daemon=True).start()

    def _make_source_preview(self):
        # Keep v2.9.2's temp-file safety, then mirror the result into the tiny UI.
        super()._make_source_preview()
        video_text = str(self.video_var.get() or "").strip()
        if not video_text:
            return
        preview = source_preview_cache_path(Path(video_text))
        if preview.exists():
            try:
                self.after(0, lambda p=preview: self._simple_show_image(p))
            except Exception:
                pass

    def _simple_show_image(self, path: Path) -> None:
        try:
            with Image.open(path) as source:
                image = ImageOps.contain(source.convert("RGB"), (820, 390), Image.Resampling.LANCZOS)
            canvas = Image.new("RGB", (820, 390), (16, 17, 22))
            canvas.paste(image, ((820 - image.width) // 2, (390 - image.height) // 2))
            photo = ImageTk.PhotoImage(canvas)
            self.simple_preview.configure(image=photo, text="", height=390)
            self._simple_preview_ref = photo
        except Exception:
            pass

    # ---------- One-button processing ----------

    def _simple_apply_hidden_defaults(self) -> None:
        defaults = {
            "director_easy_var": True,
            "performance_mode_var": "Balanced",
            "seed_mode_var": "fixed",
            "control_required_var": True,
            "control_enabled_var": True,
            "reference_level_var": "Strong",
            "reference_backend_override_var": "Auto",
            "autopilot_mode_var": "Balanced",
        }
        for name, value in defaults.items():
            variable = getattr(self, name, None)
            try:
                if variable is not None and hasattr(variable, "set"):
                    variable.set(value)
            except Exception:
                pass

    def _simple_process_clicked(self) -> None:
        if self._simple_busy:
            return
        video_text = str(self.video_var.get() or "").strip()
        if not video_text:
            messagebox.showwarning("ComicFrame", "Choose a video first.")
            return
        video = Path(video_text).expanduser().resolve()
        if not video.exists():
            messagebox.showerror("ComicFrame", "The selected video no longer exists.")
            return
        process_name = self.simple_process_var.get()
        if process_name not in simple_process_catalog():
            messagebox.showerror("ComicFrame", "Choose a valid process.")
            return

        self._simple_set_busy(True)
        self.simple_result_var.set("")
        self._simple_output_path = None
        self._simple_set_result_buttons(False)
        self.progress.set(0)
        self.progress_label_var.set("Preparing video…")

        def job() -> None:
            try:
                self._simple_apply_hidden_defaults()
                # Refresh the backend at job time. Startup discovery may have run
                # before Forge/A1111 was fully ready.
                try:
                    self._sync_webui()
                except Exception as exc:
                    self._log(f"Backend refresh warning: {exc}")

                self._extract_frames()
                timeline = self._analyze_shots()
                apply_simple_process(timeline, process_name)
                self._director_timeline = timeline
                self._save_director_timeline()
                self._log(f"Simple Flow: {process_name}")
                self._render_range(1, None, False)

                final = Path(self.project_paths()["final"])
                if not final.exists() or final.stat().st_size <= 0:
                    raise RuntimeError("Rendering finished but ComicFrame did not produce a final video file.")
                output = next_output_path(video, process_name)
                shutil.copy2(final, output)
                self._simple_output_path = output

                # Show one rendered frame as an immediate visual receipt.
                styled = Path(self.project_paths()["styled"])
                representative = next(iter(sorted(styled.glob("frame_*.png"))), None)
                if representative is not None:
                    self.after(0, lambda p=representative: self._simple_show_image(p))

                def success() -> None:
                    self.progress.set(100)
                    self.progress_label_var.set("Video ready")
                    self.simple_result_var.set(str(output))
                    self._simple_set_result_buttons(True)

                self.after(0, success)
            except Exception as exc:
                self._log(f"ERROR: {exc}")
                try:
                    title, detail = friendly_error_text(str(exc))
                except Exception:
                    title, detail = "Processing failed", str(exc)

                def failure() -> None:
                    self.progress_label_var.set("Processing failed")
                    messagebox.showerror(title or "Processing failed", detail or str(exc))

                self.after(0, failure)
            finally:
                try:
                    self.after(0, lambda: self._simple_set_busy(False))
                except Exception:
                    pass

        self._run_worker(job)

    def _simple_set_busy(self, busy: bool) -> None:
        self._simple_busy = bool(busy)
        try:
            self.simple_process_button.configure(state="disabled" if busy else "normal")
            self.simple_process_combo.configure(state="disabled" if busy else "readonly")
            self.simple_cancel_button.configure(state="normal" if busy else "disabled")
        except Exception:
            pass

    def _simple_set_result_buttons(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for button in (
            getattr(self, "simple_open_button", None),
            getattr(self, "simple_save_button", None),
            getattr(self, "simple_folder_button", None),
        ):
            try:
                if button is not None:
                    button.configure(state=state)
            except Exception:
                pass

    # ---------- Result actions ----------

    def _simple_valid_output(self) -> Path | None:
        path = self._simple_output_path
        return path if path is not None and path.exists() else None

    @staticmethod
    def _open_path(path: Path) -> None:
        path = Path(path)
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def _simple_open_result(self) -> None:
        path = self._simple_valid_output()
        if path is not None:
            self._open_path(path)

    def _simple_show_result_folder(self) -> None:
        path = self._simple_valid_output()
        if path is None:
            return
        if os.name == "nt":
            subprocess.Popen(["explorer", "/select,", str(path)])
        else:
            self._open_path(path.parent)

    def _simple_save_copy(self) -> None:
        source = self._simple_valid_output()
        if source is None:
            return
        target = filedialog.asksaveasfilename(
            title="Save processed video",
            initialfile=source.name,
            defaultextension=".mp4",
            filetypes=[("MP4 video", "*.mp4"), ("All files", "*.*")],
        )
        if target:
            shutil.copy2(source, Path(target))

    # ---------- Resume compatibility ----------

    @staticmethod
    def _profile_without_director(profile: dict[str, Any]) -> dict[str, Any]:
        normalized = UsabilityComicFrameStudioApp._profile_without_director(profile)
        normalized.pop("simple_shell", None)
        return normalized

    def _render_profile(self) -> dict[str, Any]:
        profile = super()._render_profile()
        profile["simple_shell"] = {
            "version": SIMPLE_VERSION,
            "operator_surface": "video -> process -> video",
            "engine_controls_hidden": True,
        }
        profile["app_version"] = SIMPLE_VERSION
        return profile


def main():
    ComicFrameStudioApp().mainloop()


if __name__ == "__main__":
    main()
