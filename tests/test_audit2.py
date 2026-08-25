from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from PIL import Image

import app
from comicframe_hardening import sampled_file_sha256
from comicframe_media import (
    FULL_FINGERPRINT_ALGO,
    PROJECT_MARKER,
    choose_fps_expression,
    ensure_project_owned,
    frame_numbers,
    frame_sequence_report,
    frame_timing_from_probe,
    full_file_sha256,
    safe_reset_generated_state,
    validate_png,
    write_ffconcat,
)
from comicframe_runtime_v29 import ComicFrameStudioApp


class FakeVar:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def test_stable_app_entrypoint_exports_v29_runtime():
    assert app.ComicFrameStudioApp is ComicFrameStudioApp
    assert app.main.__module__ == "comicframe_runtime_v29"


def test_second_audit_does_not_add_a_feature_mixin():
    names = [cls.__name__ for cls in ComicFrameStudioApp.__mro__]
    assert "MediaIntegrityMixin" not in names
    assert "HardeningMixin" not in names
    assert names.index("AutoPilotMixin") < names.index("SubjectLibraryMixin") < names.index("RenderIntelligenceMixin")


def test_fps_selection_rejects_zero_over_zero():
    expr, fps = choose_fps_expression("0/0", "30000/1001")
    assert expr == "30000/1001"
    assert 29.96 < fps < 29.98
    assert choose_fps_expression("nan", "0/0") == ("30/1", 30.0)


def test_frame_numbers_support_more_than_six_digits(tmp_path: Path):
    frames = tmp_path / "frames"
    frames.mkdir()
    for name in ("frame_000001.png", "frame_999999.png", "frame_1000000.png"):
        (frames / name).write_bytes(b"x")
    assert frame_numbers(frames) == [1, 999999, 1000000]


def test_frame_sequence_report_detects_gap_without_building_expected_list(tmp_path: Path):
    frames = tmp_path / "frames"
    frames.mkdir()
    for number in (1, 2, 4):
        (frames / f"frame_{number:06d}.png").write_bytes(b"x")
    report = frame_sequence_report(frames, 4)
    assert not report["valid"]
    assert report["missing"] == [3]


def test_vfr_timing_uses_timestamp_deltas():
    rows = [
        {"best_effort_timestamp_time": "0.000", "pkt_duration_time": "0.033"},
        {"best_effort_timestamp_time": "0.033", "pkt_duration_time": "0.050"},
        {"best_effort_timestamp_time": "0.083", "pkt_duration_time": "0.017"},
        {"best_effort_timestamp_time": "0.100", "pkt_duration_time": "0.040"},
    ]
    timing = frame_timing_from_probe(rows, 4, 30.0)
    assert timing["mode"] == "timestamps"
    assert timing["variable"] is True
    assert timing["durations"][:3] == pytest.approx([0.033, 0.050, 0.017], abs=1e-6)
    assert timing["durations"][3] == pytest.approx(0.040, abs=1e-6)


def test_timing_falls_back_when_probe_rows_do_not_match_frames():
    timing = frame_timing_from_probe([], 3, 25.0)
    assert timing["mode"] == "constant-fallback"
    assert timing["variable"] is False
    assert timing["durations"] == pytest.approx([0.04, 0.04, 0.04])


def test_full_fingerprint_catches_edit_outside_old_sample_windows(tmp_path: Path):
    path = tmp_path / "source.bin"
    size = 20 * 1024 * 1024
    path.write_bytes(b"A" * size)
    sampled_before = sampled_file_sha256(path)
    full_before = full_file_sha256(path)
    # 1.5 MiB sits between the first and second 1 MiB windows in the old
    # nine-sample scheme for a 20 MiB file.
    with path.open("r+b") as handle:
        handle.seek(1536 * 1024)
        handle.write(b"B" * 4096)
    sampled_after = sampled_file_sha256(path)
    full_after = full_file_sha256(path)
    assert sampled_before == sampled_after
    assert full_before != full_after


def test_png_validation_rejects_truncated_cache(tmp_path: Path):
    good = tmp_path / "good.png"
    bad = tmp_path / "bad.png"
    Image.new("RGB", (32, 18), (10, 20, 30)).save(good)
    bad.write_bytes(good.read_bytes()[:80])
    assert validate_png(good)[0] is True
    ok, reason = validate_png(bad)
    assert ok is False
    assert "invalid" in reason.lower() or "tiny" in reason.lower()


