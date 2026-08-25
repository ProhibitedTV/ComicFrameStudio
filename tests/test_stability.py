from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

import pytest

from comicframe_manifest_safety import prune_shot_memory_ranges_safe, safe_leaf_path
from comicframe_media import FULL_FINGERPRINT_ALGO, full_file_sha256
from comicframe_stability import (
    REFERENCE_CACHE_MAX_ENTRIES,
    ComicFrameStudioApp,
)


class FakeVar:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def bare_app(tmp_path: Path) -> ComicFrameStudioApp:
    app = object.__new__(ComicFrameStudioApp)
    app.work_var = FakeVar(str(tmp_path / "project"))
    app.video_var = FakeVar(str(tmp_path / "source.mp4"))
    app._stability_context = (str((tmp_path / "old-project").resolve()), str((tmp_path / "old.mp4").resolve()))
    app._stability_b64_cache = OrderedDict()
    app._stability_b64_bytes = 0
    app._director_timeline = {"shots": [{"id": 99}]}
    app._hardening_source_key = ("old",)
    app._hardening_source_info = {"source_fingerprint": "old"}
    app._audit2_timing = {"durations": [1.0]}
    app._audit2_render_scope = {"ema": 1.0}
    app._subjects = {"version": "2.6", "subjects": [{"id": "old"}]}
    app._subject_loaded_root = "old"
    app._workspace_history = [{"old": True}]
    app._workspace_redo = [{"old": True}]
    app._workspace_clipboard = {"style": "old"}
    app._shot_memory_manifest = {"version": "2.0", "anchors": [{"frame": 1}]}
    app._shot_memory_cut_frames = {2}
    app._shot_memory_last_applied_frame = 3
    app._shot_memory_outdir = tmp_path / "old"
    app._transport_cache_mem = {"old": (1, 2)}
    app._transport_cache_order = ["old"]
    app._flow_cache_hits = 9
    app._flow_cache_misses = 8
    app._efficiency_plan_dirty = False
    app._efficiency_active_directive = {"old": True}
    app._reference_caps = {"old": True}
    app._autopilot_active = True
    app._stability_b64_cache[("old", 1, 1)] = "YWJj"
    app._stability_b64_bytes = 4
    app._log = lambda _message: None
    return app


def test_context_switch_discards_all_process_local_project_state(tmp_path: Path):
    app = bare_app(tmp_path)
    assert app._stability_reconcile_context() is True
    assert app._director_timeline == {}
    assert app._hardening_source_key is None
    assert app._hardening_source_info is None
    assert app._audit2_timing is None
    assert app._subjects["subjects"] == []
    assert app._subject_loaded_root is None
    assert app._workspace_history == []
    assert app._workspace_redo == []
    assert app._workspace_clipboard is None
    assert app._shot_memory_manifest["anchors"] == []
    assert app._shot_memory_cut_frames == set()
    assert app._shot_memory_last_applied_frame is None
    assert app._transport_cache_mem == {}
    assert app._transport_cache_order == []
    assert app._flow_cache_hits == 0
    assert app._flow_cache_misses == 0
    assert app._efficiency_plan_dirty is True
    assert app._efficiency_active_directive is None
    assert app._reference_caps == {}
    assert app._autopilot_active is False
    assert len(app._stability_b64_cache) == 0
    assert app._stability_b64_bytes == 0


def test_same_context_preserves_loaded_timeline(tmp_path: Path):
    app = bare_app(tmp_path)
    app._stability_context = app._stability_context_key()
    assert app._stability_reconcile_context() is False
    assert app._director_timeline["shots"][0]["id"] == 99


def test_resume_normalization_ignores_only_non_pixel_audit_metadata():
    old = {
        "app_version": "2.8",
        "runtime_hardening": {"version": "2.8"},
        "checkpoint": "same-model",
        "sampler": "same-sampler",
    }
    new = {
        **old,
        "app_version": "2.9.1",
        "media_integrity": {"version": "2.9"},
        "stability_seal": {"version": "2.9.1"},
    }
    assert ComicFrameStudioApp._profile_without_director(old) == ComicFrameStudioApp._profile_without_director(new)

    changed = dict(new)
    changed["sampler"] = "different-sampler"
    assert ComicFrameStudioApp._profile_without_director(old) != ComicFrameStudioApp._profile_without_director(changed)


def test_source_match_requires_exact_full_hash_even_at_same_size(tmp_path: Path):
    source = tmp_path / "source.bin"
    source.write_bytes(b"A" * 8192)
    metadata = {
        "source_fingerprint": full_file_sha256(source),
        "source_fingerprint_algo": FULL_FINGERPRINT_ALGO,
        "source_bytes": source.stat().st_size,
    }
    assert ComicFrameStudioApp._stability_source_matches_metadata(source, metadata)
    with source.open("r+b") as handle:
        handle.seek(4096)
        handle.write(b"B" * 128)
    assert source.stat().st_size == metadata["source_bytes"]
    assert not ComicFrameStudioApp._stability_source_matches_metadata(source, metadata)


def test_encoding_cache_reuses_reference_and_remains_bounded(tmp_path: Path):
    app = object.__new__(ComicFrameStudioApp)
    app._stability_b64_cache = OrderedDict()
    app._stability_b64_bytes = 0

    first = tmp_path / "first.bin"
    first.write_bytes(b"repeat-me")
    one = app._encode_file(first)
    two = app._encode_file(first)
    assert one == two
    assert len(app._stability_b64_cache) == 1

    for index in range(REFERENCE_CACHE_MAX_ENTRIES + 5):
        path = tmp_path / f"ref_{index}.bin"
        path.write_bytes((f"reference-{index}" * 50).encode())
        app._encode_file(path)
    assert len(app._stability_b64_cache) <= REFERENCE_CACHE_MAX_ENTRIES


def test_encoding_cache_key_changes_when_file_changes(tmp_path: Path):
    app = object.__new__(ComicFrameStudioApp)
    app._stability_b64_cache = OrderedDict()
    app._stability_b64_bytes = 0
    path = tmp_path / "ref.bin"
    path.write_bytes(b"one")
    before = app._encode_file(path)
    path.write_bytes(b"two-two")
    after = app._encode_file(path)
    assert before != after


def test_shot_memory_root_symlink_is_refused_without_touching_target(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "keep.txt"
    sentinel.write_text("keep")
    try:
        (project / "shot_memory").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(RuntimeError, match="safely confined"):
        prune_shot_memory_ranges_safe(project, [(1, 10)])
    assert sentinel.read_text() == "keep"


def test_windows_device_names_are_not_valid_manifest_leaves(tmp_path: Path):
    assert safe_leaf_path(tmp_path, "CON") is None
    assert safe_leaf_path(tmp_path, "con.txt") is None
    assert safe_leaf_path(tmp_path, "LPT9.png") is None
    assert safe_leaf_path(tmp_path, "normal_ref.png") is not None
