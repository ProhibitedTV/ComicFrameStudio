#!/usr/bin/env python3
"""ComicFrame Studio v1 - frame-accurate Stable Diffusion video stylizer."""
from __future__ import annotations

import base64
import json
import queue
import re
import shutil
import subprocess
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

import requests
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_NAME = "ComicFrame Studio"
APP_VERSION = "1.0"

DEFAULT_PROMPT = (
    "graphic comic-book animation frame, bold hand-inked contours, clean readable silhouette, "
    "halftone dot shading, crosshatching, posterized cel shadows, screen-print texture, "
    "subtle CMYK print misregistration, high contrast cinematic lighting, vivid orange and "
    "electric blue split lighting, magenta and cyan accents, expressive linework, crisp "
    "illustrated details, dramatic graphic composition, preserve the exact person, pose, "
    "clothing, room layout, camera framing, furniture placement, and full-body proportions "
    "from the source frame"
)

DEFAULT_NEGATIVE = (
    "photorealistic, soft painterly rendering, watercolor, blurry, low contrast, extra arms, "
    "extra legs, extra fingers, missing fingers, duplicated person, warped face, malformed face, "
    "altered identity, changed hairstyle, changed clothes, cropped body, zoomed-in composition, "
    "different camera angle, changed furniture, duplicated furniture, missing furniture, "
    "text artifacts, random lettering, logo artifacts, fisheye distortion, melted objects, "
    "deformed anatomy"
)


@dataclass
class RenderSettings:
    api_url: str = "http://127.0.0.1:7860"
    prompt: str = DEFAULT_PROMPT
    negative_prompt: str = DEFAULT_NEGATIVE
    steps: int = 24
    cfg_scale: float = 6.0
    denoise: float = 0.30
    sampler: str = "DPM++ 2M Karras"
    seed: int = 123456
    seed_mode: str = "fixed"
    controlnet_enabled: bool = True
    controlnet_module: str = "canny"
    controlnet_model: str = ""
    controlnet_weight: float = 0.90
    canny_low: int = 100
    canny_high: int = 200
    processor_res: int = 1024


