from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

import comicframe_artistic as artistic
import comicframe_product as product
import comicframe_simple as simple
import comicframe_styles as styles
from comicframe_fx import GraphicFXSettings, apply_graphic_fx
from tools.evaluate_temporal import fixture


def test_dream_is_a_registered_diffusion_style_with_a_paint_finish():
    assert "Dream Rotoscope" in simple.simple_process_catalog()
    pack = styles.STYLE_PACKS["Dream Rotoscope"]
    assert pack.finish == "dream_rotoscope"
    assert "rotoscope" in pack.prompt and "stable expressive faces" in pack.prompt
    assert not any(
        (
            pack.fx_ink,
            pack.fx_posterize,
            pack.fx_halftone,
            pack.fx_misregister,
            pack.fx_grain,
        )
    )
    assert artistic.STYLE_STABILITY["Dream Rotoscope"] == "High"
    params = product.aggressive_render_parameters("Dream Rotoscope", True)
    assert params["denoise"] == 0.58
    assert params["control_weight"] == 0.80 and params["temporal_strength"] == 0.26
    assert (
        product.aggressive_render_parameters("Dream Rotoscope", False)["control_weight"]
        == 0
    )


def test_paint_finishing_is_frame_independent_and_preserves_flat_regions(tmp_path):
    sources, _, _, _ = fixture("static", count=1)
    target = tmp_path / "frame.png"
    outputs = []
    for number in (1, 2, 1031):
        Image.fromarray(sources[0]).save(target)
        styles.apply_style_finish(target, "Dream Rotoscope", number)
        outputs.append(target.read_bytes())
    assert outputs[0] == outputs[1] == outputs[2]
    flat = np.asarray(
        artistic.dream_rotoscope_finish(Image.new("RGB", (64, 64), (140, 100, 65)))
    )
    assert np.max(flat.std(axis=(0, 1))) == 0  # No random or screen-space grain.


def test_finish_follows_integer_translation_and_reduces_microdetail():
    sources, _, _, _ = fixture("static", count=1)
    source = sources[0]
    painted = np.asarray(artistic.dream_rotoscope_finish(Image.fromarray(source)))
    shifted = np.roll(source, 5, axis=1)
    shifted_paint = np.asarray(
        artistic.dream_rotoscope_finish(Image.fromarray(shifted))
    )
    np.testing.assert_array_equal(
        np.roll(painted, 5, axis=1)[:, 20:-20], shifted_paint[:, 20:-20]
    )
    gray = cv2.cvtColor(source, cv2.COLOR_RGB2GRAY)
    result_gray = cv2.cvtColor(painted, cv2.COLOR_RGB2GRAY)
    # Simplification has a measurable effect; no assertion of artistic quality.
    assert (
        cv2.Laplacian(result_gray, cv2.CV_32F).var()
        < cv2.Laplacian(gray, cv2.CV_32F).var()
    )
    assert np.abs(painted.astype(float) - source).mean() > 2


def test_disabled_print_operations_do_not_reencode_a_frame(tmp_path, monkeypatch):
    target = tmp_path / "frame.png"
    Image.new("RGB", (64, 64), "red").save(target)
    original = target.read_bytes()
    monkeypatch.setattr(
        Image,
        "open",
        lambda *args: (_ for _ in ()).throw(AssertionError("unnecessary PNG decode")),
    )
    apply_graphic_fx(
        target,
        GraphicFXSettings(
            ink=False,
            posterize=False,
            halftone=False,
            misregistration=False,
            grain=False,
        ),
        1,
    )
    assert target.read_bytes() == original
