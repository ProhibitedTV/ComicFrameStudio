from __future__ import annotations

import app
import comicframe_aggro as aggro
import comicframe_presence as presence
import comicframe_styles as styles


def test_stable_entrypoint_uses_aggro_shell_over_presence():
    assert app.ComicFrameStudioApp is aggro.ComicFrameStudioApp
    assert app.main.__module__ == "comicframe_aggro"
    assert issubclass(aggro.ComicFrameStudioApp, presence.ComicFrameStudioApp)


def test_steps_slider_is_small_and_3060_practical():
    assert aggro.MIN_STEPS == 12
    assert aggro.DEFAULT_STEPS == 24
    assert aggro.MAX_STEPS == 36
    assert aggro.MIN_STEPS < aggro.DEFAULT_STEPS < aggro.MAX_STEPS


def test_controlnet_off_really_removes_structural_pressure():
    params = aggro.aggro_parameters("Cyberpunk Print", False)
    assert params["controlnet_enabled"] is False
    assert params["control_weight"] == 0.0
    assert params["guidance_end"] == 0.0


def test_aggro_gives_cyberpunk_more_diffusion_authority():
    pack = styles.STYLE_PACKS["Cyberpunk Print"]
    params = aggro.aggro_parameters("Cyberpunk Print", True)
    assert float(params["denoise"]) > pack.denoise
    assert float(params["control_weight"]) < pack.control_weight
    assert float(params["guidance_end"]) < pack.guidance_end
    assert float(params["fx"]) >= pack.fx
    assert float(params["temporal_strength"]) < pack.temporal_strength


def test_experimental_style_gets_more_freedom_than_stable_style():
    wild = aggro.aggro_parameters("Signal Rupture", True)
    stable = aggro.aggro_parameters("Clean Graphic Novel", True)
    assert float(wild["control_weight"]) < float(stable["control_weight"])
    assert float(wild["guidance_end"]) < float(stable["guidance_end"])


def test_creative_controls_must_invalidate_render_cache():
    base = {
        "app_version": "3.2",
        "checkpoint": "same",
        "simple_shell": {"presence_version": "3.2"},
        "creative_controls": {"version": "3.3", "controlnet": True, "aggro": True, "steps": 24},
    }
    changed = {
        **base,
        "creative_controls": {"version": "3.3", "controlnet": False, "aggro": True, "steps": 18},
    }
    left = aggro.ComicFrameStudioApp._profile_without_director(base)
    right = aggro.ComicFrameStudioApp._profile_without_director(changed)
    assert left != right
    assert "simple_shell" not in left
    assert left["creative_controls"]["controlnet"] is True