class ComicFrameStudio(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("1100x900")
        self.minsize(980, 760)

        self.stop_event = threading.Event()
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.progress_queue: queue.Queue[tuple[float, str]] = queue.Queue()
        self.worker: Optional[threading.Thread] = None

        self.video_var = tk.StringVar()
        self.work_var = tk.StringVar(value=str(Path.cwd() / "comicframe_project"))
        self.api_var = tk.StringVar(value="http://127.0.0.1:7860")
        self.steps_var = tk.IntVar(value=24)
        self.cfg_var = tk.DoubleVar(value=6.0)
        self.denoise_var = tk.DoubleVar(value=0.30)
        self.seed_var = tk.IntVar(value=123456)
        self.seed_mode_var = tk.StringVar(value="fixed")
        self.sampler_var = tk.StringVar(value="DPM++ 2M Karras")
        self.control_enabled_var = tk.BooleanVar(value=True)
        self.control_module_var = tk.StringVar(value="canny")
        self.control_model_var = tk.StringVar(value="")
        self.control_weight_var = tk.DoubleVar(value=0.90)
        self.canny_low_var = tk.IntVar(value=100)
        self.canny_high_var = tk.IntVar(value=200)
        self.test_start_var = tk.IntVar(value=1)
        self.test_count_var = tk.IntVar(value=20)
        self.progress = tk.DoubleVar(value=0)
        self.progress_label_var = tk.StringVar(value="Idle")

        self._build_ui()
        self.after(100, self._poll_queues)

    def _build_ui(self):
        root = ttk.Frame(self, padding=10)
        root.pack(fill="both", expand=True)
        ttk.Label(root, text=APP_NAME, font=("TkDefaultFont", 18, "bold")).pack(anchor="w")
        ttk.Label(root, text="Extract → Stable Diffusion img2img/ControlNet → reassemble → restore audio").pack(anchor="w", pady=(0, 10))

        src = ttk.LabelFrame(root, text="1. Source / Project", padding=8)
        src.pack(fill="x", pady=5)
        row = ttk.Frame(src); row.pack(fill="x", pady=2)
        ttk.Label(row, text="Video:", width=12).pack(side="left")
        ttk.Entry(row, textvariable=self.video_var).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(row, text="Browse…", command=self._browse_video).pack(side="left")
        row = ttk.Frame(src); row.pack(fill="x", pady=2)
        ttk.Label(row, text="Project dir:", width=12).pack(side="left")
        ttk.Entry(row, textvariable=self.work_var).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(row, text="Browse…", command=self._browse_work).pack(side="left")

        api = ttk.LabelFrame(root, text="2. Stable Diffusion API", padding=8)
        api.pack(fill="x", pady=5)
        row = ttk.Frame(api); row.pack(fill="x")
        ttk.Label(row, text="API URL:", width=12).pack(side="left")
        ttk.Entry(row, textvariable=self.api_var, width=40).pack(side="left", padx=4)
        ttk.Button(row, text="Test API", command=self._test_api_clicked).pack(side="left", padx=4)
        ttk.Button(row, text="Refresh ControlNet", command=self._refresh_controlnet_clicked).pack(side="left", padx=4)

        prompts = ttk.LabelFrame(root, text="3. Comic Style", padding=8)
        prompts.pack(fill="both", pady=5)
        ttk.Label(prompts, text="Positive prompt").pack(anchor="w")
        self.prompt_text = tk.Text(prompts, height=5, wrap="word")
        self.prompt_text.pack(fill="x", pady=(0, 5)); self.prompt_text.insert("1.0", DEFAULT_PROMPT)
        ttk.Label(prompts, text="Negative prompt").pack(anchor="w")
        self.negative_text = tk.Text(prompts, height=4, wrap="word")
        self.negative_text.pack(fill="x"); self.negative_text.insert("1.0", DEFAULT_NEGATIVE)

        settings = ttk.LabelFrame(root, text="4. Render Settings", padding=8)
        settings.pack(fill="x", pady=5)
        g = ttk.Frame(settings); g.pack(fill="x")
        self._spin(g, "Steps", self.steps_var, 1, 100, 0, 0)
        self._spin(g, "CFG", self.cfg_var, 1, 30, 0, 1, 0.5)
        self._spin(g, "Denoise", self.denoise_var, 0.05, 0.95, 0, 2, 0.01)
        self._spin(g, "Seed", self.seed_var, -1, 2147483647, 0, 3)
        ttk.Label(g, text="Seed mode").grid(row=2, column=0, sticky="w", padx=4)
        ttk.Combobox(g, textvariable=self.seed_mode_var, values=["fixed", "increment"], state="readonly").grid(row=3, column=0, sticky="ew", padx=4)
        ttk.Label(g, text="Sampler").grid(row=2, column=1, sticky="w", padx=4)
        ttk.Combobox(g, textvariable=self.sampler_var, values=["DPM++ 2M Karras", "DPM++ SDE Karras", "Euler a", "Euler", "DDIM"]).grid(row=3, column=1, columnspan=2, sticky="ew", padx=4)
        for i in range(4): g.columnconfigure(i, weight=1)

        cn = ttk.LabelFrame(root, text="5. ControlNet — strongly recommended for continuity", padding=8)
        cn.pack(fill="x", pady=5)
        ttk.Checkbutton(cn, text="Enable ControlNet", variable=self.control_enabled_var).grid(row=0, column=0, sticky="w", padx=4)
        ttk.Label(cn, text="Module").grid(row=1, column=0, sticky="w", padx=4)
        self.control_module_combo = ttk.Combobox(cn, textvariable=self.control_module_var, values=["canny", "lineart_realistic", "lineart"])
        self.control_module_combo.grid(row=2, column=0, sticky="ew", padx=4)
        ttk.Label(cn, text="Model").grid(row=1, column=1, sticky="w", padx=4)
        self.control_model_combo = ttk.Combobox(cn, textvariable=self.control_model_var, values=[])
        self.control_model_combo.grid(row=2, column=1, sticky="ew", padx=4)
        self._spin(cn, "Weight", self.control_weight_var, 0, 2, 1, 2, 0.05)
        self._spin(cn, "Canny low", self.canny_low_var, 0, 255, 1, 3)
        self._spin(cn, "Canny high", self.canny_high_var, 0, 255, 1, 4)
        cn.columnconfigure(0, weight=1); cn.columnconfigure(1, weight=2)
        for i in (2, 3, 4): cn.columnconfigure(i, weight=1)

        run = ttk.LabelFrame(root, text="6. Run", padding=8)
        run.pack(fill="x", pady=5)
        row = ttk.Frame(run); row.pack(fill="x")
        ttk.Button(row, text="Extract Frames Only", command=self._extract_clicked).pack(side="left", padx=3)
        ttk.Label(row, text="Test start frame").pack(side="left", padx=(15, 3))
        ttk.Spinbox(row, textvariable=self.test_start_var, from_=1, to=999999, width=8).pack(side="left")
        ttk.Label(row, text="count").pack(side="left", padx=(8, 3))
        ttk.Spinbox(row, textvariable=self.test_count_var, from_=1, to=500, width=8).pack(side="left")
        ttk.Button(row, text="Render Test Range", command=self._test_range_clicked).pack(side="left", padx=6)
        ttk.Button(row, text="FULL RENDER", command=self._full_render_clicked).pack(side="left", padx=6)
        ttk.Button(row, text="STOP", command=self._stop_clicked).pack(side="right", padx=3)

        ttk.Progressbar(root, variable=self.progress, maximum=100).pack(fill="x", pady=(8, 2))
        ttk.Label(root, textvariable=self.progress_label_var).pack(anchor="w")
        logf = ttk.LabelFrame(root, text="Log", padding=6); logf.pack(fill="both", expand=True, pady=5)
        self.log = tk.Text(logf, height=10, wrap="word", state="disabled"); self.log.pack(fill="both", expand=True)
        ttk.Label(root, text="Tip: if style is too weak, raise denoise. If identity/layout drifts, lower denoise or raise ControlNet weight.").pack(anchor="w")

    def _spin(self, parent, label, var, low, high, row, col, increment=1):
        ttk.Label(parent, text=label).grid(row=row, column=col, sticky="w", padx=4)
        ttk.Spinbox(parent, textvariable=var, from_=low, to=high, increment=increment, width=16).grid(row=row + 1, column=col, sticky="ew", padx=4)

    def _browse_video(self):
        path = filedialog.askopenfilename(title="Choose source video", filetypes=[("Video files", "*.mp4 *.mov *.mkv *.avi *.webm *.m4v"), ("All files", "*.*")])
        if path:
            self.video_var.set(path)
            p = Path(path)
            if not self.work_var.get().strip() or self.work_var.get().endswith("comicframe_project"):
                self.work_var.set(str(p.parent / f"{p.stem}_comicframe"))

    def _browse_work(self):
        path = filedialog.askdirectory(title="Choose project directory")
        if path: self.work_var.set(path)

    def _log(self, msg): self.log_queue.put(str(msg))
    def _set_progress(self, pct, label): self.progress_queue.put((pct, label))

    def _poll_queues(self):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self.log.configure(state="normal"); self.log.insert("end", msg.rstrip() + "\n"); self.log.see("end"); self.log.configure(state="disabled")
        except queue.Empty:
            pass
        try:
            while True:
                pct, label = self.progress_queue.get_nowait(); self.progress.set(pct); self.progress_label_var.set(label)
        except queue.Empty:
            pass
        self.after(100, self._poll_queues)

    def _run_worker(self, target):
        if self.worker and self.worker.is_alive():
            messagebox.showwarning(APP_NAME, "A job is already running."); return
        self.stop_event.clear(); self.worker = threading.Thread(target=target, daemon=True); self.worker.start()

    def _check_external(self):
        missing = [x for x in ("ffmpeg", "ffprobe") if shutil.which(x) is None]
        if missing: raise RuntimeError(f"Missing from PATH: {', '.join(missing)}")

    def _run(self, args, capture=False):
        self._log("$ " + " ".join(str(x) for x in args))
        cp = subprocess.run(args, check=True, text=True, capture_output=capture)
        return cp.stdout.strip() if capture else ""

    def api_url(self): return self.api_var.get().strip().rstrip("/")

    def _test_api_clicked(self): self._run_worker(self._test_api)

    def _test_api(self):
        try:
            r = requests.get(f"{self.api_url()}/sdapi/v1/options", timeout=10); r.raise_for_status()
            self._log(f"API OK: {self.api_url()}"); self._set_progress(0, "API connected")
        except Exception as e:
            self._log(f"API ERROR: {e}"); self._set_progress(0, "API connection failed")

    def _refresh_controlnet_clicked(self): self._run_worker(self._refresh_controlnet)

    def _refresh_controlnet(self):
        url = self.api_url(); models, modules = [], []
        for ep in (f"{url}/controlnet/model_list", f"{url}/controlnet/model_list?update=true"):
            try:
                r = requests.get(ep, timeout=15)
                if r.ok:
                    d = r.json(); models = d.get("model_list", d.get("models", []))
                    if models: break
            except Exception: pass
        for ep in (f"{url}/controlnet/module_list", f"{url}/controlnet/module_list?alias_names=false"):
            try:
                r = requests.get(ep, timeout=15)
                if r.ok:
                    d = r.json(); modules = d.get("module_list", d.get("modules", []))
                    if modules: break
            except Exception: pass
        if models:
            def apply_models():
                self.control_model_combo["values"] = models
                if not self.control_model_var.get(): self.control_model_var.set(next((m for m in models if "canny" in m.lower()), models[0]))
            self.after(0, apply_models); self._log(f"Found {len(models)} ControlNet model(s).")
        else:
            self._log("Could not query ControlNet model list; type a model name manually if needed.")
        if modules:
            def apply_modules():
                self.control_module_combo["values"] = modules
                if self.control_module_var.get() not in modules: self.control_module_var.set(next((m for m in modules if "canny" in m.lower()), modules[0]))
            self.after(0, apply_modules); self._log(f"Found {len(modules)} ControlNet module(s).")

    def project_paths(self):
        root = Path(self.work_var.get().strip()).expanduser().resolve()
        return {"root": root, "frames": root / "frames", "styled": root / "styled_frames", "test": root / "test_frames", "meta": root / "source_info.json", "silent": root / "styled_silent.mp4", "final": root / "FINAL_STYLED.mp4", "settings": root / "render_settings.json"}

    def _probe_video(self, video):
        self._check_external()
        raw = self._run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate,avg_frame_rate,nb_frames:format=duration", "-of", "json", str(video)], capture=True)
        data = json.loads(raw); s = data["streams"][0]
        fps_expr = s.get("avg_frame_rate") or s.get("r_frame_rate") or "30/1"
        a, b = fps_expr.split("/") if "/" in fps_expr else (fps_expr, "1")
        fps = float(a) / float(b or 1)
        return {"width": int(s["width"]), "height": int(s["height"]), "fps": fps, "fps_expr": fps_expr, "duration": float(data.get("format", {}).get("duration") or 0), "nb_frames": s.get("nb_frames")}

    def _extract_frames(self):
        video = Path(self.video_var.get().strip()).expanduser().resolve()
        if not video.exists(): raise FileNotFoundError("Choose a valid source video first.")
        p = self.project_paths()
        for key in ("root", "frames", "styled", "test"): p[key].mkdir(parents=True, exist_ok=True)
        info = self._probe_video(video); p["meta"].write_text(json.dumps(info, indent=2), encoding="utf-8")
        self._log(f"Source: {info['width']}x{info['height']} @ {info['fps']:.6f} fps, {info['duration']:.2f}s")
        existing = sorted(p["frames"].glob("frame_*.png"))
        if existing:
            self._log(f"Frames already exist ({len(existing)}). Extraction skipped."); return info
        self._set_progress(1, "Extracting source frames…")
        self._run(["ffmpeg", "-y", "-i", str(video), "-map", "0:v:0", "-vsync", "0", str(p["frames"] / "frame_%06d.png")])
        count = len(list(p["frames"].glob("frame_*.png"))); self._log(f"Extracted {count} frame(s)."); self._set_progress(5, f"Extracted {count} frames")
        return info

    def _settings(self):
        return RenderSettings(api_url=self.api_url(), prompt=self.prompt_text.get("1.0", "end").strip(), negative_prompt=self.negative_text.get("1.0", "end").strip(), steps=int(self.steps_var.get()), cfg_scale=float(self.cfg_var.get()), denoise=float(self.denoise_var.get()), sampler=self.sampler_var.get().strip(), seed=int(self.seed_var.get()), seed_mode=self.seed_mode_var.get(), controlnet_enabled=bool(self.control_enabled_var.get()), controlnet_module=self.control_module_var.get().strip(), controlnet_model=self.control_model_var.get().strip(), controlnet_weight=float(self.control_weight_var.get()), canny_low=int(self.canny_low_var.get()), canny_high=int(self.canny_high_var.get()))

    @staticmethod
    def _encode_file(path): return base64.b64encode(path.read_bytes()).decode("ascii")

    @staticmethod
    def _save_api_image(data, out_path):
        if "," in data and data.lstrip().startswith("data:image"): data = data.split(",", 1)[1]
        out_path.write_bytes(base64.b64decode(data))

    def _frame_seed(self, settings, frame_number):
        if settings.seed < 0: return -1
        return settings.seed + frame_number - 1 if settings.seed_mode == "increment" else settings.seed

    def _build_payload(self, frame_path, settings, width, height, frame_number):
        b64 = self._encode_file(frame_path)
        payload = {"init_images": [b64], "prompt": settings.prompt, "negative_prompt": settings.negative_prompt, "steps": settings.steps, "cfg_scale": settings.cfg_scale, "sampler_name": settings.sampler, "denoising_strength": settings.denoise, "seed": self._frame_seed(settings, frame_number), "width": width, "height": height, "resize_mode": 0, "batch_size": 1, "n_iter": 1, "restore_faces": False, "tiling": False}
        if settings.controlnet_enabled and settings.controlnet_model and settings.controlnet_model.lower() not in ("none", "none [none]"):
            payload["alwayson_scripts"] = {"ControlNet": {"args": [{"enabled": True, "module": settings.controlnet_module or "canny", "model": settings.controlnet_model, "weight": settings.controlnet_weight, "image": b64, "resize_mode": "Just Resize", "low_vram": False, "processor_res": settings.processor_res, "threshold_a": settings.canny_low, "threshold_b": settings.canny_high, "guidance_start": 0.0, "guidance_end": 1.0, "control_mode": 0, "pixel_perfect": True}]}}
        return payload

    def _render_one(self, frame_path, out_path, settings, width, height, frame_number):
        r = requests.post(f"{settings.api_url.rstrip('/')}/sdapi/v1/img2img", json=self._build_payload(frame_path, settings, width, height, frame_number), timeout=3600)
        if not r.ok: raise RuntimeError(f"Stable Diffusion API HTTP {r.status_code}: {r.text[:1000]}")
        images = r.json().get("images") or []
        if not images: raise RuntimeError(f"No image returned for {frame_path.name}")
        self._save_api_image(images[0], out_path)

    def _render_range(self, start, count, test_only):
        info = self._extract_frames(); p = self.project_paths(); settings = self._settings()
        p["settings"].write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
        frames = sorted(p["frames"].glob("frame_*.png"))
        if not frames: raise RuntimeError("No frames found.")
        start_idx = max(0, start - 1); chosen = frames[start_idx:] if count is None else frames[start_idx:start_idx + count]
        outdir = p["test"] if test_only else p["styled"]; outdir.mkdir(parents=True, exist_ok=True)
        self._log(f"Rendering {len(chosen)} frame(s) from #{start}. Full source dimensions preserved: {info['width']}x{info['height']}.")
        self._log(f"Settings: denoise={settings.denoise}, CFG={settings.cfg_scale}, steps={settings.steps}, seed={settings.seed} ({settings.seed_mode}), ControlNet={'ON' if settings.controlnet_enabled else 'OFF'}")
        if settings.controlnet_enabled and not settings.controlnet_model:
            self._log("WARNING: ControlNet is enabled but no model is selected. Rendering will continue without a ControlNet unit.")
        total = len(chosen)
        for idx, frame in enumerate(chosen, 1):
            if self.stop_event.is_set(): self._log("STOP requested. Render halted safely."); break
            out_path = outdir / frame.name; frame_num = int(re.search(r"(\d+)", frame.stem).group(1))
            if out_path.exists() and out_path.stat().st_size > 10000:
                self._log(f"[{idx}/{total}] SKIP existing {frame.name}")
            else:
                self._log(f"[{idx}/{total}] Render {frame.name}"); self._render_one(frame, out_path, settings, info["width"], info["height"], frame_num)
            self._set_progress((10 if test_only else 5) + (idx / max(total, 1)) * (80 if test_only else 85), f"{idx}/{total}: {frame.name}")
        if test_only:
            self._set_progress(100, f"Test complete: {outdir}"); self._log(f"TEST COMPLETE: {outdir}")
        elif not self.stop_event.is_set():
            self._assemble(info)
        else:
            self._log("Partial styled frames are preserved. Re-run FULL RENDER to resume.")

    def _assemble(self, info):
        p = self.project_paths(); video = Path(self.video_var.get().strip()).expanduser().resolve()
        frames = sorted(p["frames"].glob("frame_*.png")); styled = sorted(p["styled"].glob("frame_*.png"))
        if len(styled) < len(frames): raise RuntimeError(f"Cannot assemble full video: {len(styled)}/{len(frames)} styled frames exist.")
        self._set_progress(92, "Encoding styled video…")
        self._run(["ffmpeg", "-y", "-framerate", info.get("fps_expr") or str(info["fps"]), "-i", str(p["styled"] / "frame_%06d.png"), "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(p["silent"])])
        self._set_progress(97, "Restoring original audio…")
        self._run(["ffmpeg", "-y", "-i", str(p["silent"]), "-i", str(video), "-map", "0:v:0", "-map", "1:a:0?", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(p["final"])])
        self._set_progress(100, f"DONE: {p['final']}"); self._log(f"FINAL VIDEO: {p['final']}")

    def _extract_clicked(self):
        def job():
            try: self._extract_frames(); self._set_progress(100, "Frame extraction complete")
            except Exception as e: self._log(f"ERROR: {e}"); self._set_progress(0, "Extraction failed")
        self._run_worker(job)

    def _test_range_clicked(self):
        def job():
            try: self._render_range(int(self.test_start_var.get()), int(self.test_count_var.get()), True)
            except Exception as e: self._log(f"ERROR: {e}"); self._set_progress(0, "Test render failed")
        self._run_worker(job)

    def _full_render_clicked(self):
        if not self.video_var.get().strip(): messagebox.showwarning(APP_NAME, "Choose a source video first."); return
        if not messagebox.askyesno(APP_NAME, "Start/resume the FULL video render?\n\nExisting styled frames will be skipped."): return
        def job():
            try: self._render_range(1, None, False)
            except Exception as e: self._log(f"ERROR: {e}"); self._set_progress(0, "Full render failed")
        self._run_worker(job)

    def _stop_clicked(self):
        self.stop_event.set(); self._log("STOP requested. The current Stable Diffusion frame will finish, then rendering stops.")


def main():
    ComicFrameStudio().mainloop()


if __name__ == "__main__":
    main()
