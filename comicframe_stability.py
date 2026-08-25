#!/usr/bin/env python3
"""Final stability boundary for ComicFrame Studio v2.9.1.

This module intentionally stays thin.  v2.9 owns media correctness; this layer
seals lifecycle edges that appear only after the application has been used for a
while: changing projects in one process, source mutation during a long job,
resume-profile migrations, and repeated reference-image encoding.
"""
from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import Any

from comicframe_hardening import load_json, runtime_source_key
from comicframe_media import FULL_FINGERPRINT_ALGO, full_file_sha256, safe_reset_generated_state
from comicframe_runtime_v29 import ComicFrameStudioApp as V29ComicFrameStudioApp


STABILITY_VERSION = "2.9.1"
REFERENCE_CACHE_MAX_ENTRIES = 12
REFERENCE_CACHE_MAX_BYTES = 32 * 1024 * 1024


class ComicFrameStudioApp(V29ComicFrameStudioApp):
    """Seal project/source lifecycle state above the audited v2.9 renderer."""

    def __init__(self):
        self._stability_context: tuple[str, str] | None = None
        self._stability_b64_cache: OrderedDict[tuple[str, int, int], str] = OrderedDict()
        self._stability_b64_bytes = 0
        super().__init__()
        self.title("ComicFrame Studio 2.9.1 · Stability Seal")
        self._stability_context = self._stability_context_key()
        for variable in (getattr(self, "video_var", None), getattr(self, "work_var", None)):
            try:
                variable.trace_add("write", self._stability_context_trace)
            except Exception:
                pass

    # ---------- Context ownership ----------

    def _stability_context_key(self) -> tuple[str, str]:
        root_text = str(self.work_var.get() or "").strip() if hasattr(self, "work_var") else ""
        video_text = str(self.video_var.get() or "").strip() if hasattr(self, "video_var") else ""
        root = str(Path(root_text).expanduser().resolve()) if root_text else ""
        video = str(Path(video_text).expanduser().resolve()) if video_text else ""
        return root, video

    def _stability_clear_reference_cache(self) -> None:
        cache = getattr(self, "_stability_b64_cache", None)
        if cache is not None:
            cache.clear()
        self._stability_b64_bytes = 0

    def _stability_reset_memory(self, reason: str = "") -> None:
        """Discard only process-local derived state; project files remain authoritative."""
        self._director_timeline = {}
        self._hardening_source_key = None
        self._hardening_source_info = None
        self._audit2_timing = None
        self._audit2_render_scope = None

        if hasattr(self, "_subjects"):
            self._subjects = {"version": "2.6", "subjects": []}
        if hasattr(self, "_subject_loaded_root"):
            self._subject_loaded_root = None

        for name in ("_workspace_history", "_workspace_redo"):
            value = getattr(self, name, None)
            if isinstance(value, list):
                value.clear()
        if hasattr(self, "_workspace_clipboard"):
            self._workspace_clipboard = None

        if hasattr(self, "_shot_memory_manifest"):
            self._shot_memory_manifest = {"version": "2.0", "anchors": []}
        if hasattr(self, "_shot_memory_cut_frames"):
            self._shot_memory_cut_frames = set()
        if hasattr(self, "_shot_memory_last_applied_frame"):
            self._shot_memory_last_applied_frame = None
        if hasattr(self, "_shot_memory_outdir"):
            self._shot_memory_outdir = None

        transport = getattr(self, "_transport_cache_mem", None)
        if isinstance(transport, dict):
            transport.clear()
        order = getattr(self, "_transport_cache_order", None)
        if isinstance(order, list):
            order.clear()
        if hasattr(self, "_flow_cache_hits"):
            self._flow_cache_hits = 0
        if hasattr(self, "_flow_cache_misses"):
            self._flow_cache_misses = 0

        if hasattr(self, "_efficiency_plan_dirty"):
            self._efficiency_plan_dirty = True
        if hasattr(self, "_efficiency_active_directive"):
            self._efficiency_active_directive = None
        if hasattr(self, "_reference_caps"):
            self._reference_caps = {}
        if hasattr(self, "_autopilot_active"):
            self._autopilot_active = False

        self._stability_clear_reference_cache()
        if reason:
            try:
                self._log(f"Stability Seal: cleared process-local project state · {reason}")
            except Exception:
                pass

    def _stability_reconcile_context(self) -> bool:
        current = self._stability_context_key()
        previous = getattr(self, "_stability_context", None)
        if previous is None:
            self._stability_context = current
            return False
        if current == previous:
            return False
        self._stability_context = current
        self._stability_reset_memory("project/source selection changed")
        return True

    def _stability_context_trace(self, *_args) -> None:
        changed = self._stability_reconcile_context()
        if not changed:
            return
        try:
            self.after_idle(self._workspace_refresh_all)
        except Exception:
            pass

    def _load_director_timeline(self, silent: bool = False):
        self._stability_reconcile_context()
        return super()._load_director_timeline(silent=silent)

    def _ensure_director_timeline(self):
        self._stability_reconcile_context()
        return super()._ensure_director_timeline()

    def _workspace_refresh_all(self):
        self._stability_reconcile_context()
        return super()._workspace_refresh_all()

    def _analyze_shots(self):
        self._stability_reconcile_context()
        return super()._analyze_shots()

    # ---------- Exact-source lifecycle guard ----------

    @staticmethod
    def _stability_source_matches_metadata(video: Path, metadata: dict[str, Any]) -> bool:
        expected = str(metadata.get("source_fingerprint") or "")
        if not expected or str(metadata.get("source_fingerprint_algo") or "") != FULL_FINGERPRINT_ALGO:
            return False
        path = Path(video).expanduser().resolve()
        if not path.exists():
            return False
        try:
            expected_size = int(metadata.get("source_bytes") or 0)
            if expected_size and path.stat().st_size != expected_size:
                return False
        except Exception:
            return False
        return full_file_sha256(path) == expected

    def _extract_frames(self):
        self._stability_reconcile_context()
        video = Path(self.video_var.get().strip()).expanduser().resolve()
        before_key = runtime_source_key(video)
        previous_meta = dict(self._hardening_source_info or load_json(self.project_paths()["meta"]))
        previous_fp = str(previous_meta.get("source_fingerprint") or "")

        metadata = super()._extract_frames()
        after_key = runtime_source_key(video)
        if before_key != after_key:
            root = self.project_paths()["root"]
            try:
                safe_reset_generated_state(root)
            finally:
                self._stability_reset_memory("source file changed during extraction")
            raise RuntimeError(
                "The source video changed while ComicFrame was reading it. Generated state was cleared so frames from two source revisions cannot mix."
            )

        current_fp = str(metadata.get("source_fingerprint") or "")
        if previous_fp and current_fp and previous_fp != current_fp:
            # v2.9 already reset incompatible on-disk state. Seal the other half:
            # the process must not keep a timeline/subject plan from the old bytes.
            self._stability_reset_memory("source bytes changed in the current project")
            self._stability_context = self._stability_context_key()
        return metadata

    def _stability_assert_source_unchanged(self) -> None:
        paths = self.project_paths()
        metadata = self._hardening_source_info or load_json(paths["meta"])
        video_text = self.video_var.get().strip()
        if not video_text:
            raise RuntimeError("Source video path is empty before final assembly.")
        video = Path(video_text).expanduser().resolve()
        if not self._stability_source_matches_metadata(video, metadata):
            raise RuntimeError(
                "The source video changed after frames were extracted. Final assembly was stopped before mismatched audio/timing could be written. "
                "Run the project again so ComicFrame can bind it to one exact source revision."
            )

    def _assemble(self, info):
        if not getattr(self, "_workspace_partial_render", False):
            self._stability_assert_source_unchanged()
        return super()._assemble(info)

    # ---------- Bounded image-encoding cache ----------

    def _encode_file(self, path):
        source = Path(path).expanduser().resolve()
        stat = source.stat()
        key = (str(source), int(stat.st_size), int(stat.st_mtime_ns))
        cache = self._stability_b64_cache
        cached = cache.get(key)
        if cached is not None:
            cache.move_to_end(key)
            return cached

        encoded = super()._encode_file(source)
        cost = len(encoded)
        cache[key] = encoded
        cache.move_to_end(key)
        self._stability_b64_bytes += cost
        while cache and (
            len(cache) > REFERENCE_CACHE_MAX_ENTRIES
            or self._stability_b64_bytes > REFERENCE_CACHE_MAX_BYTES
        ):
            _old_key, old_value = cache.popitem(last=False)
            self._stability_b64_bytes = max(0, self._stability_b64_bytes - len(old_value))
        return encoded

    # ---------- Resume migration ----------

    @staticmethod
    def _profile_without_director(profile: dict[str, Any]) -> dict[str, Any]:
        normalized = V29ComicFrameStudioApp._profile_without_director(profile)
        # These layers affect source validation, preview/assembly safety and
        # lifecycle behavior, not the pixels generated for a frame.  Timeline
        # signatures still own reference/subject/render-plan invalidation.
        normalized.pop("media_integrity", None)
        normalized.pop("stability_seal", None)
        return normalized

    def _render_range(self, start, count, test_only):
        self._stability_reconcile_context()
        return super()._render_range(start, count, test_only)

    def _render_profile(self) -> dict[str, Any]:
        profile = super()._render_profile()
        profile["stability_seal"] = {
            "version": STABILITY_VERSION,
            "context_scoped_memory": True,
            "source_reverified_before_assembly": True,
            "bounded_reference_encoding_cache": True,
            "resume_metadata_migration": True,
        }
        profile["app_version"] = STABILITY_VERSION
        return profile


def main():
    ComicFrameStudioApp().mainloop()


if __name__ == "__main__":
    main()
