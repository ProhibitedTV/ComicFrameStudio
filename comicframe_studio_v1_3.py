#!/usr/bin/env python3
"""ComicFrame Studio v1.3 - dark UI, WebUI-native model/sampler discovery, previews."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import requests
import tkinter as tk
from tkinter import messagebox, ttk
from PIL import Image, ImageTk

import comicframe_studio as v1

APP_VERSION = "1.3"

DARK = "#121318"
PANEL = "#1a1c23"
PANEL_2 = "#22252e"
BORDER = "#343844"
TEXT = "#eef1f7"
MUTED = "#9da5b4"
ACCENT = "#7c5cff"
ACCENT_2 = "#9a83ff"
GOOD = "#52d273"
WARN = "#ffbd59"
BAD = "#ff6b6b"

PRESETS = {
    "Comic Punch (recommended)": {
        "denoise": 0.48,
        "steps": 28,
        "cfg": 6.5,
        "prompt": (
            "graphic comic-book animation frame, aggressive hand-inked outlines, bold cel shading, "
            "halftone dot textures, crosshatching, posterized shadows, screen-print texture, "
            "subtle CMYK print misregistration, vivid cyan and magenta accents, orange and electric "
            "blue split lighting, strong graphic shape design, crisp illustrated details, dramatic "
            "high-contrast composition, preserve scene structure, pose, clothing, room layout, "
            "camera framing and full-body proportions"
        ),
    },
    "Balanced Comic": {
        "denoise": 0.40,
        "steps": 26,
        "cfg": 6.0,
        "prompt": (
            "cinematic comic-book illustration, inked contours, cel shading, halftone shadows, "
            "crosshatching, print texture, graphic lighting, saturated comic color separation, "
            "preserve pose, identity, scene geometry and camera framing"
        ),
    },
    "Conservative / Stable": {
        "denoise": 0.30,
        "steps": 24,
        "cfg": 6.0,
        "prompt": v1.DEFAULT_PROMPT,
    },
}

NEGATIVE = (
    "photorealism, realistic skin texture, soft painterly rendering, watercolor, blurry, "
    "low contrast, weak outlines, flat lighting, extra arms, extra legs, extra fingers, "
    "missing fingers, duplicated person, warped face, malformed face, changed hairstyle, "
    "changed clothes, cropped body, zoomed-in composition, different camera angle, changed "
    "room layout, duplicated furniture, missing furniture, text artifacts, random lettering, "
    "logo artifacts, fisheye distortion, melted objects, deformed anatomy"
)


class ComicFrameStudioV13(v1.ComicFrameStudio):
    def __init__(self):
        super().__init__()
        self.title(f"ComicFrame Studio {APP_VERSION}")
        self.geometry("1500x940")
        self.minsize(1200, 760)
        self.control_enabled_var.set(False)
        self._api_routes = set()
        self._controlnet_available = False
        self._preview_refs = {}
        self._sync_webui_background()

    def _configure_theme(self):
        self.configure(bg=DARK)
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure(".", background=DARK, foreground=TEXT, fieldbackground=PANEL_2)
        style.configure("TFrame", background=DARK)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("TLabel", background=DARK, foreground=TEXT)
        style.configure("Panel.TLabel", background=PANEL, foreground=TEXT)
        style.configure("Muted.TLabel", background=PANEL, foreground=MUTED)
        style.configure("Good.TLabel", background=PANEL, foreground=GOOD)
        style.configure("Warn.TLabel", background=PANEL, foreground=WARN)
        style.configure("Bad.TLabel", background=PANEL, foreground=BAD)
        style.configure("Title.TLabel", background=DARK, foreground=TEXT, font=("Segoe UI", 20, "bold"))
        style.configure("Subtitle.TLabel", background=DARK, foreground=MUTED, font=("Segoe UI", 10))
        style.configure("TLabelframe", background=PANEL, foreground=TEXT, bordercolor=BORDER)
        style.configure("TLabelframe.Label", background=PANEL, foreground=TEXT, font=("Segoe UI", 10, "bold"))
        style.configure("TEntry", fieldbackground=PANEL_2, foreground=TEXT, insertcolor=TEXT, bordercolor=BORDER)
        style.configure("TCombobox", fieldbackground=PANEL_2, foreground=TEXT, arrowcolor=TEXT, bordercolor=BORDER)
        style.map("TCombobox", fieldbackground=[("readonly", PANEL_2)], foreground=[("readonly", TEXT)])
        style.configure("TSpinbox", fieldbackground=PANEL_2, foreground=TEXT, arrowcolor=TEXT)
        style.configure("TCheckbutton", background=PANEL, foreground=TEXT)
        style.map("TCheckbutton", background=[("active", PANEL)])
        style.configure("TButton", background=PANEL_2, foreground=TEXT, bordercolor=BORDER, padding=(9, 5))
        style.map("TButton", background=[("active", "#2e3240")])
        style.configure("Accent.TButton", background=ACCENT, foreground="#ffffff", bordercolor=ACCENT, padding=(12, 6))
        style.map("Accent.TButton", background=[("active", ACCENT_2)])
        style.configure("Danger.TButton", background="#56242a", foreground="#ffd9dd", bordercolor="#74333b")
        style.map("Danger.TButton", background=[("active", "#693039")])
        style.configure("Horizontal.TProgressbar", troughcolor=PANEL_2, background=ACCENT, bordercolor=PANEL_2)

        self.option_add("*TCombobox*Listbox.background", PANEL_2)
        self.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.option_add("*TCombobox*Listbox.selectBackground", ACCENT)

    def _panel(self, parent, title):
        return ttk.LabelFrame(parent, text=title, padding=10)

    def _make_text(self, parent, height):
        return tk.Text(
            parent, height=height, wrap="word", bg=PANEL_2, fg=TEXT,
            insertbackground=TEXT, selectbackground=ACCENT, relief="flat",
            highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT,
            font=("Consolas", 9),
        )

    def _build_ui(self):
        self._configure_theme()

        self.checkpoint_var = tk.StringVar()
        self.loaded_checkpoint_var = tk.StringVar(value="Not synced")
        self.scheduler_var = tk.StringVar(value="")
        self.preset_var = tk.StringVar(value="Comic Punch (recommended)")
        self.webui_status_var = tk.StringVar(value="Connecting…")
        self.cn_status_var = tk.StringVar(value="Optional — not detected yet")
        self.source_preview_status = tk.StringVar(value="Choose a video")
        self.output_preview_status = tk.StringVar(value="No render yet")

        outer = ttk.Frame(self, padding=12)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 10))
        ttk.Label(header, text="ComicFrame Studio", style="Title.TLabel").pack(side="left")
        ttk.Label(
            header,
            text="video → frames → Stable Diffusion → video",
            style="Subtitle.TLabel",
        ).pack(side="left", padx=(14, 0), pady=(8, 0))
        self.webui_status_label = ttk.Label(header, textvariable=self.webui_status_var, style="Warn.TLabel")
        self.webui_status_label.pack(side="right", pady=(5, 0))

        paned = ttk.Panedwindow(outer, orient="horizontal")
        paned.pack(fill="both", expand=True)

        left_wrap = ttk.Frame(paned)
        right_wrap = ttk.Frame(paned)
        paned.add(left_wrap, weight=3)
        paned.add(right_wrap, weight=2)

        left_canvas = tk.Canvas(left_wrap, bg=DARK, highlightthickness=0)
        left_scroll = ttk.Scrollbar(left_wrap, orient="vertical", command=left_canvas.yview)
        self.left = ttk.Frame(left_canvas)
        self.left.bind("<Configure>", lambda e: left_canvas.configure(scrollregion=left_canvas.bbox("all")))
        left_canvas.create_window((0, 0), window=self.left, anchor="nw")
        left_canvas.configure(yscrollcommand=left_scroll.set)
        left_canvas.pack(side="left", fill="both", expand=True)
        left_scroll.pack(side="right", fill="y")

        self._build_source_card()
        self._build_webui_card()
        self._build_style_card()
        self._build_continuity_card()
        self._build_run_card()
        self._build_preview_card(right_wrap)
        self._build_log_card(right_wrap)

    def _build_source_card(self):
        src = self._panel(self.left, "1 · Source")
        src.pack(fill="x", pady=(0, 8))

        r = ttk.Frame(src, style="Panel.TFrame")
        r.pack(fill="x", pady=3)
        ttk.Label(r, text="Video", width=12, style="Panel.TLabel").pack(side="left")
        ttk.Entry(r, textvariable=self.video_var).pack(side="left", fill="x", expand=True, padx=5)
        ttk.Button(r, text="Browse…", command=self._browse_video).pack(side="left")

        r = ttk.Frame(src, style="Panel.TFrame")
        r.pack(fill="x", pady=3)
        ttk.Label(r, text="Project", width=12, style="Panel.TLabel").pack(side="left")
        ttk.Entry(r, textvariable=self.work_var).pack(side="left", fill="x", expand=True, padx=5)
        ttk.Button(r, text="Browse…", command=self._browse_work).pack(side="left")

        r = ttk.Frame(src, style="Panel.TFrame")
        r.pack(fill="x", pady=(7, 0))
        ttk.Button(r, text="Extract frames", command=self._extract_clicked).pack(side="left")
        ttk.Button(r, text="Refresh previews", command=self._refresh_previews).pack(side="left", padx=5)
        ttk.Button(r, text="Open project folder", command=self._open_project).pack(side="left", padx=5)

    def _build_webui_card(self):
        card = self._panel(self.left, "2 · Stable Diffusion WebUI")
        card.pack(fill="x", pady=8)

        r = ttk.Frame(card, style="Panel.TFrame")
        r.pack(fill="x", pady=3)
        ttk.Label(r, text="API", width=12, style="Panel.TLabel").pack(side="left")
        ttk.Entry(r, textvariable=self.api_var, width=34).pack(side="left", padx=5)
        ttk.Button(r, text="Sync WebUI", style="Accent.TButton", command=self._sync_webui_background).pack(side="left")

        r = ttk.Frame(card, style="Panel.TFrame")
        r.pack(fill="x", pady=3)
        ttk.Label(r, text="Checkpoint", width=12, style="Panel.TLabel").pack(side="left")
        self.checkpoint_combo = ttk.Combobox(r, textvariable=self.checkpoint_var, state="readonly")
        self.checkpoint_combo.pack(side="left", fill="x", expand=True, padx=5)
        ttk.Button(r, text="Load", command=self._load_checkpoint_clicked).pack(side="left")

        r = ttk.Frame(card, style="Panel.TFrame")
        r.pack(fill="x", pady=3)
        ttk.Label(r, text="Sampler", width=12, style="Panel.TLabel").pack(side="left")
        self.sampler_combo = ttk.Combobox(r, textvariable=self.sampler_var, state="readonly")
        self.sampler_combo.pack(side="left", fill="x", expand=True, padx=5)

        r = ttk.Frame(card, style="Panel.TFrame")
        r.pack(fill="x", pady=3)
        ttk.Label(r, text="Scheduler", width=12, style="Panel.TLabel").pack(side="left")
        self.scheduler_combo = ttk.Combobox(r, textvariable=self.scheduler_var, state="readonly")
        self.scheduler_combo.pack(side="left", fill="x", expand=True, padx=5)

        ttk.Label(
            card,
            text="ComicFrame queries the running WebUI directly for checkpoints and samplers. "
                 "The selected checkpoint is loaded once before rendering.",
            style="Muted.TLabel",
            wraplength=760,
        ).pack(anchor="w", pady=(6, 0))

    def _build_style_card(self):
        card = self._panel(self.left, "3 · Look")
        card.pack(fill="x", pady=8)

        top = ttk.Frame(card, style="Panel.TFrame")
        top.pack(fill="x", pady=(0, 6))
        ttk.Label(top, text="Preset", width=12, style="Panel.TLabel").pack(side="left")
        ttk.Combobox(
            top, textvariable=self.preset_var, state="readonly",
            values=list(PRESETS.keys()), width=30,
        ).pack(side="left", padx=5)
        ttk.Button(top, text="Apply preset", command=self._apply_preset).pack(side="left")

        ttk.Label(card, text="Positive prompt", style="Panel.TLabel").pack(anchor="w")
        self.prompt_text = self._make_text(card, 5)
        self.prompt_text.pack(fill="x", pady=(2, 6))
        self.prompt_text.insert("1.0", PRESETS[self.preset_var.get()]["prompt"])

        ttk.Label(card, text="Negative prompt", style="Panel.TLabel").pack(anchor="w")
        self.negative_text = self._make_text(card, 3)
        self.negative_text.pack(fill="x", pady=(2, 8))
        self.negative_text.insert("1.0", NEGATIVE)

        g = ttk.Frame(card, style="Panel.TFrame")
        g.pack(fill="x")
        self._dark_spin(g, "Steps", self.steps_var, 1, 100, 0)
        self._dark_spin(g, "CFG", self.cfg_var, 1, 30, 1, 0.5)
        self._dark_spin(g, "Style strength", self.denoise_var, 0.05, 0.95, 2, 0.01)
        self._dark_spin(g, "Seed", self.seed_var, -1, 2147483647, 3)
        for i in range(4):
            g.columnconfigure(i, weight=1)

        row = ttk.Frame(card, style="Panel.TFrame")
        row.pack(fill="x", pady=(7, 0))
        ttk.Label(row, text="Seed behavior", style="Panel.TLabel").pack(side="left")
        ttk.Combobox(
            row, textvariable=self.seed_mode_var, values=["fixed", "increment"],
            state="readonly", width=16,
        ).pack(side="left", padx=6)
        ttk.Label(
            row, text="Fixed is recommended for neighboring-frame consistency.",
            style="Muted.TLabel",
        ).pack(side="left", padx=6)

    def _dark_spin(self, parent, label, var, lo, hi, col, inc=1):
        box = ttk.Frame(parent, style="Panel.TFrame")
        box.grid(row=0, column=col, sticky="ew", padx=(0, 6))
        ttk.Label(box, text=label, style="Panel.TLabel").pack(anchor="w")
        ttk.Spinbox(box, textvariable=var, from_=lo, to=hi, increment=inc).pack(fill="x", pady=(2, 0))

    def _build_continuity_card(self):
        card = self._panel(self.left, "4 · Advanced continuity (optional)")
        card.pack(fill="x", pady=8)

        row = ttk.Frame(card, style="Panel.TFrame")
        row.pack(fill="x")
        self.cn_check = ttk.Checkbutton(
            row, text="Use ControlNet structural guidance",
            variable=self.control_enabled_var,
        )
        self.cn_check.pack(side="left")
        ttk.Button(row, text="Detect", command=self._detect_controlnet_background).pack(side="left", padx=7)
        self.cn_status_label = ttk.Label(row, textvariable=self.cn_status_var, style="Muted.TLabel")
        self.cn_status_label.pack(side="left", padx=5)

        ttk.Label(
            card,
            text=(
                "ControlNet is not required. It is an optional extension that can lock edges/pose/geometry "
                "when you push style strength high. If your WebUI does not expose it, leave this off."
            ),
            style="Muted.TLabel", wraplength=760,
        ).pack(anchor="w", pady=(5, 7))

        fields = ttk.Frame(card, style="Panel.TFrame")
        fields.pack(fill="x")
        ttk.Label(fields, text="Module", style="Panel.TLabel").grid(row=0, column=0, sticky="w")
        self.control_module_combo = ttk.Combobox(
            fields, textvariable=self.control_module_var,
            values=["canny", "lineart_realistic", "lineart"], width=24,
        )
        self.control_module_combo.grid(row=1, column=0, sticky="ew", padx=(0, 6))
        ttk.Label(fields, text="Model", style="Panel.TLabel").grid(row=0, column=1, sticky="w")
        self.control_model_combo = ttk.Combobox(fields, textvariable=self.control_model_var)
        self.control_model_combo.grid(row=1, column=1, sticky="ew", padx=(0, 6))
        ttk.Label(fields, text="Weight", style="Panel.TLabel").grid(row=0, column=2, sticky="w")
        ttk.Spinbox(fields, textvariable=self.control_weight_var, from_=0, to=2, increment=0.05, width=10).grid(row=1, column=2, sticky="ew")
        fields.columnconfigure(1, weight=1)

    def _build_run_card(self):
        card = self._panel(self.left, "5 · Render")
        card.pack(fill="x", pady=8)

        row = ttk.Frame(card, style="Panel.TFrame")
        row.pack(fill="x")
        ttk.Label(row, text="Test start", style="Panel.TLabel").pack(side="left")
        ttk.Spinbox(row, textvariable=self.test_start_var, from_=1, to=999999, width=8).pack(side="left", padx=5)
        ttk.Label(row, text="Frames", style="Panel.TLabel").pack(side="left", padx=(8, 0))
        ttk.Spinbox(row, textvariable=self.test_count_var, from_=1, to=500, width=8).pack(side="left", padx=5)
        ttk.Button(row, text="Render test", style="Accent.TButton", command=self._test_range_clicked).pack(side="left", padx=(12, 5))
        ttk.Button(row, text="FULL RENDER", style="Accent.TButton", command=self._full_render_clicked).pack(side="left", padx=5)
        ttk.Button(row, text="STOP", style="Danger.TButton", command=self._stop_clicked).pack(side="right")

        ttk.Progressbar(card, variable=self.progress, maximum=100).pack(fill="x", pady=(10, 3))
        ttk.Label(card, textvariable=self.progress_label_var, style="Muted.TLabel").pack(anchor="w")

    def _build_preview_card(self, parent):
        card = self._panel(parent, "Preview")
        card.pack(fill="both", expand=True, padx=(10, 0), pady=(0, 8))

        ttk.Label(card, text="Source", style="Panel.TLabel").pack(anchor="w")
        self.source_preview = tk.Label(card, bg="#0b0c10", fg=MUTED, text="No source preview", relief="flat", height=14)
        self.source_preview.pack(fill="both", expand=True, pady=(3, 3))
        ttk.Label(card, textvariable=self.source_preview_status, style="Muted.TLabel").pack(anchor="w")

        ttk.Separator(card).pack(fill="x", pady=8)

        ttk.Label(card, text="Latest styled frame", style="Panel.TLabel").pack(anchor="w")
        self.output_preview = tk.Label(card, bg="#0b0c10", fg=MUTED, text="No styled preview", relief="flat", height=14)
        self.output_preview.pack(fill="both", expand=True, pady=(3, 3))
        ttk.Label(card, textvariable=self.output_preview_status, style="Muted.TLabel").pack(anchor="w")

    def _build_log_card(self, parent):
        card = self._panel(parent, "Activity")
        card.pack(fill="both", expand=False, padx=(10, 0))
        self.log = self._make_text(card, 11)
        self.log.configure(state="disabled")
        self.log.pack(fill="both", expand=True)

    def _sync_webui_background(self):
        self._run_worker(self._sync_webui)

    @staticmethod
    def _names_from_list(data, keys=("name", "title", "label")):
        out = []
        if isinstance(data, list):
            for item in data:
                if isinstance(item, str):
                    out.append(item)
                elif isinstance(item, dict):
                    for key in keys:
                        value = item.get(key)
                        if isinstance(value, str) and value:
                            out.append(value)
                            break
        return out

    def _sync_webui(self):
        url = self.api_url()
        try:
            openapi = requests.get(f"{url}/openapi.json", timeout=15)
            if openapi.ok:
                paths = (openapi.json() or {}).get("paths") or {}
                self._api_routes = set(paths.keys())
            else:
                self._api_routes = set()

            options_r = requests.get(f"{url}/sdapi/v1/options", timeout=15)
            options_r.raise_for_status()
            options = options_r.json()

            models_r = requests.get(f"{url}/sdapi/v1/sd-models", timeout=30)
            models_r.raise_for_status()
            model_names = self._names_from_list(models_r.json(), ("title", "model_name", "name"))

            samplers_r = requests.get(f"{url}/sdapi/v1/samplers", timeout=15)
            samplers_r.raise_for_status()
            sampler_names = self._names_from_list(samplers_r.json(), ("name", "label"))

            schedulers = []
            try:
                sched_r = requests.get(f"{url}/sdapi/v1/schedulers", timeout=15)
                if sched_r.ok:
                    schedulers = self._names_from_list(sched_r.json(), ("name", "label"))
            except Exception:
                pass

            current = str(options.get("sd_model_checkpoint") or "")
            current_sampler = str(options.get("sampler_name") or "")

            def apply():
                self.checkpoint_combo["values"] = model_names
                if current and current in model_names:
                    self.checkpoint_var.set(current)
                elif model_names and not self.checkpoint_var.get():
                    match = next((m for m in model_names if current and current.split(" [")[0] in m), None)
                    self.checkpoint_var.set(match or model_names[0])

                self.sampler_combo["values"] = sampler_names
                if current_sampler in sampler_names:
                    self.sampler_var.set(current_sampler)
                elif self.sampler_var.get() not in sampler_names and sampler_names:
                    preferred = next((s for s in sampler_names if s.lower() == "dpm++ 2m"), sampler_names[0])
                    self.sampler_var.set(preferred)

                self.scheduler_combo["values"] = schedulers
                if schedulers and self.scheduler_var.get() not in schedulers:
                    auto = next((s for s in schedulers if s.lower() == "automatic"), schedulers[0])
                    self.scheduler_var.set(auto)

                self.loaded_checkpoint_var.set(current or "Unknown")
                self.webui_status_var.set(f"WebUI ready · {len(model_names)} models · {len(sampler_names)} samplers")
                self.webui_status_label.configure(style="Good.TLabel")

            self.after(0, apply)
            self._log(f"WebUI ready: {len(model_names)} checkpoints, {len(sampler_names)} samplers.")
            if schedulers:
                self._log(f"Schedulers: {len(schedulers)}")
            self._detect_controlnet()
        except Exception as exc:
            self._log(f"WEBUI ERROR: {exc}")
            def fail():
                self.webui_status_var.set("WebUI connection failed")
                self.webui_status_label.configure(style="Bad.TLabel")
            self.after(0, fail)

    def _load_checkpoint_clicked(self):
        self._run_worker(self._ensure_checkpoint_loaded)

    def _ensure_checkpoint_loaded(self):
        target = self.checkpoint_var.get().strip()
        if not target:
            return
        url = self.api_url()
        options = requests.get(f"{url}/sdapi/v1/options", timeout=15)
        options.raise_for_status()
        current = str(options.json().get("sd_model_checkpoint") or "")
        if current == target or (current and current.split(" [")[0] == target.split(" [")[0]):
            self._log(f"Checkpoint already active: {target}")
            return
        self._log(f"Loading checkpoint: {target}")
        self._set_progress(self.progress.get(), f"Loading checkpoint: {target}")
        r = requests.post(f"{url}/sdapi/v1/options", json={"sd_model_checkpoint": target}, timeout=600)
        r.raise_for_status()
        self._log(f"Checkpoint loaded: {target}")
        self.loaded_checkpoint_var.set(target)

    def _detect_controlnet_background(self):
        self._run_worker(self._detect_controlnet)

    def _detect_controlnet(self):
        url = self.api_url()
        routes = self._api_routes
        if not routes:
            try:
                r = requests.get(f"{url}/openapi.json", timeout=15)
                if r.ok:
                    routes = set(((r.json() or {}).get("paths") or {}).keys())
                    self._api_routes = routes
            except Exception:
                routes = set()

        control_routes = [r for r in routes if "controlnet" in r.lower() or r.lower().startswith("/control")]
        if not control_routes:
            self._controlnet_available = False
            self.control_enabled_var.set(False)
            self.cn_status_var.set("Not exposed by this WebUI — safely ignored")
            self.cn_status_label.configure(style="Muted.TLabel")
            self._log("ControlNet not exposed by this WebUI. That's okay; ComicFrame will use normal img2img.")
            return

        models = []
        modules = []
        for route in control_routes:
            if "{" in route:
                continue
            low = route.lower()
            try:
                if "model" in low:
                    r = requests.get(f"{url}{route}", timeout=15)
                    if r.ok:
                        data = r.json()
                        vals = data.get("model_list") or data.get("models") or [] if isinstance(data, dict) else data
                        models.extend(self._names_from_list(vals))
                if any(x in low for x in ("module", "preprocessor", "processor")):
                    r = requests.get(f"{url}{route}", timeout=15)
                    if r.ok:
                        data = r.json()
                        vals = (data.get("module_list") or data.get("modules") or data.get("preprocessors") or []) if isinstance(data, dict) else data
                        modules.extend(self._names_from_list(vals))
            except Exception:
                pass

        models = list(dict.fromkeys(models))
        modules = list(dict.fromkeys(modules))
        self._controlnet_available = bool(models)

        def apply():
            if models:
                self.control_model_combo["values"] = models
                if not self.control_model_var.get():
                    self.control_model_var.set(next((m for m in models if "canny" in m.lower()), models[0]))
                if modules:
                    self.control_module_combo["values"] = modules
                    if self.control_module_var.get() not in modules:
                        self.control_module_var.set(next((m for m in modules if "canny" in m.lower()), modules[0]))
                self.cn_status_var.set(f"Available · {len(models)} model(s)")
                self.cn_status_label.configure(style="Good.TLabel")
            else:
                self.control_enabled_var.set(False)
                self.cn_status_var.set("Extension route found, but no models exposed")
                self.cn_status_label.configure(style="Warn.TLabel")
        self.after(0, apply)

    def _build_payload(self, frame_path, settings, width, height, frame_number):
        payload = super()._build_payload(frame_path, settings, width, height, frame_number)
        if self.scheduler_var.get().strip():
            payload["scheduler"] = self.scheduler_var.get().strip()
        scripts = payload.get("alwayson_scripts")
        if isinstance(scripts, dict) and "ControlNet" in scripts and "controlnet" not in scripts:
            scripts["controlnet"] = scripts.pop("ControlNet")
        return payload

    def _render_range(self, start, count, test_only):
        self._ensure_checkpoint_loaded()
        if self.control_enabled_var.get() and not self._controlnet_available:
            self._log("ControlNet requested but unavailable; disabling it for this render.")
            self.control_enabled_var.set(False)
        return super()._render_range(start, count, test_only)

    def _test_range_clicked(self):
        def job():
            try:
                self._render_range(int(self.test_start_var.get()), int(self.test_count_var.get()), True)
                self.after(0, self._refresh_previews)
            except Exception as exc:
                self._log(f"ERROR: {exc}")
                self._set_progress(0, "Test render failed")
        self._run_worker(job)

    def _full_render_clicked(self):
        if not self.video_var.get().strip():
            messagebox.showwarning("ComicFrame Studio", "Choose a source video first.")
            return
        if not messagebox.askyesno("ComicFrame Studio", "Start/resume the full render?\n\nCompleted styled frames will be skipped."):
            return

        def job():
            try:
                self._render_range(1, None, False)
                self.after(0, self._refresh_previews)
            except Exception as exc:
                self._log(f"ERROR: {exc}")
                self._set_progress(0, "Full render failed")
        self._run_worker(job)

    def _apply_preset(self):
        p = PRESETS[self.preset_var.get()]
        self.denoise_var.set(p["denoise"])
        self.steps_var.set(p["steps"])
        self.cfg_var.set(p["cfg"])
        self.prompt_text.delete("1.0", "end")
        self.prompt_text.insert("1.0", p["prompt"])

    def _browse_video(self):
        super()._browse_video()
        if self.video_var.get():
            self._run_worker(self._make_source_preview)

    def _refresh_previews(self):
        self._run_worker(self._refresh_previews_worker)

    def _refresh_previews_worker(self):
        self._make_source_preview()
        p = self.project_paths()
        candidates = sorted(p["test"].glob("frame_*.png"))
        if not candidates:
            candidates = sorted(p["styled"].glob("frame_*.png"))
        if candidates:
            latest = candidates[-1]
            self.after(0, lambda x=latest: self._show_image(x, self.output_preview, "output"))
            self.output_preview_status.set(latest.name)
        else:
            self.output_preview_status.set("No styled frame yet")

    def _make_source_preview(self):
        video = Path(self.video_var.get().strip()).expanduser()
        if not video.exists():
            return
        p = self.project_paths()
        p["root"].mkdir(parents=True, exist_ok=True)
        preview = p["root"] / "_source_preview.jpg"
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-ss", "0", "-i", str(video),
                 "-frames:v", "1", "-q:v", "2", str(preview)],
                check=True,
            )
            self.after(0, lambda: self._show_image(preview, self.source_preview, "source"))
            self.source_preview_status.set(video.name)
        except Exception as exc:
            self._log(f"Preview error: {exc}")

    def _show_image(self, path, label, key):
        try:
            im = Image.open(path).convert("RGB")
            im.thumbnail((620, 340), Image.LANCZOS)
            photo = ImageTk.PhotoImage(im)
            label.configure(image=photo, text="")
            self._preview_refs[key] = photo
        except Exception as exc:
            label.configure(text=f"Preview failed: {exc}", image="")

    def _open_project(self):
        root = self.project_paths()["root"]
        root.mkdir(parents=True, exist_ok=True)
        try:
            if os.name == "nt":
                os.startfile(root)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(root)])
        except Exception as exc:
            messagebox.showerror("ComicFrame Studio", f"Could not open project folder:\n{exc}")


def main():
    ComicFrameStudioV13().mainloop()


if __name__ == "__main__":
    main()
