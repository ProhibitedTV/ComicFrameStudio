#!/usr/bin/env python3
"""ComicFrame Studio v3.2 — visible processing presence.

v3.1 fixed the operator surface. v3.2 fixes the remaining perception problem:
long SDXL frame renders must never look like a frozen application.

This layer adds no renderer controls and changes no render semantics. It only
turns existing progress/output state into continuous, redundant visual feedback:

* pulsing PROCESSING action state
* elapsed-time heartbeat independent of render progress
* current frame / total frame presentation
* live preview of newly completed styled frames
* compact cancel action instead of a dominant destructive bar
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

import tkinter as tk
from tkinter import ttk

from comicframe_interface import (
    ACCENT,
    ACCENT_HOVER,
    ACCENT_SOFT,
    BG,
    BORDER,
    CARD,
    CARD_ALT,
    GOOD,
    MUTED,
    TEXT,
    ComicFrameStudioApp as InterfaceApp,
    process_display_name,
)

PRESENCE_VERSION = "3.2"
LIVE_PREVIEW_EVERY = 5

_FRAME_PROGRESS_RE = re.compile(r"^\s*(\d+)\s*/\s*(\d+)\s*:\s*(frame_(\d+)\.png)\s*$", re.IGNORECASE)


def parse_render_progress(label: str) -> tuple[int, int, str, int] | None:
    """Parse the renderer's stable ``idx/total: frame_N.png`` progress label."""
    match = _FRAME_PROGRESS_RE.match(str(label or ""))
    if not match:
        return None
    index = int(match.group(1))
    total = int(match.group(2))
    filename = match.group(3)
    frame_number = int(match.group(4))
    if index < 0 or total <= 0 or index > total:
        return None
    return index, total, filename, frame_number


def format_elapsed(seconds: float) -> str:
    """Human heartbeat timer with hours only when they are useful."""
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d} elapsed"
    return f"{minutes:02d}:{secs:02d} elapsed"


def should_refresh_live_preview(frame_number: int, last_frame: int | None, every: int = LIVE_PREVIEW_EVERY) -> bool:
    """Throttle expensive preview image loads without making the UI feel stale."""
    frame_number = int(frame_number)
    if frame_number <= 0:
        return False
    if last_frame is None:
        return True
    if frame_number <= int(last_frame):
        return False
    return frame_number - int(last_frame) >= max(1, int(every))


def friendly_activity(label: str) -> str:
    """Translate existing engine phase text into compact operator-facing activity."""
    text = str(label or "").strip()
    parsed = parse_render_progress(text)
    if parsed:
        index, total, _filename, frame_number = parsed
        return f"Rendering frame {frame_number} · {index} of {total} complete"
    lowered = text.lower()
    if "extract" in lowered and "frame" in lowered:
        return "Preparing source frames"
    if "source verified" in lowered:
        return text
    if "analy" in lowered and "shot" in lowered:
        return "Reading shot changes"
    if "checkpoint" in lowered and ("load" in lowered or "loading" in lowered):
        return "Preparing renderer"
    if "assembl" in lowered or "reassembl" in lowered:
        return "Building final video"
    if "audio" in lowered:
        return "Restoring source audio"
    if "upscal" in lowered:
        return "Finishing output resolution"
    if text:
        return text
    return "Working"


