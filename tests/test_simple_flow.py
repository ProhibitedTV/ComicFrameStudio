from __future__ import annotations

from pathlib import Path

import comicframe_simple as simple
import comicframe_styles as styles


def _timeline():
    return {
        "fps": 30.0,
        "total_frames": 90,
        "shots": [
            {"id": 1, "start": 1, "end": 30},
            {"id": 2, "start": 31, "end": 60},
            {"id": 3, "start": 61, "end": 90},
        ],
    }


def test_public_process_catalog_is_creative_not_diagnostic():
    values = simple.simple_process_catalog()
    assert "Graphic Shock · maximum print" in values
    assert "Signal Rupture" in values
    assert "Glitch Collapse" in values
    assert "Clean → Chaos · sequence" in values
    assert not any("diagnostic" in value.lower() for value in values)
    assert not any("controlnet test" in value.lower() for value in values)


def test_single_style_process_applies_one_look_to_every_shot():
    timeline = _timeline()
    simple.simple_process_catalog()  # registers the artistic expansion
    simple.apply_simple_process(timeline, "Signal Rupture")
    assert timeline["simple_process"] == "Signal Rupture"
    assert timeline["treatment"] == "Single Style · Signal Rupture"
    assert all(shot["style"] == "Signal Rupture" for shot in timeline["shots"])
    assert all(shot["intensity_start"] == 1.0 for shot in timeline["shots"])
    assert all(shot["intensity_end"] == 1.0 for shot in timeline["shots"])


def test_sequence_process_still_uses_shot_aware_treatment():
    timeline = _timeline()
    simple.apply_simple_process(timeline, "Clean → Chaos · sequence")
    assert timeline["treatment"] == "Clean → Chaos"
    styles_used = [shot["style"] for shot in timeline["shots"]]
    assert len(set(styles_used)) > 1


def test_output_filename_is_beside_source_and_non_destructive(tmp_path: Path):
    video = tmp_path / "camera clip.mp4"
    video.write_bytes(b"source")
    first = simple.next_output_path(video, "Signal Rupture")
    assert first.parent == tmp_path
    assert first.name == "camera clip_comicframe_signal-rupture.mp4"
    first.write_bytes(b"render one")
    second = simple.next_output_path(video, "Signal Rupture")
    assert second.name == "camera clip_comicframe_signal-rupture_2.mp4"
    assert video.read_bytes() == b"source"


def test_output_slug_is_safe_and_stable():
    assert simple.output_slug("Clean → Chaos · sequence") == "clean-to-chaos-sequence"
    assert simple.output_slug("VHS Horror") == "vhs-horror"


def test_simple_profile_metadata_does_not_break_render_cache_compatibility():
    old = {
        "app_version": "2.9.2",
        "checkpoint": "same",
        "sampler": "same",
    }
    new = {
        "app_version": "3.0",
        "checkpoint": "same",
        "sampler": "same",
        "simple_shell": {"version": "3.0"},
    }
    assert simple.ComicFrameStudioApp._profile_without_director(old) == simple.ComicFrameStudioApp._profile_without_director(new)
    new["sampler"] = "different"
    assert simple.ComicFrameStudioApp._profile_without_director(old) != simple.ComicFrameStudioApp._profile_without_director(new)
