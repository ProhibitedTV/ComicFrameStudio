#!/usr/bin/env python3
"""Stable ComicFrame Studio entrypoint."""
import json
import shutil
from pathlib import Path

from comicframe_app import ComicFrameStudioApp as BaseComicFrameStudioApp
from comicframe_artistic import ArtisticExpansionMixin
from comicframe_autopilot import AutoPilotMixin
from comicframe_controlnet import DirectControlNetProbeMixin
from comicframe_controlnet_compat import ControlNetV3CompatMixin
from comicframe_director import EasyShotDirectorMixin
from comicframe_efficiency import PERFORMANCE_MODES, RenderIntelligenceMixin
from comicframe_hardening import (
    HARDENING_VERSION,
    affected_shot_ranges,
    analysis_signature,
    atomic_json_write,
    build_source_metadata,
    canonical_frame_signature,
    changed_frame_numbers,
    clear_directory,
    frame_numbers,
    frame_sequence_report,
    legacy_source_compatible,
    load_json,
    project_has_derived_state,
    prune_shot_memory_ranges,
    reset_project_for_new_source,
    runtime_source_key,
    source_fingerprint,
    touch,
    trim_cache_directory,
)
from comicframe_optical_flow import OpticalFlowTemporalMixin
from comicframe_preflight import ControlNetPreflightMixin
from comicframe_reference_lock import ReferenceLockMixin
from comicframe_shot_memory import ShotMemoryMixin
from comicframe_styles import StylePackMixin
from comicframe_subjects import SubjectLibraryMixin
from comicframe_video_lock import ControlNetFirstVideoMixin
from comicframe_webui_contract import WebUIContractMixin
import comicframe_workspace as workspace_module
from comicframe_workspace import ProjectWorkspaceMixin


# v2.4's workspace predates the newer dependency layers and its pure cache helper
# imports the v2.3 reference signature as a module global. Point that global at the
# canonical v2.7-aware signature so the UI's "reusable" count matches the renderer.
workspace_module.reference_plan_signature = canonical_frame_signature


