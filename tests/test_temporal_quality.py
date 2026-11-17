from __future__ import annotations

from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from comicframe_efficiency import RenderIntelligenceMixin as Efficiency
from comicframe_optical_flow import OpticalFlowTemporalMixin as Flow
from tools.evaluate_temporal import evaluate, fixture, legacy_confidence


@pytest.mark.parametrize("quality", [False, True])
def test_confidence_feathering_never_revives_invalid_or_occluded_pixels(quality):
    prev = np.full((48, 64), 70, np.uint8)
    cur = prev.copy()
    cur[:, 28:34] = 255
    forward = np.zeros((48, 64, 2), np.float32)
    backward = forward.copy()
    forward[..., 0], backward[..., 0] = -3, 3
    confidence = Flow._transport_confidence(prev, cur, forward, backward, quality)
    old = legacy_confidence(prev, cur, forward, backward, quality)
    assert np.max(confidence[:, -3:]) == 0
    assert np.max(confidence[:, 28:34]) < 1e-6
    assert np.mean(old[:, -3:]) > 0.05  # Fixture exposes the actual baseline defect.
    assert confidence[20, 10] > 0.99


def test_full_resolution_support_and_adaptive_previous_dimensions():
    previous = np.zeros((24, 32, 3), np.uint8)
    previous[:, 16:] = 200
    backward = np.zeros((12, 16, 2), np.float32)
    confidence = np.ones((12, 16), np.float32)
    confidence[:, -1] = 0
    transported, trust = Flow._warp_previous(previous, backward, confidence, (64, 48))
    assert transported.shape == (48, 64, 3)
    assert transported[:, :30].mean() < 1
    assert transported[:, 34:].mean() > 199
    assert trust[:, -4:].max() == 0
    backward[..., 0] = 2
    _transported, trust = Flow._warp_previous(
        previous, backward, np.ones_like(confidence), (64, 48)
    )
    assert trust[:, -8:].max() == 0


class CachedFlow(Efficiency):
    def __init__(self, root):
        self.root = root
        self._transport_cache_mem = {}
        self._transport_cache_order = []
        self._flow_cache_hits = self._flow_cache_misses = 0

    def project_paths(self):
        return {"flow_cache": self.root}

    def _refresh_flow_cache_status(self):
        pass


@pytest.mark.parametrize("quality", [False, True])
def test_cached_and_uncached_transport_agree_and_floor_reuses_solve(
    tmp_path, monkeypatch, quality
):
    sources, _, _, _ = fixture("occlusion", count=2, size=(192, 144))
    prev, cur = [cv2.cvtColor(source, cv2.COLOR_RGB2GRAY) for source in sources]
    expected_flow, expected = Flow._estimate_transport(prev, cur, quality, 0.35)
    cached = CachedFlow(tmp_path)
    backward, confidence = cached._estimate_transport(prev, cur, quality, 0.35)
    np.testing.assert_array_equal(backward, expected_flow)
    np.testing.assert_array_equal(confidence, expected)
    monkeypatch.setattr(
        Flow,
        "_farneback",
        lambda *args: pytest.fail("cache miss on an unchanged source pair"),
    )
    _, stricter = cached._estimate_transport(prev, cur, quality, 0.65)
    assert np.all(stricter <= confidence)
    # Persisted raw confidence is also shared after a restart.
    disk = CachedFlow(tmp_path)
    _, loaded = disk._estimate_transport(prev, cur, quality, 0.35)
    np.testing.assert_array_equal(loaded, expected)
    assert disk._flow_cache_hits == 1


@pytest.mark.parametrize("bad", ["shape", "nan", "range"])
def test_invalid_cached_transport_is_rebuilt(tmp_path, bad):
    gray = np.zeros((24, 32), np.uint8)
    app = CachedFlow(tmp_path)
    path = app._transport_cache_path(app._transport_key(gray, gray, False))
    confidence = np.ones_like(gray, dtype=np.float32)
    if bad == "nan":
        confidence[0, 0] = np.nan
    elif bad == "range":
        confidence[0, 0] = 10
    else:
        confidence = confidence[:2]
    np.savez(path, flow=np.zeros((*gray.shape, 2)), confidence=confidence)
    _, rebuilt = app._raw_transport(gray, gray, False)
    assert rebuilt.shape == gray.shape
    assert np.isfinite(rebuilt).all() and rebuilt.max() <= 1
    assert app._flow_cache_misses == 1


def test_known_cut_skips_history_even_for_identical_histograms(tmp_path):
    app = SimpleNamespace(_director_timeline={"shots": [{"start": 1}, {"start": 7}]})
    app._temporal_shot_boundary = lambda n: Flow._temporal_shot_boundary(app, n)
    assert app._temporal_shot_boundary(7)
    assert not app._temporal_shot_boundary(6)
    # No frame I/O or backend access is needed on an explicit boundary.
    Flow._temporal_lock(app, tmp_path / "source.png", tmp_path / "out.png", 7)


def test_repeatable_transport_benchmark_reduces_ghosting_without_blur_win():
    report, _ = evaluate("occlusion")
    old, new = report["baseline"], report["patched"]
    assert new["ghosting_error"] < old["ghosting_error"] * 0.97
    assert new["edge_difference"] < old["edge_difference"]
    assert new["detail_retention"] >= old["detail_retention"]
    # Reject a frozen/smeared-output win; retain the moving scene's gradients.
    assert 0.94 < new["detail_retention"] < 1.06
    assert new["mc_difference"] < old["mc_difference"] * 1.05


def test_pan_exposed_border_receives_no_transported_paint():
    report, _ = evaluate("pan")
    assert report["baseline"]["ghosting_error"] > 0
    assert report["patched"]["ghosting_error"] == 0
