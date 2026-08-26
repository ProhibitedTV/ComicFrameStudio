from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import comicframe_usability as usability
from comicframe_media import PROJECT_MARKER, PROJECT_PRODUCT


def test_preview_cache_never_uses_project_directory(tmp_path: Path):
    video = tmp_path / "camera clip.mp4"
    video.write_bytes(b"video")
    temp_root = tmp_path / "os-temp"
    preview = usability.source_preview_cache_path(video, temp_root=temp_root)
    project = usability.default_project_path_for_video(video)

    assert preview.parent == temp_root
    assert preview.suffix == ".jpg"
    assert project not in preview.parents


def test_preview_only_auto_project_recovers_safely(tmp_path: Path):
    video = tmp_path / "WIN_20260824_12_29_21_Pro.mp4"
    video.write_bytes(b"source")
    root = usability.default_project_path_for_video(video)
    root.mkdir()
    (root / usability.LEGACY_SOURCE_PREVIEW).write_bytes(b"legacy preview")

    assert usability.recover_preview_only_project(root, video) is True
    marker = json.loads((root / PROJECT_MARKER).read_text(encoding="utf-8"))
    assert marker["product"] == PROJECT_PRODUCT
    assert marker["recovered_preview_only"] is True

    # Marker now exists, so the recovery shim is one-shot.
    assert usability.recover_preview_only_project(root, video) is False


def test_preview_recovery_refuses_custom_or_ambiguous_folder(tmp_path: Path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"source")

    custom = tmp_path / "my random folder"
    custom.mkdir()
    (custom / usability.LEGACY_SOURCE_PREVIEW).write_bytes(b"preview")
    assert usability.recover_preview_only_project(custom, video) is False
    assert not (custom / PROJECT_MARKER).exists()

    auto = usability.default_project_path_for_video(video)
    auto.mkdir()
    (auto / usability.LEGACY_SOURCE_PREVIEW).write_bytes(b"preview")
    (auto / "frames").mkdir()
    assert usability.recover_preview_only_project(auto, video) is False
    assert not (auto / PROJECT_MARKER).exists()


def test_parse_video_probe_accepts_rotation_and_rate():
    parsed = usability.parse_video_probe({
        "streams": [{
            "width": 1920,
            "height": 1080,
            "avg_frame_rate": "30000/1001",
            "r_frame_rate": "30/1",
            "nb_frames": "120",
            "tags": {},
            "side_data_list": [{"rotation": -90}],
        }],
        "format": {"duration": "4.004"},
    })
    assert parsed["coded_width"] == 1920
    assert parsed["coded_height"] == 1080
    assert parsed["rotation"] == -90
    assert 29.9 < parsed["fps"] < 30.0
    assert parsed["duration"] == 4.004


def test_probe_falls_back_when_rich_show_entries_is_rejected(monkeypatch, tmp_path: Path):
    video = tmp_path / "camera.mp4"
    video.write_bytes(b"source")
    calls = []
    logs = []

    payload = {
        "streams": [{
            "width": 1280,
            "height": 720,
            "avg_frame_rate": "30/1",
            "r_frame_rate": "30/1",
            "nb_frames": "90",
            "tags": {"rotate": "0"},
        }],
        "format": {"duration": "3.0"},
    }

    def fake_run(command, **_kwargs):
        calls.append(command)
        if len(calls) == 1:
            return SimpleNamespace(
                returncode=1,
                stdout="",
                stderr="No match for section 'stream_side_data'",
            )
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(usability.subprocess, "run", fake_run)

    class Harness:
        def _check_external(self):
            return None

        def _log(self, message):
            logs.append(str(message))

    info = usability.ComicFrameStudioApp._probe_video(Harness(), video)
    assert info["width"] == 1280
    assert info["height"] == 720
    assert len(calls) == 2
    assert any("more portable probe" in line for line in logs)
    assert any("recovered with the portable" in line for line in logs)


def test_probe_final_error_contains_real_ffprobe_diagnostic(monkeypatch, tmp_path: Path):
    video = tmp_path / "bad.mp4"
    video.write_bytes(b"source")

    def fake_run(_command, **_kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="Invalid data found when processing input")

    monkeypatch.setattr(usability.subprocess, "run", fake_run)

    class Harness:
        def _check_external(self):
            return None

        def _log(self, _message):
            return None

    try:
        usability.ComicFrameStudioApp._probe_video(Harness(), video)
    except RuntimeError as exc:
        message = str(exc)
        assert "Invalid data found when processing input" in message
        assert str(video.resolve()) in message
    else:
        raise AssertionError("expected readable ffprobe failure")
