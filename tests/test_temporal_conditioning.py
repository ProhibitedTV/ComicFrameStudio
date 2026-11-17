from __future__ import annotations

import base64
from pathlib import Path

import numpy as np
from PIL import Image

from comicframe_optical_flow import OpticalFlowTemporalMixin
from comicframe_shot_memory import ShotMemoryMixin


class Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class SourcePayload:
    def _build_payload(self, frame_path, settings, width, height, frame_number):
        source = base64.b64encode(Path(frame_path).read_bytes()).decode()
        return {
            "init_images": [source],
            "width": width,
            "height": height,
            "alwayson_scripts": {"controlnet": {"args": [{"image": source}]}},
        }


class MemoryHarness(ShotMemoryMixin, OpticalFlowTemporalMixin, SourcePayload):
    def __init__(self, root):
        self.shot_memory_enabled_var = Var(True)
        self.shot_memory_confidence_var = Var(0.35)
        self.shot_memory_strength_var = Var(0.4)
        self.shot_palette_strength_var = Var(0.14)
        self.shot_memory_status_var = Var("")
        self.temporal_cut_var = Var(0.22)
        self._shot_memory_outdir = root / "styled"
        self._shot_memory_start_frame = 1
        self._shot_memory_cut_frames = set()
        self._director_timeline = {"shots": [{"start": 1}]}
        self._log = lambda *_: None

    def _latest_anchor(self, _frame):
        return None

    def _estimate_transport(self, prev, cur, quality, confidence_floor):
        confidence = np.ones_like(cur, dtype=np.float32)
        confidence[:, :8] = 0
        return np.zeros((*cur.shape, 2), np.float32), confidence


def test_conditioning_reuses_paint_only_on_trusted_pixels_and_keeps_controlnet_source(
    tmp_path,
):
    source, styled = tmp_path / "source", tmp_path / "styled"
    source.mkdir()
    styled.mkdir()
    for number in (1, 2):
        Image.new("RGB", (64, 48), (70, 100, 140)).save(
            source / f"frame_{number:06d}.png"
        )
    Image.new("RGB", (32, 24), (200, 50, 100)).save(styled / "frame_000001.png")
    memory = MemoryHarness(tmp_path)
    frame = source / "frame_000002.png"
    payload = memory._build_payload(frame, None, 64, 48, 2)
    assert (
        base64.b64decode(payload["alwayson_scripts"]["controlnet"]["args"][0]["image"])
        == frame.read_bytes()
    )
    assert base64.b64decode(payload["init_images"][0]) != frame.read_bytes()
    from io import BytesIO

    conditioned = np.asarray(
        Image.open(BytesIO(base64.b64decode(payload["init_images"][0])))
    )
    np.testing.assert_array_equal(
        conditioned[:, :8], np.asarray(Image.open(frame))[:, :8]
    )
    assert conditioned[:, 20:, 0].mean() > 100
    assert memory._shot_memory_last_applied_frame == 2


def test_authored_cut_does_not_condition_from_the_previous_shot(tmp_path):
    memory = MemoryHarness(tmp_path)
    memory._director_timeline["shots"].append({"start": 2})
    frame = tmp_path / "current.png"
    Image.new("RGB", (64, 48), "red").save(frame)
    payload = memory._build_payload(frame, None, 64, 48, 2)
    assert base64.b64decode(payload["init_images"][0]) == frame.read_bytes()
    assert 2 in memory._shot_memory_cut_frames