class ComicFrameStudioApp(
    ControlNetV3CompatMixin,
    AutoPilotMixin,
    SubjectLibraryMixin,
    RenderIntelligenceMixin,
    ProjectWorkspaceMixin,
    ReferenceLockMixin,
    ShotMemoryMixin,
    EasyShotDirectorMixin,
    OpticalFlowTemporalMixin,
    ArtisticExpansionMixin,
    ControlNetPreflightMixin,
    ControlNetFirstVideoMixin,
    StylePackMixin,
    DirectControlNetProbeMixin,
    WebUIContractMixin,
    BaseComicFrameStudioApp,
):
    """Canonical runtime with one-click AutoPilot over the full v2 engine."""

    FLOW_CACHE_MAX_BYTES = 2 * 1024 * 1024 * 1024
    FLOW_CACHE_MAX_FILES = 1600

    def __init__(self):
        self._hardening_source_key = None
        self._hardening_source_info = None
        self._hardening_force_analysis = False
        self._hardening_flow_calls = 0
        super().__init__()
        self.title("ComicFrame Studio 2.8 · Runtime Hardening")
        try:
            for child in self.director_card.winfo_children():
                for widget in child.winfo_children():
                    try:
                        if widget.cget("text") == "Show advanced controls":
                            widget.configure(text="Easy Mode · hide advanced controls")
                    except Exception:
                        pass
        except Exception:
            pass

    # ---------- Source identity / extraction safety ----------

    def _extract_frames(self):
        video = Path(self.video_var.get().strip()).expanduser().resolve()
        if not video.exists():
            raise FileNotFoundError("Choose a valid source video first.")

        runtime_key = runtime_source_key(video)
        paths = self.project_paths()
        cached = self._hardening_source_info
        if self._hardening_source_key == runtime_key and isinstance(cached, dict):
            expected = int(cached.get("frame_count") or 0) or None
            report = frame_sequence_report(paths["frames"], expected)
            if report["valid"]:
                return dict(cached)

        self._check_external()
        for key in ("root", "frames", "styled", "test"):
            paths[key].mkdir(parents=True, exist_ok=True)

        info = self._probe_video(video)
        fingerprint = source_fingerprint(video)
        meta_path = paths["meta"]
        old_meta = load_json(meta_path)
        old_fingerprint = str(old_meta.get("source_fingerprint") or "")

        source_changed = False
        if old_meta:
            if old_fingerprint:
                source_changed = old_fingerprint != fingerprint
            else:
                source_changed = not legacy_source_compatible(old_meta, info, paths["frames"])
        elif project_has_derived_state(paths["root"]):
            # A generated project with no source metadata is not safe to resume.
            source_changed = bool(frame_numbers(paths["frames"]) or (paths["root"] / "comicframe_timeline.json").exists())

        if source_changed:
            self._log("Source content changed for this project directory; clearing ComicFrame-derived state before extraction.")
            reset_project_for_new_source(paths["root"])
            paths = self.project_paths()
            for key in ("root", "frames", "styled", "test"):
                paths[key].mkdir(parents=True, exist_ok=True)
            old_meta = {}
            old_fingerprint = ""

        # Pre-v2.8 projects can be upgraded in place when their legacy source facts
        # and existing extracted sequence agree with the current source.
        if old_meta and not old_fingerprint and legacy_source_compatible(old_meta, info, paths["frames"]):
            report = frame_sequence_report(paths["frames"])
            metadata = build_source_metadata(video, info, fingerprint, int(report["count"]))
            atomic_json_write(paths["meta"], metadata)
            self._hardening_source_key = runtime_key
            self._hardening_source_info = metadata
            self._log(f"Source metadata upgraded safely; reusing {report['count']} extracted frame(s).")
            return dict(metadata)

        expected = None
        if old_fingerprint == fingerprint:
            try:
                expected = int(old_meta.get("frame_count") or 0) or None
            except Exception:
                expected = None
        report = frame_sequence_report(paths["frames"], expected)
        if report["valid"]:
            metadata = build_source_metadata(video, info, fingerprint, int(report["count"]))
            atomic_json_write(paths["meta"], metadata)
            self._hardening_source_key = runtime_key
            self._hardening_source_info = metadata
            self._log(f"Frames already exist and are complete ({report['count']}). Extraction skipped.")
            return dict(metadata)

        if frame_numbers(paths["frames"]):
            self._log(
                "Extracted frame sequence is incomplete or non-contiguous; rebuilding source frames "
                "without discarding compatible styled frames."
            )
            clear_directory(paths["frames"])

        self._set_progress(1, "Extracting source frames…")
        self._run([
            "ffmpeg", "-y", "-i", str(video), "-map", "0:v:0", "-vsync", "0",
            str(paths["frames"] / "frame_%06d.png"),
        ])
        report = frame_sequence_report(paths["frames"])
        if not report["valid"]:
            raise RuntimeError(
                "ffmpeg returned but the extracted source sequence is incomplete/non-contiguous. "
                f"count={report['count']} first={report['first']} last={report['last']}"
            )

        metadata = build_source_metadata(video, info, fingerprint, int(report["count"]))
        atomic_json_write(paths["meta"], metadata)
        self._hardening_source_key = runtime_key
        self._hardening_source_info = metadata
        self._log(f"Extracted {report['count']} frame(s); source fingerprint recorded.")
        self._set_progress(5, f"Extracted {report['count']} frames")
        return dict(metadata)

    # ---------- Shot-analysis reuse ----------

    def _analyze_shots(self):
        info = self._extract_frames()
        cut_setting = float(self.temporal_cut_var.get()) if hasattr(self, "temporal_cut_var") else 0.42
        signature = analysis_signature(
            str(info.get("source_fingerprint") or ""),
            int(info.get("frame_count") or 0),
            cut_setting,
        )
        existing = self._director_timeline if getattr(self, "_director_timeline", {}).get("shots") else self._load_director_timeline(silent=True)
        if (
            not self._hardening_force_analysis
            and existing.get("shots")
            and str(existing.get("analysis_signature") or "") == signature
            and int(existing.get("total_frames") or 0) == int(info.get("frame_count") or 0)
        ):
            self._log(f"Shot analysis cache hit · {len(existing.get('shots', []))} shot(s) reused.")
            try:
                self.after(0, self._refresh_director_ui)
            except Exception:
                pass
            return existing

        timeline = super()._analyze_shots()
        timeline["source_fingerprint"] = str(info.get("source_fingerprint") or "")
        timeline["analysis_signature"] = signature
        atomic_json_write(self._timeline_path(), timeline)
        return timeline

    def _director_analyze_clicked(self) -> None:
        def job():
            self._hardening_force_analysis = True
            try:
                self._analyze_shots()
            except Exception as exc:
                self._workspace_show_error(exc)
            finally:
                self._hardening_force_analysis = False
        self._run_worker(job)

    def _load_director_timeline(self, silent: bool = False):
        timeline = super()._load_director_timeline(silent=silent)
        if not isinstance(timeline, dict):
            return timeline
        try:
            performance = str((timeline.get("render_intelligence") or {}).get("mode") or "")
            if performance in PERFORMANCE_MODES and hasattr(self, "performance_mode_var"):
                self.performance_mode_var.set(performance)
        except Exception:
            pass
        try:
            mode = str((timeline.get("autopilot") or {}).get("mode") or "")
            if mode in ("Safe", "Balanced", "Wild") and hasattr(self, "autopilot_mode_var"):
                self.autopilot_mode_var.set(mode)
        except Exception:
            pass
        return timeline

    # ---------- Canonical selective invalidation ----------

    def _invalidate_changed_timeline_frames(self, old, new) -> int:
        # Once both sides are v2.7-aware, one canonical signature contains all
        # Director -> Reference -> Efficiency -> Subject -> AutoPilot dependencies.
        # Avoid five nested full-frame passes and five rounds of file-system work.
        if isinstance(old.get("autopilot"), dict) and isinstance(new.get("autopilot"), dict):
            changed_frames = changed_frame_numbers(old, new)
            styled = self.project_paths()["styled"]
            removed = 0
            for frame_number in changed_frames:
                candidate = styled / f"frame_{frame_number:06d}.png"
                if candidate.exists():
                    candidate.unlink()
                    removed += 1
            ranges = affected_shot_ranges(old, new, changed_frames)
            pruned = prune_shot_memory_ranges(self.project_paths()["root"], ranges)
            if changed_frames:
                self._log(
                    f"Runtime hardening: one-pass dependency invalidation found {len(changed_frames)} changed frame(s); "
                    f"removed {removed} cached PNG(s), pruned {pruned if pruned >= 0 else 'all'} stale memory anchor(s)."
                )
            return removed
        return super()._invalidate_changed_timeline_frames(old, new)

    def _workspace_rerender_shot_job(self) -> None:
        shot = self._selected_shot()
        if shot:
            start, end = int(shot["start"]), int(shot["end"])
            prune_shot_memory_ranges(self.project_paths()["root"], [(start, end)])
        return super()._workspace_rerender_shot_job()

    # ---------- Persistent flow-cache bound ----------

    def _raw_transport(self, prev_gray, cur_gray, quality: bool):
        result = super()._raw_transport(prev_gray, cur_gray, quality)
        try:
            key = self._transport_key(prev_gray, cur_gray, quality)
            cache_path = self.project_paths()["flow_cache"] / f"{key}.npz"
            if cache_path.exists():
                touch(cache_path)
            self._hardening_flow_calls += 1
            if self._hardening_flow_calls % 64 == 0:
                trimmed = trim_cache_directory(
                    self.project_paths()["flow_cache"],
                    self.FLOW_CACHE_MAX_BYTES,
                    self.FLOW_CACHE_MAX_FILES,
                )
                if trimmed["removed_files"]:
                    self._log(
                        "Flow cache GC: removed "
                        f"{trimmed['removed_files']} old file(s) / {trimmed['removed_bytes'] / (1024**2):.1f} MiB; "
                        f"{trimmed['remaining_bytes'] / (1024**2):.1f} MiB remains."
                    )
        except Exception as exc:
            self._log(f"Flow cache maintenance skipped: {exc}")
        return result

    # ---------- Auto-subject garbage collection ----------

    def _autopilot_plan(self, timeline):
        plan = super()._autopilot_plan(timeline)
        try:
            self._load_subjects(force=True)
            used = {
                str(shot.get("subject_id") or "")
                for shot in timeline.get("shots", [])
                if str(shot.get("subject_id") or "")
            }
            subjects = list(self._subjects.get("subjects", []))
            kept = []
            removed = []
            for subject in subjects:
                sid = str(subject.get("id") or "")
                if sid.startswith("auto_") and sid not in used:
                    removed.append(sid)
                else:
                    kept.append(subject)
            if removed:
                self._subjects["subjects"] = kept
                for sid in removed:
                    root = self._subject_root(sid)
                    if root.exists():
                        shutil.rmtree(root)
                self._save_subjects()
                self._log(f"AutoPilot subject GC: removed {len(removed)} orphan automatic subject(s).")
        except Exception as exc:
            self._log(f"AutoPilot subject GC skipped: {exc}")
        return plan

    # ---------- Deterministic assembly ----------

    def _hardening_final_dimensions(self, info) -> tuple[int, int]:
        source_w, source_h = int(info["width"]), int(info["height"])
        target_w, target_h = self._target_dimensions(source_w, source_h)
        if bool(self.upscale_to_source_var.get()):
            final_w, final_h = source_w, source_h
        else:
            final_w, final_h = target_w, target_h
        # yuv420p/H.264 requires even dimensions on common ffmpeg builds.
        final_w = max(2, int(final_w) - (int(final_w) % 2))
        final_h = max(2, int(final_h) - (int(final_h) % 2))
        return final_w, final_h

    def _assemble(self, info):
        if getattr(self, "_workspace_partial_render", False):
            return super()._assemble(info)

        paths = self.project_paths()
        video = Path(self.video_var.get().strip()).expanduser().resolve()
        source_numbers = frame_numbers(paths["frames"])
        styled_numbers = frame_numbers(paths["styled"])
        if not source_numbers:
            raise RuntimeError("Cannot assemble: no extracted source frames exist.")
        if styled_numbers != source_numbers:
            source_set, styled_set = set(source_numbers), set(styled_numbers)
            missing = sorted(source_set - styled_set)[:12]
            extras = sorted(styled_set - source_set)[:12]
            raise RuntimeError(
                "Cannot assemble: styled frame sequence does not exactly match the source sequence. "
                f"source={len(source_numbers)} styled={len(styled_numbers)} missing={missing} extras={extras}"
            )

        self._set_progress(92, "Encoding styled video…")
        fps_expr = info.get("fps_expr") or str(info["fps"])
        final_w, final_h = self._hardening_final_dimensions(info)
        self._run([
            "ffmpeg", "-y", "-framerate", fps_expr, "-start_number", "1",
            "-i", str(paths["styled"] / "frame_%06d.png"),
            "-frames:v", str(len(source_numbers)),
            "-vf", f"scale={final_w}:{final_h}:flags=lanczos",
            "-c:v", "libx264", "-preset", "medium", "-crf", "17",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(paths["silent"]),
        ])
        self._set_progress(97, "Restoring original audio…")
        self._run([
            "ffmpeg", "-y", "-i", str(paths["silent"]), "-i", str(video),
            "-map", "0:v:0", "-map", "1:a:0?", "-c:v", "copy", "-c:a", "aac",
            "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(paths["final"]),
        ])
        self._set_progress(100, f"DONE: {paths['final']}")
        self._log(f"FINAL VIDEO: {paths['final']} · {final_w}x{final_h} · {len(source_numbers)} frames")

    def _autopilot_verify_final(self):
        report = super()._autopilot_verify_final()
        info = load_json(self.project_paths()["meta"])
        if info:
            expected_w, expected_h = self._hardening_final_dimensions(info)
            actual = (int(report.get("width") or 0), int(report.get("height") or 0))
            if actual != (expected_w, expected_h):
                raise RuntimeError(
                    f"Final dimensions are wrong: expected {expected_w}x{expected_h}, got {actual[0]}x{actual[1]}"
                )
            report["expected_width"] = expected_w
            report["expected_height"] = expected_h
            report["hardening_version"] = HARDENING_VERSION
            atomic_json_write(self.project_paths()["autopilot_verify"], report)
        return report

    @staticmethod
    def _profile_without_director(profile: dict) -> dict:
        """Let timeline dependencies govern selective render invalidation."""
        normalized = json.loads(json.dumps(profile))
        normalized.pop("shot_director", None)
        normalized.pop("reference_lock", None)
        normalized.pop("workspace", None)
        normalized.pop("render_intelligence", None)
        normalized.pop("subject_library", None)
        normalized.pop("autopilot", None)
        normalized.pop("runtime_hardening", None)
        # v2.8 reuses v2.7 frames when their actual per-shot dependencies match.
        normalized.pop("app_version", None)
        return normalized

    def _render_profile(self) -> dict:
        profile = super()._render_profile()
        profile["runtime_hardening"] = {
            "version": HARDENING_VERSION,
            "source_fingerprint": "sampled first/middle/last content",
            "canonical_invalidation": True,
            "bounded_flow_cache_bytes": self.FLOW_CACHE_MAX_BYTES,
            "explicit_final_dimensions": True,
        }
        profile["app_version"] = "2.8"
        return profile


def main():
    ComicFrameStudioApp().mainloop()


if __name__ == "__main__":
    main()
