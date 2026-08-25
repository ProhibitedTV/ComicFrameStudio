from __future__ import annotations

import copy
import json
import os
import time
from pathlib import Path

import comicframe_workspace
from app import ComicFrameStudioApp
from comicframe_hardening import (
    affected_shot_ranges,
    analysis_signature,
    canonical_frame_signature,
    frame_sequence_report,
    reset_project_for_new_source,
    sampled_file_sha256,
    trim_cache_directory,
)
from comicframe_manifest_safety import prune_shot_memory_ranges_safe, safe_leaf_path


class FakeVar:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeWidget:
    def __init__(self, widget_class="TFrame", state="normal", text="", children=None):
        self.widget_class = widget_class
        self.state = state
        self.text = text
        self.children = list(children or [])
        self.exists = True

    def winfo_children(self):
        return self.children

    def winfo_class(self):
        return self.widget_class

    def cget(self, key):
        if key == "state":
            return self.state
        if key == "text":
            return self.text
        raise KeyError(key)

    def configure(self, **kwargs):
        if "state" in kwargs:
            self.state = kwargs["state"]

    def winfo_exists(self):
        return self.exists


def timeline() -> dict:
    return {
        "version": "2.7",
        "fps": 30.0,
        "total_frames": 10,
        "treatment": "Clean Comic",
        "render_intelligence": {"version": "2.5", "mode": "Balanced"},
        "subject_library": {"version": "2.6"},
        "autopilot": {"version": "2.7", "mode": "Balanced", "treatment": "Clean Comic"},
        "shots": [
            {
                "id": 1,
                "start": 1,
                "end": 5,
                "style": "Clean Graphic Novel",
                "intensity_start": 0.40,
                "intensity_end": 0.40,
                "curve": "linear",
                "subject_lock": "Strong",
                "reference_frame": 3,
                "reference_backend_resolved": "Shot Memory",
                "reference_model": "",
                "render_intelligence": {"tier": "easy", "long_edge": 768, "steps": 18},
                "autopilot": {"guarded_intensity": 0.40, "subject_group": ""},
            },
            {
                "id": 2,
                "start": 6,
                "end": 10,
                "style": "Clean Graphic Novel",
                "intensity_start": 0.45,
                "intensity_end": 0.45,
                "curve": "linear",
                "subject_lock": "Strong",
                "reference_frame": 8,
                "reference_backend_resolved": "Shot Memory",
                "reference_model": "",
                "render_intelligence": {"tier": "moderate", "long_edge": 1024, "steps": 22},
                "autopilot": {"guarded_intensity": 0.45, "subject_group": ""},
            },
        ],
    }


def test_source_fingerprint_detects_sampled_content_change(tmp_path: Path):
    path = tmp_path / "video.bin"
    path.write_bytes(b"A" * (4 * 1024 * 1024))
    first = sampled_file_sha256(path)
    with path.open("r+b") as handle:
        handle.seek(2 * 1024 * 1024)
        handle.write(b"B" * 4096)
    second = sampled_file_sha256(path)
    assert first != second


def test_frame_sequence_rejects_gap_and_extra(tmp_path: Path):
    frames = tmp_path / "frames"
    frames.mkdir()
    for number in (1, 2, 4):
        (frames / f"frame_{number:06d}.png").write_bytes(b"x")
    report = frame_sequence_report(frames, expected_count=4)
    assert report["valid"] is False
    assert 3 in report["missing"]

    (frames / "frame_000003.png").write_bytes(b"x")
    assert frame_sequence_report(frames, expected_count=4)["valid"] is True
    (frames / "frame_000005.png").write_bytes(b"x")
    report = frame_sequence_report(frames, expected_count=4)
    assert report["valid"] is False
    assert 5 in report["extras"]


def test_source_reset_removes_only_generated_state(tmp_path: Path):
    for name in ("frames", "styled_frames", "cache", "subjects"):
        directory = tmp_path / name
        directory.mkdir()
        (directory / "generated.txt").write_text("generated")
    (tmp_path / "comicframe_timeline.json").write_text("{}")
    user_file = tmp_path / "keep_me.txt"
    user_file.write_text("mine")

    reset_project_for_new_source(tmp_path)

    assert user_file.read_text() == "mine"
    assert not (tmp_path / "frames").exists()
    assert not (tmp_path / "styled_frames").exists()
    assert not (tmp_path / "comicframe_timeline.json").exists()