class ComicFrameStudioApp(InterfaceApp):
    """v3.1 interface with continuous visible render activity."""

    def __init__(self):
        super().__init__()
        self.title("ComicFrame Studio 3.2 · Video In / Video Out")

    # ---------- Presence UI ----------

    def _configure_simple_interface_styles(self) -> None:
        super()._configure_simple_interface_styles()
        style = ttk.Style(self)
        # These styles are intentionally bright even while disabled. The button
        # becomes a status surface while work is running, not an inert control.
        style.configure(
            "WorkingBright.TButton",
            background=ACCENT,
            foreground="#ffffff",
            bordercolor=ACCENT,
            font=("Segoe UI Semibold", 12),
            padding=(20, 13),
        )
        style.map(
            "WorkingBright.TButton",
            background=[("disabled", ACCENT), ("active", ACCENT_HOVER)],
            foreground=[("disabled", "#ffffff")],
        )
        style.configure(
            "WorkingDim.TButton",
            background="#493d79",
            foreground="#ddd7ff",
            bordercolor="#5e4d96",
            font=("Segoe UI Semibold", 12),
            padding=(20, 13),
        )
        style.map(
            "WorkingDim.TButton",
            background=[("disabled", "#493d79")],
            foreground=[("disabled", "#ddd7ff")],
        )

    def _install_simple_shell(self) -> None:
        super()._install_simple_shell()

        self.simple_activity_title_var = tk.StringVar(value="PROCESSING")
        self.simple_activity_detail_var = tk.StringVar(value="Working")
        self.simple_activity_elapsed_var = tk.StringVar(value="00:00 elapsed")
        self.simple_activity_frame_var = tk.StringVar(value="")

        self._presence_started_at: float | None = None
        self._presence_tick_job = None
        self._presence_pulse = False
        self._presence_last_preview_frame: int | None = None
        self._presence_preview_pending: Path | None = None

        # The v3.1 progress row is the parent of the cancel button. Insert one
        # compact activity card immediately before it and keep it hidden at rest.
        self._presence_progress_row = self.simple_cancel_button.master
        self.simple_activity = tk.Frame(
            self.simple_shell,
            bg=CARD,
            highlightbackground=BORDER,
            highlightthickness=1,
            padx=14,
            pady=10,
        )

        left = tk.Frame(self.simple_activity, bg=CARD)
        left.pack(side="left", fill="x", expand=True)
        title_row = tk.Frame(left, bg=CARD)
        title_row.pack(anchor="w", fill="x")
        self.simple_activity_dot = tk.Label(
            title_row,
            text="●",
            bg=CARD,
            fg=ACCENT,
            font=("Segoe UI", 13),
        )
        self.simple_activity_dot.pack(side="left", padx=(0, 7))
        tk.Label(
            title_row,
            textvariable=self.simple_activity_title_var,
            bg=CARD,
            fg=TEXT,
            font=("Segoe UI Semibold", 10),
        ).pack(side="left")
        tk.Label(
            left,
            textvariable=self.simple_activity_detail_var,
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 9),
            anchor="w",
        ).pack(anchor="w", pady=(2, 0))

        right = tk.Frame(self.simple_activity, bg=CARD)
        right.pack(side="right", padx=(18, 0))
        tk.Label(
            right,
            textvariable=self.simple_activity_frame_var,
            bg=CARD,
            fg="#bcaeff",
            font=("Segoe UI Semibold", 9),
            anchor="e",
        ).pack(anchor="e")
        tk.Label(
            right,
            textvariable=self.simple_activity_elapsed_var,
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 9),
            anchor="e",
        ).pack(anchor="e", pady=(2, 0))

        # v3.1 already traces numeric progress. The textual label arrives after
        # the numeric value in the queue poll, so this trace is where completed
        # frame paths are guaranteed to exist for live preview.
        self.progress_label_var.trace_add("write", self._presence_progress_label_changed)

    # ---------- Busy / heartbeat ----------

    def _simple_set_busy(self, busy: bool) -> None:
        super()._simple_set_busy(busy)
        busy = bool(busy)

        if busy:
            self._presence_started_at = time.monotonic()
            self._presence_last_preview_frame = None
            self._presence_pulse = False
            self.simple_activity_title_var.set(
                f"PROCESSING · {process_display_name(self.simple_process_var.get())}"
            )
            self.simple_activity_detail_var.set("Preparing video")
            self.simple_activity_frame_var.set("")
            self.simple_activity_elapsed_var.set("00:00 elapsed")
            self.simple_preview_badge.configure(
                text="WORKING",
                bg=ACCENT_SOFT,
                fg="#c7bbff",
            )

            if not self.simple_activity.winfo_manager():
                self.simple_activity.pack(
                    fill="x",
                    pady=(14, 0),
                    before=self._presence_progress_row,
                )

            # v3.1 intentionally made cancel visible only while processing, but
            # a full-width red bar visually dominated the useful state. Repack it
            # as a small escape hatch on the right.
            try:
                self.simple_cancel_button.pack_forget()
                self.simple_cancel_button.configure(text="CANCEL")
                self.simple_cancel_button.pack(side="right", anchor="e", pady=(8, 0))
            except Exception:
                pass

            try:
                self.simple_process_list.configure(
                    bg="#0f1117",
                    fg="#606879",
                    selectbackground="#362d5a",
                    disabledforeground="#606879",
                )
            except Exception:
                pass
            self._presence_schedule_tick()
        else:
            self._presence_cancel_tick()
            try:
                self.simple_activity.pack_forget()
                self.simple_process_button.configure(style="Hero.TButton", text="PROCESS VIDEO")
                self.simple_process_list.configure(
                    bg=CARD_ALT,
                    fg="#cbd1dc",
                    selectbackground=ACCENT,
                )
            except Exception:
                pass
            try:
                if self._simple_valid_output() is not None:
                    self.simple_preview_badge.configure(
                        text="RESULT",
                        bg="#173522",
                        fg=GOOD,
                    )
                else:
                    self.simple_preview_badge.configure(
                        text="SOURCE",
                        bg=ACCENT_SOFT,
                        fg="#c7bbff",
                    )
            except Exception:
                pass

    def _presence_schedule_tick(self) -> None:
        if self._presence_tick_job is None:
            self._presence_tick_job = self.after(120, self._presence_tick)

    def _presence_cancel_tick(self) -> None:
        job = self._presence_tick_job
        self._presence_tick_job = None
        if job is not None:
            try:
                self.after_cancel(job)
            except Exception:
                pass

    def _presence_tick(self) -> None:
        self._presence_tick_job = None
        if not bool(getattr(self, "_simple_busy", False)):
            return

        self._presence_pulse = not self._presence_pulse
        bright = self._presence_pulse
        try:
            self.simple_activity_dot.configure(fg=ACCENT if bright else "#554a7b")
            self.simple_process_button.configure(
                style="WorkingBright.TButton" if bright else "WorkingDim.TButton",
                text=f"●  PROCESSING  ·  {self.simple_progress_pct_var.get()}",
            )
        except Exception:
            pass

        if self._presence_started_at is not None:
            self.simple_activity_elapsed_var.set(
                format_elapsed(time.monotonic() - self._presence_started_at)
            )

        self._presence_tick_job = self.after(500, self._presence_tick)

    # ---------- Progress / live preview ----------

    def _presence_progress_label_changed(self, *_args) -> None:
        if not bool(getattr(self, "_simple_busy", False)):
            return
        label = str(self.progress_label_var.get() or "")
        self.simple_activity_detail_var.set(friendly_activity(label))

        parsed = parse_render_progress(label)
        if not parsed:
            lowered = label.lower()
            if "assembl" in lowered or "audio" in lowered or "upscal" in lowered:
                self.simple_activity_frame_var.set("FINALIZING")
                try:
                    self.simple_preview_badge.configure(text="FINALIZING")
                except Exception:
                    pass
            return

        index, total, filename, frame_number = parsed
        self.simple_activity_frame_var.set(f"FRAME {index} / {total}")

        if not should_refresh_live_preview(frame_number, self._presence_last_preview_frame):
            return
        try:
            path = Path(self.project_paths()["styled"]) / filename
        except Exception:
            return
        if not path.exists() or path.stat().st_size <= 0:
            return

        self._presence_last_preview_frame = frame_number
        self._presence_preview_pending = path
        self.after_idle(lambda p=path, i=index, t=total: self._presence_apply_live_preview(p, i, t))

    def _presence_apply_live_preview(self, path: Path, index: int, total: int) -> None:
        if not bool(getattr(self, "_simple_busy", False)):
            return
        if self._presence_preview_pending != path or not path.exists():
            return
        self._simple_show_image(path)
        try:
            self.simple_preview_badge.configure(
                text=f"LIVE · {index}/{total}",
                bg=ACCENT_SOFT,
                fg="#d6ceff",
            )
        except Exception:
            pass

    # ---------- Compatibility ----------

    def _render_profile(self) -> dict[str, Any]:
        profile = super()._render_profile()
        shell = profile.setdefault("simple_shell", {})
        if isinstance(shell, dict):
            shell["presence_version"] = PRESENCE_VERSION
            shell["live_preview_every"] = LIVE_PREVIEW_EVERY
        return profile


def main():
    ComicFrameStudioApp().mainloop()


if __name__ == "__main__":
    main()
