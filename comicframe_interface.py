#!/usr/bin/env python3
"""ComicFrame Studio v3.1 — focused video/process/result interface.

The renderer remains the v3.0 simple-flow engine.  This layer only changes the
operator surface: a large responsive preview, a visible process browser, one
primary action, compact progress, and a result card that appears only when a
result exists.
"""
from __future__ import annotations

from pathlib import Path

import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageOps, ImageTk

import comicframe_styles as styles
from comicframe_artistic import STYLE_CATEGORIES, STYLE_STABILITY
from comicframe_simple import (
    ComicFrameStudioApp as SimpleFlowApp,
    SEQUENCE_PROCESSES,
    process_description,
    simple_process_catalog,
)

INTERFACE_VERSION = "3.1"

BG = "#0d0f14"
CARD = "#171a22"
CARD_ALT = "#12151c"
BORDER = "#2b3040"
TEXT = "#f3f5fb"
MUTED = "#8f98aa"
ACCENT = "#7c5cff"
ACCENT_HOVER = "#927dff"
ACCENT_SOFT = "#25203b"
GOOD = "#52d273"
DANGER = "#693039"


def process_display_name(name: str) -> str:
    """Short public label for the process browser."""
    if " · " in name:
        return name.split(" · ", 1)[0]
    return name


def process_meta(name: str) -> str:
    if name in SEQUENCE_PROCESSES:
        return "SEQUENCE · shot-aware progression"
    category = STYLE_CATEGORIES.get(name, "Style")
    stability = STYLE_STABILITY.get(name, "Medium")
    return f"{category.upper()} · {stability.lower()} continuity"


def process_rows() -> list[tuple[str, str]]:
    """Return stable (display, canonical) rows for the browser."""
    rows: list[tuple[str, str]] = []
    seen: set[str] = set()
    for canonical in simple_process_catalog():
        label = process_display_name(canonical)
        # Labels are expected to be unique. Keep a deterministic fallback if a
        # future style family introduces the same short name.
        if label in seen:
            label = canonical
        seen.add(label)
        rows.append((label, canonical))
    return rows