def test_canonical_signature_sees_autopilot_and_lower_dependencies():
    old = timeline()
    new = copy.deepcopy(old)
    assert canonical_frame_signature(old, 2) == canonical_frame_signature(new, 2)
    new["shots"][0]["intensity_start"] = 0.55
    new["shots"][0]["intensity_end"] = 0.55
    new["shots"][0]["autopilot"]["guarded_intensity"] = 0.55
    assert canonical_frame_signature(old, 2) != canonical_frame_signature(new, 2)
    assert canonical_frame_signature(old, 7) == canonical_frame_signature(new, 7)


def test_workspace_uses_canonical_signature_after_app_import():
    assert comicframe_workspace.reference_plan_signature is canonical_frame_signature


def test_changed_frame_ranges_expand_to_whole_changed_shot():
    old = timeline()
    new = copy.deepcopy(old)
    ranges = affected_shot_ranges(old, new, [2, 3])
    assert ranges == [(1, 5)]


def test_shot_memory_pruning_is_selective(tmp_path: Path):
    memory = tmp_path / "shot_memory" / "full"
    refs = memory / "references"
    refs.mkdir(parents=True)
    anchors = []
    for frame in (1, 3, 6, 9):
        name = f"anchor_{frame}.png"
        (refs / name).write_bytes(b"png")
        anchors.append({"frame": frame, "shot": 1 if frame <= 5 else 2, "file": name})
    (memory / "manifest.json").write_text(json.dumps({"version": "2.0", "anchors": anchors}))

    removed = prune_shot_memory_ranges_safe(tmp_path, [(1, 5)])
    assert removed == 2
    data = json.loads((memory / "manifest.json").read_text())
    assert [entry["frame"] for entry in data["anchors"]] == [6, 9]
    assert not (refs / "anchor_1.png").exists()
    assert (refs / "anchor_6.png").exists()


def test_manifest_leaf_path_rejects_escape_and_windows_syntax(tmp_path: Path):
    root = tmp_path / "refs"
    root.mkdir()
    assert safe_leaf_path(root, "ref_abc123.png") == root / "ref_abc123.png"
    for value in ("../outside.txt", "..\\outside.txt", "/tmp/outside", "C:\\outside.txt", "x/y.png", "x\\y.png"):
        assert safe_leaf_path(root, value) is None


def test_malicious_shot_memory_filename_cannot_delete_outside_project(tmp_path: Path):
    outside = tmp_path / "outside.txt"
    outside.write_text("do not touch")
    memory = tmp_path / "project" / "shot_memory" / "full"
    refs = memory / "references"
    refs.mkdir(parents=True)
    (memory / "manifest.json").write_text(json.dumps({
        "version": "2.0",
        "anchors": [{"frame": 3, "shot": 1, "file": "../../../../outside.txt"}],
    }))

    assert prune_shot_memory_ranges_safe(tmp_path / "project", [(1, 5)]) == 1
    assert outside.read_text() == "do not touch"


def test_subject_loader_drops_unsafe_ids_and_reference_paths(tmp_path: Path):
    subjects_root = tmp_path / "subjects"
    valid_root = subjects_root / "abc123"
    valid_root.mkdir(parents=True)
    valid_ref = valid_root / "ref_good.png"
    # A real image is needed because the loader content-hashes accepted references.
    from PIL import Image
    Image.new("RGB", (8, 8), (1, 2, 3)).save(valid_ref)
    registry = {
        "version": "2.6",
        "subjects": [
            {
                "id": "abc123",
                "name": "Good",
                "type": "Other",
                "references": [
                    {"id": "refgood", "file": "ref_good.png", "sha256": "", "source_shot": 1, "source_frame": 1},
                    {"id": "evilref", "file": "../../outside.png", "sha256": ""},
                ],
            },
            {"id": "../../evil", "name": "Bad", "type": "Other", "references": []},
        ],
    }
    subjects_root.mkdir(exist_ok=True)
    (subjects_root / "subjects.json").write_text(json.dumps(registry))

    app = object.__new__(ComicFrameStudioApp)
    app._subjects = {"version": "2.6", "subjects": []}
    app._subject_loaded_root = None
    app._log = lambda _message: None
    app.project_paths = lambda: {
        "root": tmp_path,
        "subjects_root": subjects_root,
        "subjects_registry": subjects_root / "subjects.json",
    }

    loaded = ComicFrameStudioApp._load_subjects(app, force=True)
    assert [subject["id"] for subject in loaded["subjects"]] == ["abc123"]
    assert [ref["file"] for ref in loaded["subjects"][0]["references"]] == ["ref_good.png"]


