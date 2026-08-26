from __future__ import annotations

import inspect

import comicframe_artistic as artistic
import comicframe_simple as simple
import comicframe_style_overhaul as overhaul
import comicframe_styles as styles


def test_public_library_is_materially_larger_and_contains_new_extremes():
    catalog = simple.simple_process_catalog()
    assert len(catalog) >= 55
    for name in (
        "Toxic Xerox",
        "Photocopier Riot",
        "Chrome Nightmare",
        "Dead Channel",
        "Acid Cathedral",
        "Heavy Gouache",
        "Ink Brutalism",
        "Pastel Nightmare",
    ):
        assert name in catalog
        assert name in styles.STYLE_PACKS


def test_every_public_single_style_has_authored_redraw_policy():
    for name in simple.simple_process_catalog():
        if name in simple.SEQUENCE_PROCESSES:
            continue
        pack = styles.STYLE_PACKS[name]
        assert "decisive authored reinterpretation" in pack.prompt
        assert "Aggressive redraw baseline" in pack.description


def test_existing_styles_are_retuned_away_from_filter_strength():
    clean = styles.STYLE_PACKS["Clean Graphic Novel"]
    cyber = styles.STYLE_PACKS["Cyberpunk Print"]
    rupture = styles.STYLE_PACKS["Signal Rupture"]

    assert clean.denoise >= 0.53
    assert clean.control_weight <= 0.82
    assert clean.guidance_end <= 0.82

    assert cyber.denoise >= 0.59
    assert cyber.control_weight <= 0.70
    assert cyber.fx >= 0.76

    assert rupture.denoise >= 0.64
    assert rupture.control_weight <= 0.55
    assert rupture.guidance_end <= 0.62
    assert rupture.fx >= 0.90


def test_experimental_new_styles_are_registered_with_artistic_finisher():
    for name in ("Toxic Xerox", "Dead Channel", "Memory Burn", "Pastel Nightmare"):
        assert name in artistic.ARTISTIC_STYLE_PACKS
        assert artistic.STYLE_STABILITY[name] == "Experimental"


def test_aggro_is_not_a_public_control_anymore():
    source = inspect.getsource(overhaul.ComicFrameStudioApp._install_simple_shell)
    assert "simple_aggro_toggle.grid_remove" in source
    assert overhaul.STYLE_POLICY_VERSION == "3.4"


def test_public_controls_remain_controlnet_and_steps_semantically():
    assert overhaul.MIN_STEPS == 12
    assert overhaul.DEFAULT_STEPS == 24
    assert overhaul.MAX_STEPS == 36
    assert "CONTROLNET" not in " ".join(simple.simple_process_catalog()).upper()


def test_style_policy_change_is_cache_significant():
    old = {
        "checkpoint": "same",
        "creative_controls": {"version": "3.3", "controlnet": True, "aggro": True, "steps": 24},
    }
    new = {
        "checkpoint": "same",
        "creative_controls": {"version": "3.4", "controlnet": True, "steps": 24, "style_policy": "aggressive-by-default"},
    }
    assert overhaul.ComicFrameStudioApp._profile_without_director(old) != overhaul.ComicFrameStudioApp._profile_without_director(new)
