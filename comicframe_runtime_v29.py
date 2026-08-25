#!/usr/bin/env python3
"""Second-audit canonical runtime for ComicFrame Studio v2.9.

v2.9 intentionally subclasses the exact v2.8 hardening runtime.  The point of
this layer is to finish media/resume correctness without adding another feature
mixin to the cooperative renderer MRO.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

import requests
from PIL import Image

from comicframe_hardening import analysis_signature, legacy_source_compatible, load_json, runtime_source_key, sampled_file_sha256
from comicframe_manifest_safety import prune_shot_memory_ranges_safe
from comicframe_media import (
    FULL_FINGERPRINT_ALGO,
    MEDIA_VERSION,
    atomic_bytes_write,
    atomic_json_write,
    choose_fps_expression,
    display_dimensions_from_frame,
    ensure_project_owned,
    frame_numbers,
    frame_sequence_report,
    frame_timing_from_probe,
    full_file_sha256,
    image_similarity,
    invalid_png_numbers,
    representative_numbers,
    safe_clear_generated_directory,
    safe_reset_generated_state,
    validate_png,
    write_ffconcat,
)
from comicframe_runtime_v28 import ComicFrameStudioApp as V28ComicFrameStudioApp
from comicframe_workspace import sequence_frame_numbers


RUNTIME_VERSION = "2.9"


class ComicFrameStudioApp(V28ComicFrameStudioApp):
    """v2.8 + exact media timing, safer resume, telemetry and audit fixes."""

    def __init__(self):
        self._audit2_timing: dict[str, Any] | None = None
        self._audit2_render_scope: dict[str, Any] | None = None
        self._audit2_closing = False
        super().__init__()
        self.title("ComicFrame Studio 2.9 · Media Integrity")
        try:
            self.protocol("WM_DELETE_WINDOW", self._audit2_close_requested)
        except Exception:
            pass

    # ---------- Paths / media probing ----------

    def project_paths(self):
        paths = super().project_paths()
        root = paths["root"]
        paths.update({
            "timing_dir": root / "cache" / "timing",
            "source_timing": root / "cache" / "timing" / "source_timing.json",
            "styled_concat": root / "cache" / "timing" / "styled.ffconcat",
        })
        return paths

    def _probe_video(self, video):
        self._check_external()
        raw = self._run([
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries",
            "stream=width,height,r_frame_rate,avg_frame_rate,nb_frames:stream_tags=rotate:stream_side_data=rotation:format=duration",
            "-of", "json", str(video),
        ], capture=True)
        data = json.loads(raw or "{}")
        streams = list(data.get("streams") or [])
        if not streams:
            raise RuntimeError("ffprobe found no video stream in the selected source.")
        stream = streams[0]
        coded_width = int(stream.get("width") or 0)
        coded_height = int(stream.get("height") or 0)
        if coded_width <= 0 or coded_height <= 0:
            raise RuntimeError("ffprobe returned invalid video dimensions.")
        fps_expr, fps = choose_fps_expression(stream.get("avg_frame_rate"), stream.get("r_frame_rate"))
        try:
            duration = max(0.0, float((data.get("format") or {}).get("duration") or 0.0))
        except Exception:
            duration = 0.0
        rotation = 0
        try:
            rotation = int(round(float((stream.get("tags") or {}).get("rotate") or 0)))
        except Exception:
            rotation = 0
        for side in stream.get("side_data_list") or []:
            if isinstance(side, dict) and side.get("rotation") is not None:
                try:
                    rotation = int(round(float(side.get("rotation") or 0)))
                except Exception:
                    pass
        return {
            "width": coded_width,
            "height": coded_height,
            "coded_width": coded_width,
            "coded_height": coded_height,
            "rotation": rotation,
            "fps": fps,
            "fps_expr": fps_expr,
            "duration": duration,
            "nb_frames": stream.get("nb_frames"),
        }

    def _audit2_probe_timing(self, video: Path, info: dict[str, Any], frame_count: int, fingerprint: str) -> dict[str, Any]:
        paths = self.project_paths()
        cached = load_json(paths["source_timing"])
        if (
            cached.get("source_fingerprint") == fingerprint
            and int(cached.get("frame_count") or 0) == int(frame_count)
            and isinstance(cached.get("durations"), list)
            and len(cached.get("durations") or []) == int(frame_count)
        ):
            self._audit2_timing = cached
            return cached
        raw = self._run([
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "frame=best_effort_timestamp_time,pkt_duration_time,duration_time",
            "-of", "json", str(video),
        ], capture=True)
        try:
            rows = list((json.loads(raw or "{}") or {}).get("frames") or [])
        except Exception:
            rows = []
        timing = frame_timing_from_probe(rows, int(frame_count), float(info.get("fps") or 30.0))
        timing.update({
            "source_fingerprint": fingerprint,
            "frame_count": int(frame_count),
        })
        atomic_json_write(paths["source_timing"], timing)
        self._audit2_timing = timing
        return timing

    def _audit2_verify_legacy_source(self, video: Path, info: dict[str, Any], old_meta: dict[str, Any], frames_dir: Path) -> bool:
        if not legacy_source_compatible(old_meta, info, frames_dir):
            return False
        old_fp = str(old_meta.get("source_fingerprint") or "")
        if old_fp and old_fp != sampled_file_sha256(video):
            return False
        numbers = frame_numbers(frames_dir)
        samples = representative_numbers(len(numbers), samples=5)
        if not samples:
            return False
        cache_root = self.project_paths()["root"] / "cache"
        cache_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="source_verify_", dir=cache_root) as temp_text:
            temp = Path(temp_text)
            expression = "+".join(f"eq(n\\,{number - 1})" for number in samples)
            try:
                self._run([
                    "ffmpeg", "-y", "-loglevel", "error", "-i", str(video),
                    "-vf", f"select={expression}", "-vsync", "0",
                    str(temp / "probe_%06d.png"),
                ])
            except Exception:
                return False
            probes = sorted(temp.glob("probe_*.png"))
            if len(probes) != len(samples):
                return False
            for number, probe in zip(samples, probes):
                source = frames_dir / f"frame_{number:06d}.png"
                try:
                    if image_similarity(source, probe) < 0.985:
                        return False
                except Exception:
                    return False
        return True

    def _audit2_clear_geometry_dependent_outputs(self, root: Path) -> None:
        for directory in (root / "styled_frames", root / "test_frames", root / "shot_memory", root / "cache"):
            if directory.exists() or directory.is_symlink():
                safe_clear_generated_directory(root, directory)
        for name in ("styled_silent.mp4", "FINAL_STYLED.mp4", "comicframe_timeline.rendered.json", "comicframe_profile.json"):
            path = root / name
            if path.is_file() or path.is_symlink():
                path.unlink(missing_ok=True)

    # ---------- Exact source identity / extraction ----------

    def _extract_frames(self):
        video = Path(self.video_var.get().strip()).expanduser().resolve()
        if not video.exists():
            raise FileNotFoundError("Choose a valid source video first.")
        paths = self.project_paths()
        root = paths["root"]
        ownership = ensure_project_owned(root)
        runtime_key = (str(root.resolve()), *runtime_source_key(video))
        cached = self._hardening_source_info
        if self._hardening_source_key == runtime_key and isinstance(cached, dict):
            expected = int(cached.get("frame_count") or 0) or None
            if frame_sequence_report(paths["frames"], expected)["valid"]:
                return dict(cached)

        self._check_external()
        info = self._probe_video(video)
        full_fingerprint = full_file_sha256(video)
        old_meta = load_json(paths["meta"])
        old_algo = str(old_meta.get("source_fingerprint_algo") or "")
        old_fp = str(old_meta.get("source_fingerprint") or "")

        source_changed = False
        legacy_match = False
        if old_meta:
            if old_algo == FULL_FINGERPRINT_ALGO:
                source_changed = old_fp != full_fingerprint
            else:
                legacy_match = self._audit2_verify_legacy_source(video, info, old_meta, paths["frames"])
                source_changed = not legacy_match

        if source_changed:
            self._log("Source content does not match this project; clearing only ComicFrame-owned derived state.")
            safe_reset_generated_state(root)
            paths = self.project_paths()
            old_meta = {}
            old_fp = ""
            legacy_match = False

        for key in ("root", "frames", "styled", "test"):
            paths[key].mkdir(parents=True, exist_ok=True)

        expected = None
        if old_meta and ((old_algo == FULL_FINGERPRINT_ALGO and old_fp == full_fingerprint) or legacy_match):
            try:
                expected = int(old_meta.get("frame_count") or 0) or None
            except Exception:
                expected = None
        report = frame_sequence_report(paths["frames"], expected)
        if not report["valid"]:
            if frame_numbers(paths["frames"]):
                self._log("Source-frame sequence is incomplete; rebuilding it before any GPU work.")
                safe_clear_generated_directory(root, paths["frames"])
            self._set_progress(1, "Extracting source frames…")
            self._run([
                "ffmpeg", "-y", "-i", str(video), "-map", "0:v:0", "-vsync", "0",
                str(paths["frames"] / "frame_%06d.png"),
            ])
            report = frame_sequence_report(paths["frames"])
            if not report["valid"]:
                raise RuntimeError(
                    "ffmpeg returned but the source PNG sequence is incomplete/non-contiguous: "
                    f"count={report['count']} first={report['first']} last={report['last']}"
                )
        else:
            self._log(f"Source frames verified · {report['count']} contiguous frame(s) reusable.")

        samples = representative_numbers(int(report["count"]), samples=5)
        bad_source = invalid_png_numbers(paths["frames"], samples)
        if bad_source:
            self._log(f"Source PNG validation found corruption ({bad_source[0]}); extracting a clean sequence.")
            safe_clear_generated_directory(root, paths["frames"])
            self._run([
                "ffmpeg", "-y", "-i", str(video), "-map", "0:v:0", "-vsync", "0",
                str(paths["frames"] / "frame_%06d.png"),
            ])
            report = frame_sequence_report(paths["frames"])
            if not report["valid"] or invalid_png_numbers(paths["frames"], representative_numbers(int(report["count"]), 5)):
                raise RuntimeError("Source extraction produced invalid PNG frames after a clean retry.")

        first_frame = paths["frames"] / "frame_000001.png"
        display_width, display_height = display_dimensions_from_frame(first_frame)
        old_display = (int(old_meta.get("width") or 0), int(old_meta.get("height") or 0)) if old_meta else (0, 0)
        coded = (int(info.get("coded_width") or info["width"]), int(info.get("coded_height") or info["height"]))
        info["width"], info["height"] = display_width, display_height
        info["coded_width"], info["coded_height"] = coded
        info["autorotation_applied"] = (display_width, display_height) != coded

        if old_meta and old_display != (0, 0) and old_display != (display_width, display_height):
            self._log(
                f"Display geometry corrected from {old_display[0]}x{old_display[1]} to "
                f"{display_width}x{display_height}; stale styled outputs are being discarded."
            )
            self._audit2_clear_geometry_dependent_outputs(root)
            paths = self.project_paths()
            for key in ("styled", "test"):
                paths[key].mkdir(parents=True, exist_ok=True)

        timing = self._audit2_probe_timing(video, info, int(report["count"]), full_fingerprint)
        metadata = dict(info)
        metadata.update({
            "source_fingerprint": full_fingerprint,
            "source_fingerprint_algo": FULL_FINGERPRINT_ALGO,
            "source_path": str(video),
            "source_bytes": int(video.stat().st_size),
            "source_mtime_ns": int(video.stat().st_mtime_ns),
            "frame_count": int(report["count"]),
            "timing_mode": str(timing.get("mode") or "constant-fallback"),
            "variable_frame_rate": bool(timing.get("variable")),
            "timing_duration": float(timing.get("total_duration") or 0.0),
            "media_integrity_version": MEDIA_VERSION,
            "project_ownership": ownership,
        })
        atomic_json_write(paths["meta"], metadata)
        self._hardening_source_key = runtime_key
        self._hardening_source_info = metadata
        self._audit2_timing = timing
        self._log(
            f"Source ready · {display_width}x{display_height} · {report['count']} frames · "
            f"timing={timing.get('mode')}{' VFR' if timing.get('variable') else ''}."
        )
        self._set_progress(5, f"Source verified · {report['count']} frames")
        return dict(metadata)

    def _source_fingerprint(self) -> str:
        meta = self._hardening_source_info or load_json(self.project_paths()["meta"])
        timeline = getattr(self, "_director_timeline", {}) or {}
        payload = {
            "source": str(meta.get("source_fingerprint") or ""),
            "total_frames": int(timeline.get("total_frames") or 0),
            "shots": [
                [int(shot.get("id", 0)), int(shot.get("start", 0)), int(shot.get("end", 0))]
                for shot in timeline.get("shots", []) if isinstance(shot, dict)
            ],
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

    # ---------- Render-frame validation / telemetry / retry ----------

    @staticmethod
    def _audit2_transient_render_error(exc: Exception) -> bool:
        low = str(exc).lower()
        if any(token in low for token in ("cuda out of memory", "outofmemory", "out of vram", "nansexception", "nan was produced")):
            return False
        return any(token in low for token in (
            "connection reset", "connection aborted", "connection refused", "remote end closed",
            "read timed out", "connect timeout", "temporarily unavailable", "http 429",
            "http 500", "http 502", "http 503", "http 504",
        ))

    @staticmethod
    def _audit2_eta_text(seconds: float) -> str:
        seconds = max(0, int(round(seconds)))
        hours, rem = divmod(seconds, 3600)
        minutes, secs = divmod(rem, 60)
        if hours:
            return f"{hours}h {minutes:02d}m"
        if minutes:
            return f"{minutes}m {secs:02d}s"
        return f"{secs}s"

    def _set_progress(self, pct, label):
        scope = self._audit2_render_scope
        text = str(label)
        if scope and scope.get("ema") and "ETA" not in text:
            match = re.search(r"(\d+)\s*/\s*(\d+)", text)
            if match:
                index, total = int(match.group(1)), max(1, int(match.group(2)))
                left = max(0, total - index)
                ema = float(scope["ema"])
                text += f" · {ema:.1f}s/frame · ETA ~{self._audit2_eta_text(left * ema)}"
        return super()._set_progress(pct, text)

    def _render_one(self, frame_path, out_path, settings, width, height, frame_number):
        source_ok, source_reason = validate_png(Path(frame_path))
        if not source_ok:
            raise RuntimeError(f"Source frame {frame_number} is corrupt ({source_reason}); re-extract the source frames.")
        started = time.perf_counter()
        attempts = 0
        while True:
            attempts += 1
            try:
                result = super()._render_one(frame_path, out_path, settings, width, height, frame_number)
                ok, reason = validate_png(Path(out_path))
                if not ok:
                    Path(out_path).unlink(missing_ok=True)
                    prune_shot_memory_ranges_safe(self.project_paths()["root"], [(int(frame_number), int(frame_number))])
                    if attempts < 2 and not self.stop_event.is_set():
                        self._log(f"Frame {frame_number} output validation failed ({reason}); retrying once.")
                        continue
                    raise RuntimeError(f"Rendered frame {frame_number} is invalid after retry: {reason}")
                break
            except Exception as exc:
                if self.stop_event.is_set() or attempts >= 3 or not self._audit2_transient_render_error(exc):
                    raise
                delay = 1.0 if attempts == 1 else 2.0
                Path(out_path).unlink(missing_ok=True)
                self._log(f"Transient backend failure on frame {frame_number}; retrying in {delay:.0f}s: {exc}")
                if self.stop_event.wait(delay):
                    raise
        elapsed = time.perf_counter() - started
        scope = self._audit2_render_scope
        if scope is not None and elapsed >= 0.15:
            previous = scope.get("ema")
            scope["ema"] = elapsed if previous is None else float(previous) * 0.75 + elapsed * 0.25
            scope["measured"] = int(scope.get("measured") or 0) + 1
            scope["measured_seconds"] = float(scope.get("measured_seconds") or 0.0) + elapsed
        return result

    def _render_range(self, start, count, test_only):
        info = self._extract_frames()
        paths = self.project_paths()
        source = frame_numbers(paths["frames"])
        start_index = max(0, int(start) - 1)
        selected = source[start_index:] if count is None else source[start_index:start_index + int(count)]
        outdir = paths["test"] if test_only else paths["styled"]
        outdir.mkdir(parents=True, exist_ok=True)
        invalid = invalid_png_numbers(outdir, selected)
        if invalid:
            for number, _reason in invalid:
                (outdir / f"frame_{number:06d}.png").unlink(missing_ok=True)
            if not test_only:
                prune_shot_memory_ranges_safe(paths["root"], [(number, number) for number, _reason in invalid])
            self._log(f"Resume validation removed {len(invalid)} corrupt cached output frame(s).")

        outer_scope = self._audit2_render_scope
        scope = {
            "started": time.perf_counter(),
            "ema": None,
            "measured": 0,
            "measured_seconds": 0.0,
            "total": len(selected),
            "test_only": bool(test_only),
        }
        self._audit2_render_scope = scope
        try:
            return super()._render_range(start, count, test_only)
        finally:
            measured = int(scope.get("measured") or 0)
            if measured:
                seconds = float(scope.get("measured_seconds") or 0.0)
                self._log(
                    f"Render telemetry: {measured} rendered frame(s) measured · "
                    f"{seconds / measured:.2f}s/frame mean · {seconds:.1f}s measured work."
                )
            self._audit2_render_scope = outer_scope

    # ---------- ControlNet reference-unit capacity ----------

    @staticmethod
    def _audit2_unit_capacity(data: Any) -> int | None:
        if not isinstance(data, dict):
            return None
        value = data.get("control_net_unit_count")
        try:
            parsed = int(value)
            return parsed if parsed > 0 else None
        except Exception:
            return None

    def _refresh_reference_capabilities(self):
        caps = super()._refresh_reference_capabilities()
        capacity = None
        try:
            response = requests.get(f"{self.api_url()}/controlnet/settings", timeout=10)
            if response.ok:
                capacity = self._audit2_unit_capacity(response.json())
        except Exception:
            capacity = None
        caps = dict(caps or {})
        caps["controlnet_unit_capacity"] = capacity
        if capacity is not None and capacity < 2:
            caps["ip_adapter"] = False
            caps["reference_only"] = False
            self._log(
                "Reference Lock: ControlNet is configured for one unit; external reference conditioning disabled "
                "so Canny keeps the unit and Shot Memory handles identity continuity."
            )
            try:
                self.after(0, lambda: self.reference_status_var.set("Subject Lock standard · Shot Memory · ControlNet unit limit=1"))
            except Exception:
                pass
        self._reference_caps = caps
        return caps

    # ---------- Preview correctness ----------

    def _workspace_compare_looks_job(self) -> None:
        snapshot = copy.deepcopy(getattr(self, "_director_timeline", {}) or {})
        timeline_path = self._timeline_path()
        disk_before = timeline_path.read_bytes() if timeline_path.exists() else None
        try:
            return super()._workspace_compare_looks_job()
        finally:
            self._director_timeline = snapshot
            self._efficiency_plan_dirty = True
            try:
                if disk_before is not None:
                    atomic_bytes_write(timeline_path, disk_before)
                else:
                    atomic_json_write(timeline_path, snapshot)
            except Exception as exc:
                self._log(f"Compare Looks timeline restore failed: {exc}")
            try:
                self.after(0, self._director_load_selected_shot)
            except Exception:
                pass

    def _workspace_sequence_job(self) -> None:
        super()._workspace_sequence_job()
        if self.stop_event.is_set():
            return
        try:
            timeline = self._director_timeline
            shot = self._selected_shot()
            if not shot:
                return
            numbers = sequence_frame_numbers(list(timeline.get("shots", [])), int(shot["id"]), per_side=6)
            if not numbers:
                return
            start, count = numbers[0], len(numbers)
            if any(not (self.project_paths()["test"] / f"frame_{number:06d}.png").exists() for number in numbers):
                return
            self._ensure_workspace_dirs()
            output = self.project_paths()["sequence"] / f"SHOT_{int(shot['id']):02d}_ORIGINAL_VS_STYLED.mp4"
            fps = float(timeline.get("fps") or 30.0)
            self._run([
                "ffmpeg", "-y",
                "-framerate", f"{fps:.8f}", "-start_number", str(start), "-i", str(self.project_paths()["frames"] / "frame_%06d.png"),
                "-framerate", f"{fps:.8f}", "-start_number", str(start), "-i", str(self.project_paths()["test"] / "frame_%06d.png"),
                "-filter_complex",
                "[0:v]scale=-2:360:flags=lanczos[left];[1:v]scale=-2:360:flags=lanczos[right];[left][right]hstack=inputs=2[v]",
                "-map", "[v]", "-frames:v", str(count),
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                str(output),
            ])
            self._log(f"Original-vs-styled test clip: {output}")
            self._set_progress(100, f"Sequence + comparison ready · {output.name}")
        except Exception as exc:
            self._log(f"Original-vs-styled comparison clip skipped: {exc}")

    # ---------- VFR-safe, crash-safe assembly ----------

    @staticmethod
    def _audit2_temp_media(root: Path, stem: str) -> Path:
        return Path(root) / f".{stem}.{os.getpid()}.{time.time_ns()}.mp4"

    def _audit2_validate_media(self, path: Path, width: int, height: int, duration: float, require_audio: bool = False) -> dict[str, Any]:
        if not path.exists() or path.stat().st_size < 8192:
            raise RuntimeError(f"Encoded media is missing or unexpectedly small: {path.name}")
        probe = self._ffprobe_json(path)
        streams = list(probe.get("streams") or [])
        video = next((item for item in streams if str(item.get("codec_type")) == "video"), None)
        if not video:
            raise RuntimeError(f"Encoded media has no video stream: {path.name}")
        actual = (int(video.get("width") or 0), int(video.get("height") or 0))
        if actual != (int(width), int(height)):
            raise RuntimeError(f"Encoded dimensions are wrong: expected {width}x{height}, got {actual[0]}x{actual[1]}")
        actual_duration = float((probe.get("format") or {}).get("duration") or 0.0)
        if duration > 0 and abs(actual_duration - duration) > max(0.35, duration * 0.025):
            raise RuntimeError(f"Encoded duration is wrong: expected about {duration:.3f}s, got {actual_duration:.3f}s")
        if require_audio and not any(str(item.get("codec_type")) == "audio" for item in streams):
            raise RuntimeError("Encoded final video lost the source audio stream.")
        return probe

    def _assemble(self, info):
        if getattr(self, "_workspace_partial_render", False):
            return super()._assemble(info)
        paths = self.project_paths()
        video = Path(self.video_var.get().strip()).expanduser().resolve()
        source_numbers = frame_numbers(paths["frames"])
        styled_numbers = frame_numbers(paths["styled"])
        if not source_numbers or styled_numbers != source_numbers:
            source_set, styled_set = set(source_numbers), set(styled_numbers)
            raise RuntimeError(
                "Cannot assemble: styled frame sequence must exactly match source frames. "
                f"source={len(source_numbers)} styled={len(styled_numbers)} "
                f"missing={sorted(source_set - styled_set)[:12]} extras={sorted(styled_set - source_set)[:12]}"
            )
        corrupt = invalid_png_numbers(paths["styled"], styled_numbers)
        if corrupt:
            raise RuntimeError(f"Cannot assemble: styled frame {corrupt[0][0]} is corrupt ({corrupt[0][1]}). Rerun to repair it.")

        timing = self._audit2_timing or load_json(paths["source_timing"])
        durations = list(timing.get("durations") or [])
        if len(durations) != len(styled_numbers):
            fallback = 1.0 / max(0.001, float(info.get("fps") or 30.0))
            durations = [fallback] * len(styled_numbers)
        total_duration = float(sum(float(value) for value in durations))
        paths["timing_dir"].mkdir(parents=True, exist_ok=True)
        write_ffconcat(paths["styled_concat"], paths["styled"], styled_numbers, durations)
        final_w, final_h = self._hardening_final_dimensions(info)
        silent_tmp = self._audit2_temp_media(paths["root"], "styled_silent")
        final_tmp = self._audit2_temp_media(paths["root"], "FINAL_STYLED")
        try:
            self._set_progress(92, "Encoding styled video with source timing…")
            self._run([
                "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(paths["styled_concat"]),
                "-frames:v", str(len(styled_numbers)), "-vsync", "vfr",
                "-vf", f"scale={final_w}:{final_h}:flags=lanczos",
                "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                str(silent_tmp),
            ])
            self._audit2_validate_media(silent_tmp, final_w, final_h, total_duration, require_audio=False)
            os.replace(silent_tmp, paths["silent"])

            source_probe = self._ffprobe_json(video)
            source_has_audio = any(str(item.get("codec_type")) == "audio" for item in source_probe.get("streams") or [])
            self._set_progress(97, "Restoring original audio…")
            self._run([
                "ffmpeg", "-y", "-i", str(paths["silent"]), "-i", str(video),
                "-map", "0:v:0", "-map", "1:a:0?", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                "-t", f"{total_duration:.9f}", "-movflags", "+faststart", str(final_tmp),
            ])
            self._audit2_validate_media(final_tmp, final_w, final_h, total_duration, require_audio=source_has_audio)
            os.replace(final_tmp, paths["final"])
        finally:
            silent_tmp.unlink(missing_ok=True)
            final_tmp.unlink(missing_ok=True)
        self._set_progress(100, f"DONE: {paths['final']}")
        self._log(
            f"FINAL VIDEO: {paths['final']} · {final_w}x{final_h} · {len(styled_numbers)} frames · "
            f"timing={timing.get('mode', 'fallback')}{' VFR' if timing.get('variable') else ''}"
        )

    def _autopilot_verify_final(self):
        report = super()._autopilot_verify_final()
        timing = self._audit2_timing or load_json(self.project_paths()["source_timing"])
        report["timing_mode"] = str(timing.get("mode") or "constant-fallback")
        report["variable_frame_rate"] = bool(timing.get("variable"))
        report["source_fingerprint_algo"] = FULL_FINGERPRINT_ALGO
        report["runtime_version"] = RUNTIME_VERSION
        atomic_json_write(self.project_paths()["autopilot_verify"], report)
        return report

    # ---------- STOP / graceful close ----------

    def _audit2_interrupt_webui(self) -> None:
        try:
            requests.post(f"{self.api_url()}/sdapi/v1/interrupt", timeout=3)
        except Exception:
            pass

    def _stop_clicked(self):
        self.stop_event.set()
        self._log("STOP requested · interrupting the current WebUI generation when supported.")
        try:
            import threading
            threading.Thread(target=self._audit2_interrupt_webui, daemon=True).start()
        except Exception:
            pass

    def _workspace_show_error(self, exc: Exception) -> None:
        if self.stop_event.is_set():
            self._log(f"Render stopped: {exc}")
            self._set_progress(0, "Render stopped safely")
            try:
                if hasattr(self, "autopilot_status_var"):
                    self.after(0, lambda: self.autopilot_status_var.set("STOPPED · partial frames preserved"))
            except Exception:
                pass
            return
        return super()._workspace_show_error(exc)

    def _audit2_close_requested(self):
        if self.worker and self.worker.is_alive():
            from tkinter import messagebox
            if not messagebox.askyesno(
                "ComicFrame Studio",
                "A job is still running. Stop it and close after the current backend request exits?\n\nCompleted frames remain resumable.",
            ):
                return
            self._audit2_closing = True
            self._stop_clicked()
            self.after(100, self._audit2_finish_close)
            return
        self.destroy()

    def _audit2_finish_close(self):
        if self.worker and self.worker.is_alive():
            self.after(100, self._audit2_finish_close)
            return
        try:
            self.destroy()
        except Exception:
            pass

    # ---------- Profile ----------

    def _render_profile(self) -> dict:
        profile = super()._render_profile()
        profile["media_integrity"] = {
            "version": RUNTIME_VERSION,
            "full_source_sha256": True,
            "project_ownership_marker": True,
            "display_geometry_from_extracted_pixels": True,
            "source_frame_timing": True,
            "validated_png_resume": True,
            "atomic_media_assembly": True,
            "render_eta": "measured EMA",
            "reference_unit_capacity_check": True,
        }
        profile["app_version"] = RUNTIME_VERSION
        return profile


def main():
    ComicFrameStudioApp().mainloop()


if __name__ == "__main__":
    main()