def test_flow_cache_gc_bounds_files_and_bytes(tmp_path: Path):
    cache = tmp_path / "flow"
    cache.mkdir()
    for index in range(10):
        path = cache / f"{index}.npz"
        path.write_bytes(bytes([index]) * 100)
        stamp = time.time() - (100 - index)
        os.utime(path, (stamp, stamp))
    result = trim_cache_directory(cache, max_bytes=600, max_files=6, target_ratio=0.5)
    assert result["removed_files"] > 0
    assert result["remaining_files"] <= 3
    assert result["remaining_bytes"] <= 300


def test_analysis_signature_changes_with_source_or_detector_setting():
    one = analysis_signature("source-a", 100, 0.40)
    assert one != analysis_signature("source-b", 100, 0.40)
    assert one != analysis_signature("source-a", 101, 0.40)
    assert one != analysis_signature("source-a", 100, 0.41)


def test_current_timeline_invalidation_is_one_pass_and_prunes_only_changed_shot(tmp_path: Path):
    old = timeline()
    new = copy.deepcopy(old)
    new["shots"][0]["intensity_start"] = 0.60
    new["shots"][0]["intensity_end"] = 0.60
    new["shots"][0]["autopilot"]["guarded_intensity"] = 0.60

    styled = tmp_path / "styled_frames"
    styled.mkdir()
    for number in range(1, 11):
        (styled / f"frame_{number:06d}.png").write_bytes(b"styled")

    memory = tmp_path / "shot_memory" / "full"
    refs = memory / "references"
    refs.mkdir(parents=True)
    anchors = [
        {"frame": 3, "shot": 1, "file": "a3.png"},
        {"frame": 8, "shot": 2, "file": "a8.png"},
    ]
    for entry in anchors:
        (refs / entry["file"]).write_bytes(b"anchor")
    (memory / "manifest.json").write_text(json.dumps({"version": "2.0", "anchors": anchors}))

    app = object.__new__(ComicFrameStudioApp)
    app.project_paths = lambda: {"root": tmp_path, "styled": styled}
    app._log = lambda _message: None

    removed = ComicFrameStudioApp._invalidate_changed_timeline_frames(app, old, new)
    assert removed == 5
    assert all(not (styled / f"frame_{number:06d}.png").exists() for number in range(1, 6))
    assert all((styled / f"frame_{number:06d}.png").exists() for number in range(6, 11))
    manifest = json.loads((memory / "manifest.json").read_text())
    assert [entry["frame"] for entry in manifest["anchors"]] == [8]


def test_final_dimensions_are_explicit_and_even():
    app = object.__new__(ComicFrameStudioApp)
    app.upscale_to_source_var = FakeVar(False)
    app._target_dimensions = lambda _w, _h: (1024, 576)
    assert ComicFrameStudioApp._hardening_final_dimensions(app, {"width": 1921, "height": 1081}) == (1024, 576)
    app.upscale_to_source_var.set(True)
    assert ComicFrameStudioApp._hardening_final_dimensions(app, {"width": 1921, "height": 1081}) == (1920, 1080)


def test_render_job_locks_interactive_controls_but_keeps_stop_live():
    run = FakeWidget("TFrame", children=[
        FakeWidget("TButton", state="normal", text="ANALYZE + RENDER"),
        FakeWidget("TButton", state="normal", text="STOP"),
        FakeWidget("TCombobox", state="readonly", text=""),
    ])
    app = object.__new__(ComicFrameStudioApp)
    app.left = run
    app._hardening_job_widget_states = []

    ComicFrameStudioApp._hardening_lock_job_controls(app)
    assert run.children[0].state == "disabled"
    assert run.children[1].state == "normal"
    assert run.children[2].state == "disabled"

    ComicFrameStudioApp._hardening_unlock_job_controls(app)
    assert run.children[0].state == "normal"
    assert run.children[1].state == "normal"
    assert run.children[2].state == "readonly"


def test_audit_did_not_add_another_feature_mixin():
    names = [cls.__name__ for cls in ComicFrameStudioApp.__mro__]
    assert "HardeningMixin" not in names
    assert names.index("AutoPilotMixin") < names.index("SubjectLibraryMixin") < names.index("RenderIntelligenceMixin")
