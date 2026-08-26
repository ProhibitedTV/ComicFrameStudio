from __future__ import annotations

import inspect
from pathlib import Path

import app
import comicframe_artistic as artistic
import comicframe_product as product
import comicframe_simple as simple
import comicframe_styles as styles
from comicframe_style_library import NEW_STYLE_SPECS, STYLE_LIBRARY_VERSION


def test_stable_entrypoint_is_the_single_product_shell():
    assert app.ComicFrameStudioApp is product.ComicFrameStudioApp
    assert app.main.__module__ == "comicframe_product"
    modules = [cls.__module__ for cls in product.ComicFrameStudioApp.__mro__]
    for retired in ("comicframe_interface", "comicframe_presence", "comicframe_aggro", "comicframe_style_overhaul"):
        assert retired not in modules


def test_public_library_remains_large_and_curated():
    catalog = simple.simple_process_catalog()
    assert len(catalog) >= 55
    for name in (
        "Toxic Xerox", "Photocopier Riot", "Chrome Nightmare", "Dead Channel",
        "Acid Cathedral", "Heavy Gouache", "Ink Brutalism", "Pastel Nightmare",
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


def test_style_policy_floors_still_hold():
    clean = styles.STYLE_PACKS["Clean Graphic Novel"]
    cyber = styles.STYLE_PACKS["Cyberpunk Print"]
    rupture = styles.STYLE_PACKS["Signal Rupture"]
    assert clean.denoise >= 0.53 and clean.control_weight <= 0.82
    assert cyber.denoise >= 0.59 and cyber.control_weight <= 0.70 and cyber.fx >= 0.76
    assert rupture.denoise >= 0.64 and rupture.control_weight <= 0.55 and rupture.fx >= 0.90


def test_new_style_finishers_resolve_to_real_artistic_finishes():
    assert NEW_STYLE_SPECS["Chrome Nightmare"].finish == "albumart"
    assert NEW_STYLE_SPECS["Neon Ruin"].finish == "glitchcollapse"
    for name in ("Chrome Nightmare", "Neon Ruin", "Dead Channel", "Pastel Nightmare"):
        assert name in artistic.ARTISTIC_STYLE_PACKS


def test_controlnet_off_removes_structural_pressure():
    params = product.aggressive_render_parameters("Signal Rupture", False)
    assert params["controlnet_enabled"] is False
    assert params["control_weight"] == 0.0
    assert params["guidance_end"] == 0.0


def test_preferences_normalize_round_trip_and_recover(tmp_path: Path):
    prefs = product.normalize_preferences({"style": "missing", "controlnet": 0, "steps": 999})
    assert prefs == {"style": product.DEFAULT_PROCESS, "controlnet": False, "steps": product.MAX_STEPS}

    target = tmp_path / "prefs.json"
    product.save_preferences({"style": "Toxic Xerox", "controlnet": False, "steps": 19}, target)
    assert product.load_preferences(target) == {"style": "Toxic Xerox", "controlnet": False, "steps": 19}
    target.write_text("{broken", encoding="utf-8")
    assert product.load_preferences(target) == {
        "style": product.DEFAULT_PROCESS, "controlnet": True, "steps": product.DEFAULT_STEPS,
    }


def test_style_filter_searches_name_metadata_and_sequence_description():
    assert product.filter_processes("xerox") == ["Toxic Xerox"]
    assert any(name in simple.SEQUENCE_PROCESSES for name in product.filter_processes("shot progression"))
    assert len(product.filter_processes("experimental")) >= 5


def test_primary_action_is_gated_by_real_source(tmp_path: Path):
    assert product.primary_action_state("", False) == ("CHOOSE A VIDEO FIRST", "disabled")
    missing = tmp_path / "missing.mp4"
    assert product.primary_action_state(str(missing), False) == ("SOURCE MISSING", "disabled")
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"x")
    assert product.primary_action_state(str(source), False) == ("PROCESS VIDEO", "normal")
    assert product.primary_action_state(str(source), True) == ("PROCESSING…", "disabled")


def test_public_surface_and_live_presence_contract():
    shell_source = inspect.getsource(product.ComicFrameStudioApp._install_simple_shell)
    busy_source = inspect.getsource(product.ComicFrameStudioApp._simple_set_busy)
    progress_source = inspect.getsource(product.ComicFrameStudioApp._presence_progress_changed)
    assert "simple_controlnet_toggle" in shell_source
    assert "simple_steps_scale" in shell_source
    assert "simple_filter_entry" in shell_source
    assert "COPY PATH" in shell_source
    assert "AGGRO" not in shell_source
    assert "_presence_tick" in busy_source
    assert "LIVE_PREVIEW_EVERY" in progress_source
    assert product.MIN_STEPS == 12 and product.DEFAULT_STEPS == 24 and product.MAX_STEPS == 36
    assert product.PRODUCT_VERSION == "3.5" and STYLE_LIBRARY_VERSION == "3.5"