def test_project_ownership_refuses_generic_generated_name_collision(tmp_path: Path):
    (tmp_path / "cache").mkdir()
    (tmp_path / "cache" / "mine.txt").write_text("user data")
    with pytest.raises(RuntimeError, match="not a recognized ComicFrame project"):
        ensure_project_owned(tmp_path)
    assert (tmp_path / "cache" / "mine.txt").read_text() == "user data"
    assert not (tmp_path / PROJECT_MARKER).exists()


def test_project_ownership_migrates_extraction_only_legacy_project(tmp_path: Path):
    (tmp_path / "source_info.json").write_text(json.dumps({"width": 10, "height": 10, "fps": 30}))
    frames = tmp_path / "frames"
    frames.mkdir()
    (frames / "frame_000001.png").write_bytes(b"legacy")
    assert ensure_project_owned(tmp_path) == "legacy"
    marker = json.loads((tmp_path / PROJECT_MARKER).read_text())
    assert marker["product"] == "ComicFrameStudio"
    assert marker["migrated_legacy"] is True


def test_project_reset_requires_marker_and_preserves_unowned_file(tmp_path: Path):
    (tmp_path / "frames").mkdir()
    user = tmp_path / "notes.txt"
    user.write_text("keep")
    with pytest.raises(RuntimeError):
        safe_reset_generated_state(tmp_path)
    assert user.read_text() == "keep"


def test_owned_project_reset_preserves_user_file(tmp_path: Path):
    assert ensure_project_owned(tmp_path) == "new"
    frames = tmp_path / "frames"
    frames.mkdir()
    (frames / "frame_000001.png").write_bytes(b"generated")
    user = tmp_path / "notes.txt"
    user.write_text("keep")
    safe_reset_generated_state(tmp_path)
    assert user.read_text() == "keep"
    assert not frames.exists()
    assert (tmp_path / PROJECT_MARKER).exists()


def test_project_ownership_rejects_generated_symlink(tmp_path: Path):
    outside = tmp_path / "outside"
    outside.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    try:
        (project / "cache").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(RuntimeError, match="symlink"):
        ensure_project_owned(project)
    assert outside.exists()


def test_ffconcat_has_duration_per_frame_and_repeated_last_file(tmp_path: Path):
    frames = tmp_path / "frames"
    frames.mkdir()
    for number in (1, 2, 3):
        Image.new("RGB", (4, 4), (number, number, number)).save(frames / f"frame_{number:06d}.png")
    target = tmp_path / "list.ffconcat"
    write_ffconcat(target, frames, [1, 2, 3], [0.033, 0.050, 0.017])
    text = target.read_text()
    assert text.startswith("ffconcat version 1.0\n")
    assert text.count("duration ") == 3
    assert text.count("frame_000003.png") == 2


def test_controlnet_unit_capacity_parser():
    assert ComicFrameStudioApp._audit2_unit_capacity({"control_net_unit_count": 1}) == 1
    assert ComicFrameStudioApp._audit2_unit_capacity({"control_net_unit_count": "3"}) == 3
    assert ComicFrameStudioApp._audit2_unit_capacity({}) is None
    assert ComicFrameStudioApp._audit2_unit_capacity({"control_net_unit_count": 0}) is None


def test_transient_retry_does_not_mask_oom():
    assert ComicFrameStudioApp._audit2_transient_render_error(RuntimeError("HTTP 503 backend unavailable"))
    assert ComicFrameStudioApp._audit2_transient_render_error(RuntimeError("connection reset by peer"))
    assert not ComicFrameStudioApp._audit2_transient_render_error(RuntimeError("HTTP 500 CUDA out of memory"))
    assert not ComicFrameStudioApp._audit2_transient_render_error(RuntimeError("NansException was produced"))


def test_eta_formatting_is_human_readable():
    assert ComicFrameStudioApp._audit2_eta_text(8) == "8s"
    assert ComicFrameStudioApp._audit2_eta_text(68) == "1m 08s"
    assert ComicFrameStudioApp._audit2_eta_text(3661) == "1h 01m"


def test_runtime_profile_uses_full_fingerprint_algorithm_constant():
    assert FULL_FINGERPRINT_ALGO == "sha256-full-v1"