class ComicFrameStudioApp(SimpleFlowApp):
    """v3.0 processing engine with the v3.1 product interface."""

    def __init__(self):
        super().__init__()
        self.title("ComicFrame Studio 3.1 · Video In / Video Out")
        self.geometry("1180x760")
        self.minsize(980, 680)

    # ---------- Interface construction ----------

    def _configure_simple_interface_styles(self) -> None:
        style = ttk.Style(self)
        style.configure(
            "Hero.TButton",
            background=ACCENT,
            foreground="#ffffff",
            bordercolor=ACCENT,
            font=("Segoe UI Semibold", 12),
            padding=(20, 13),
        )
        style.map(
            "Hero.TButton",
            background=[("active", ACCENT_HOVER), ("disabled", "#38334b")],
            foreground=[("disabled", "#8f899e")],
        )
        style.configure(
            "Compact.TButton",
            background="#20242e",
            foreground=TEXT,
            bordercolor=BORDER,
            font=("Segoe UI Semibold", 9),
            padding=(12, 7),
        )
        style.map("Compact.TButton", background=[("active", "#2b3040")])
        style.configure(
            "Cancel.TButton",
            background=DANGER,
            foreground="#ffecef",
            bordercolor="#8c4650",
            font=("Segoe UI Semibold", 9),
            padding=(12, 7),
        )
        style.map("Cancel.TButton", background=[("active", "#82414a")])
        style.configure(
            "Simple.Horizontal.TProgressbar",
            troughcolor="#1a1e27",
            background=ACCENT,
            bordercolor="#1a1e27",
            lightcolor=ACCENT,
            darkcolor=ACCENT,
            thickness=7,
        )

    def _install_simple_shell(self) -> None:
        # The legacy engine UI is still created because mature renderer layers
        # own variables/widgets there.  It is intentionally removed from view.
        for child in list(self.winfo_children()):
            self._forget_widget(child)

        self.configure(bg=BG)
        self._configure_simple_interface_styles()

        self.simple_video_var = tk.StringVar(value="No video selected")
        self.simple_process_var = tk.StringVar(value="Graphic Shock · maximum print")
        self.simple_process_info_var = tk.StringVar(value=process_description(self.simple_process_var.get()))
        self.simple_process_meta_var = tk.StringVar(value=process_meta(self.simple_process_var.get()))
        self.simple_selected_title_var = tk.StringVar(value=process_display_name(self.simple_process_var.get()))
        self.simple_result_var = tk.StringVar(value="")
        self.simple_progress_pct_var = tk.StringVar(value="0%")
        self._simple_process_rows = process_rows()
        self._simple_preview_path: Path | None = None
        self._simple_preview_resize_job = None

        shell = tk.Frame(self, bg=BG, padx=28, pady=22)
        shell.pack(fill="both", expand=True)
        self.simple_shell = shell

        # Header: brand at left, source control at right. No bordered form header.
        header = tk.Frame(shell, bg=BG)
        header.pack(fill="x", pady=(0, 18))
        brand = tk.Frame(header, bg=BG)
        brand.pack(side="left", fill="x", expand=True)
        tk.Label(
            brand,
            text="ComicFrame",
            bg=BG,
            fg=TEXT,
            font=("Segoe UI Semibold", 24),
        ).pack(anchor="w")
        tk.Label(
            brand,
            text="Choose a clip. Choose a look. Get a video.",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(2, 0))

        source_ctl = tk.Frame(header, bg=BG)
        source_ctl.pack(side="right", anchor="e", padx=(20, 0))
        tk.Label(
            source_ctl,
            textvariable=self.simple_video_var,
            bg=BG,
            fg="#b9c0cf",
            font=("Segoe UI", 9),
            anchor="e",
        ).pack(side="left", padx=(0, 10))
        self.simple_choose_button = ttk.Button(
            source_ctl,
            text="CHOOSE VIDEO",
            style="Compact.TButton",
            command=self._simple_choose_video,
        )
        self.simple_choose_button.pack(side="left")

        # Main workspace: preview and process browser side-by-side.
        body = tk.Frame(shell, bg=BG)
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=7, minsize=560)
        body.grid_columnconfigure(1, weight=4, minsize=330)
        body.grid_rowconfigure(0, weight=1)

        preview_card = tk.Frame(
            body,
            bg=CARD,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        preview_card.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        preview_card.grid_rowconfigure(1, weight=1)
        preview_card.grid_columnconfigure(0, weight=1)

        preview_head = tk.Frame(preview_card, bg=CARD, padx=15, pady=11)
        preview_head.grid(row=0, column=0, sticky="ew")
        tk.Label(
            preview_head,
            text="VIDEO",
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI Semibold", 9),
        ).pack(side="left")
        self.simple_preview_badge = tk.Label(
            preview_head,
            text="SOURCE",
            bg=ACCENT_SOFT,
            fg="#c7bbff",
            font=("Segoe UI Semibold", 8),
            padx=8,
            pady=3,
        )
        self.simple_preview_badge.pack(side="right")

        self.simple_preview = tk.Canvas(
            preview_card,
            bg="#090a0e",
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.simple_preview.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.simple_preview.bind("<Button-1>", lambda _event: self._simple_choose_video())
        self.simple_preview.bind("<Configure>", self._simple_preview_configured)
        self._simple_draw_placeholder()

        process_card = tk.Frame(
            body,
            bg=CARD,
            highlightbackground=BORDER,
            highlightthickness=1,
            padx=16,
            pady=14,
        )
        process_card.grid(row=0, column=1, sticky="nsew")
        process_card.grid_rowconfigure(3, weight=1)
        process_card.grid_columnconfigure(0, weight=1)

        tk.Label(
            process_card,
            text="PROCESS",
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI Semibold", 9),
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            process_card,
            textvariable=self.simple_selected_title_var,
            bg=CARD,
            fg=TEXT,
            font=("Segoe UI Semibold", 19),
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", pady=(5, 1))
        tk.Label(
            process_card,
            textvariable=self.simple_process_meta_var,
            bg=CARD,
            fg="#a999ff",
            font=("Segoe UI Semibold", 8),
            anchor="w",
        ).grid(row=2, column=0, sticky="ew", pady=(0, 10))

        list_wrap = tk.Frame(process_card, bg=CARD_ALT, highlightbackground=BORDER, highlightthickness=1)
        list_wrap.grid(row=3, column=0, sticky="nsew")
        list_wrap.grid_rowconfigure(0, weight=1)
        list_wrap.grid_columnconfigure(0, weight=1)
        self.simple_process_list = tk.Listbox(
            list_wrap,
            bg=CARD_ALT,
            fg="#cbd1dc",
            selectbackground=ACCENT,
            selectforeground="#ffffff",
            activestyle="none",
            highlightthickness=0,
            bd=0,
            relief="flat",
            exportselection=False,
            font=("Segoe UI", 10),
            selectmode="browse",
        )
        self.simple_process_list.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=7)
        scroll = ttk.Scrollbar(list_wrap, orient="vertical", command=self.simple_process_list.yview)
        scroll.grid(row=0, column=1, sticky="ns", pady=7, padx=(2, 5))
        self.simple_process_list.configure(yscrollcommand=scroll.set)
        for display, _canonical in self._simple_process_rows:
            self.simple_process_list.insert("end", display)
        self.simple_process_list.selection_set(0)
        self.simple_process_list.activate(0)
        self.simple_process_list.bind("<<ListboxSelect>>", self._simple_process_list_changed)

        self.simple_process_description = tk.Label(
            process_card,
            textvariable=self.simple_process_info_var,
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 9),
            justify="left",
            anchor="nw",
            wraplength=330,
        )
        self.simple_process_description.grid(row=4, column=0, sticky="ew", pady=(11, 12))

        self.simple_process_button = ttk.Button(
            process_card,
            text="PROCESS VIDEO",
            style="Hero.TButton",
            command=self._simple_process_clicked,
        )
        self.simple_process_button.grid(row=5, column=0, sticky="ew")

        # Progress is compact and always visible; Cancel only appears during work.
        progress_row = tk.Frame(shell, bg=BG)
        progress_row.pack(fill="x", pady=(14, 0))
        progress_text = tk.Frame(progress_row, bg=BG)
        progress_text.pack(fill="x")
        tk.Label(
            progress_text,
            textvariable=self.progress_label_var,
            bg=BG,
            fg="#b4bccb",
            font=("Segoe UI", 9),
        ).pack(side="left")
        tk.Label(
            progress_text,
            textvariable=self.simple_progress_pct_var,
            bg=BG,
            fg=MUTED,
            font=("Segoe UI Semibold", 9),
        ).pack(side="right")
        ttk.Progressbar(
            progress_row,
            variable=self.progress,
            maximum=100,
            style="Simple.Horizontal.TProgressbar",
        ).pack(fill="x", pady=(5, 0))
        self.simple_cancel_button = ttk.Button(
            progress_row,
            text="CANCEL PROCESSING",
            style="Cancel.TButton",
            command=self._stop_clicked,
        )
        # Hidden until processing starts.

        # Result is intentionally absent until a result exists.
        self.simple_result = tk.Frame(
            shell,
            bg="#131d18",
            highlightbackground="#2c5a40",
            highlightthickness=1,
            padx=14,
            pady=12,
        )
        result_copy = tk.Frame(self.simple_result, bg="#131d18")
        result_copy.pack(side="left", fill="x", expand=True)
        tk.Label(
            result_copy,
            text="VIDEO READY",
            bg="#131d18",
            fg=GOOD,
            font=("Segoe UI Semibold", 9),
        ).pack(anchor="w")
        tk.Label(
            result_copy,
            textvariable=self.simple_result_var,
            bg="#131d18",
            fg="#d9e5dc",
            font=("Segoe UI", 9),
            anchor="w",
        ).pack(anchor="w", pady=(2, 0))

        result_actions = tk.Frame(self.simple_result, bg="#131d18")
        result_actions.pack(side="right", padx=(16, 0))
        self.simple_open_button = ttk.Button(
            result_actions,
            text="OPEN VIDEO",
            style="Hero.TButton",
            command=self._simple_open_result,
            state="disabled",
        )
        self.simple_open_button.pack(side="left")
        self.simple_folder_button = ttk.Button(
            result_actions,
            text="SHOW IN FOLDER",
            style="Compact.TButton",
            command=self._simple_show_result_folder,
            state="disabled",
        )
        self.simple_folder_button.pack(side="left", padx=(8, 0))
        self.simple_save_button = ttk.Button(
            result_actions,
            text="SAVE COPY",
            style="Compact.TButton",
            command=self._simple_save_copy,
            state="disabled",
        )
        self.simple_save_button.pack(side="left", padx=(8, 0))

        self.progress.trace_add("write", self._simple_progress_changed)
        self.progress_label_var.set("Ready")

    # ---------- Process browser ----------

    def _simple_process_list_changed(self, _event=None) -> None:
        selection = self.simple_process_list.curselection()
        if not selection:
            return
        index = int(selection[0])
        if not 0 <= index < len(self._simple_process_rows):
            return
        display, canonical = self._simple_process_rows[index]
        self.simple_process_var.set(canonical)
        self.simple_selected_title_var.set(display)
        self.simple_process_meta_var.set(process_meta(canonical))
        self.simple_process_info_var.set(process_description(canonical))

    def _simple_process_changed(self, _event=None) -> None:
        # Compatibility path for engine code that updates simple_process_var.
        canonical = self.simple_process_var.get()
        self.simple_selected_title_var.set(process_display_name(canonical))
        self.simple_process_meta_var.set(process_meta(canonical))
        self.simple_process_info_var.set(process_description(canonical))

    # ---------- Responsive preview ----------

    def _simple_draw_placeholder(self) -> None:
        try:
            self.simple_preview.delete("all")
            w = max(200, self.simple_preview.winfo_width())
            h = max(180, self.simple_preview.winfo_height())
            self.simple_preview.create_text(
                w // 2,
                h // 2 - 10,
                text="Choose a video",
                fill="#c0c6d2",
                font=("Segoe UI Semibold", 16),
            )
            self.simple_preview.create_text(
                w // 2,
                h // 2 + 20,
                text="Click here or use CHOOSE VIDEO",
                fill="#646d7d",
                font=("Segoe UI", 9),
            )
        except Exception:
            pass

    def _simple_preview_configured(self, _event=None) -> None:
        if self._simple_preview_resize_job is not None:
            try:
                self.after_cancel(self._simple_preview_resize_job)
            except Exception:
                pass
        self._simple_preview_resize_job = self.after(90, self._simple_redraw_preview)

    def _simple_show_image(self, path: Path) -> None:
        self._simple_preview_path = Path(path)
        self.simple_preview_badge.configure(text="RESULT" if "styled" in str(path).lower() else "SOURCE")
        self.after_idle(self._simple_redraw_preview)

    def _simple_redraw_preview(self) -> None:
        self._simple_preview_resize_job = None
        path = self._simple_preview_path
        if path is None or not path.exists():
            self._simple_draw_placeholder()
            return
        try:
            width = max(320, int(self.simple_preview.winfo_width()))
            height = max(220, int(self.simple_preview.winfo_height()))
            with Image.open(path) as source:
                image = ImageOps.contain(
                    source.convert("RGB"),
                    (max(1, width - 2), max(1, height - 2)),
                    Image.Resampling.LANCZOS,
                )
            canvas = Image.new("RGB", (width, height), (9, 10, 14))
            canvas.paste(image, ((width - image.width) // 2, (height - image.height) // 2))
            photo = ImageTk.PhotoImage(canvas)
            self.simple_preview.delete("all")
            self.simple_preview.create_image(width // 2, height // 2, image=photo, anchor="center")
            self._simple_preview_ref = photo
        except Exception:
            self._simple_draw_placeholder()

    # ---------- State presentation ----------

    def _simple_progress_changed(self, *_args) -> None:
        try:
            value = max(0, min(100, int(round(float(self.progress.get())))))
        except Exception:
            value = 0
        self.simple_progress_pct_var.set(f"{value}%")

    def _simple_choose_video(self) -> None:
        before = str(self.video_var.get() or "")
        super()._simple_choose_video()
        after = str(self.video_var.get() or "")
        if after and after != before:
            self.simple_choose_button.configure(text="REPLACE VIDEO")
            self.simple_preview_badge.configure(text="SOURCE")
            self._simple_hide_result()

    def _simple_set_busy(self, busy: bool) -> None:
        self._simple_busy = bool(busy)
        try:
            self.simple_process_button.configure(
                state="disabled" if busy else "normal",
                text="PROCESSING…" if busy else "PROCESS VIDEO",
            )
            self.simple_process_list.configure(state="disabled" if busy else "normal")
            self.simple_choose_button.configure(state="disabled" if busy else "normal")
            if busy:
                self.simple_cancel_button.pack(fill="x", pady=(9, 0))
                self._simple_hide_result()
            else:
                self.simple_cancel_button.pack_forget()
        except Exception:
            pass

    def _simple_hide_result(self) -> None:
        try:
            self.simple_result.pack_forget()
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
        if enabled:
            try:
                if not self.simple_result.winfo_manager():
                    self.simple_result.pack(fill="x", pady=(14, 0), before=None)
            except Exception:
                pass
        else:
            self._simple_hide_result()

    # ---------- Profile metadata ----------

    def _render_profile(self) -> dict[str, Any]:
        profile = super()._render_profile()
        shell = profile.setdefault("simple_shell", {})
        shell["interface_version"] = INTERFACE_VERSION
        shell["layout"] = "responsive preview + visible process browser"
        profile["app_version"] = INTERFACE_VERSION
        return profile


def main():
    ComicFrameStudioApp().mainloop()


if __name__ == "__main__":
    main()
