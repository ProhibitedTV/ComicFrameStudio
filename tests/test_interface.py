from __future__ import annotations

import app
import comicframe_interface as interface
import comicframe_presence as presence
import comicframe_simple as simple


def test_stable_entrypoint_keeps_v31_interface_under_presence_shell():
    assert app.ComicFrameStudioApp is presence.ComicFrameStudioApp
    assert app.main.__module__ == "comicframe_presence"
    assert issubclass(app.ComicFrameStudioApp, interface.ComicFrameStudioApp)


def test_process_browser_has_unique_short_labels():
    rows = interface.process_rows()
    labels = [display for display, _canonical in rows]
    canonicals = [canonical for _display, canonical in rows]
    assert len(labels) == len(set(labels))
    assert canonicals == simple.simple_process_catalog()
    assert "Graphic Shock" in labels
    assert "Clean → Chaos" in labels
    assert "Signal Rupture" in labels


def test_process_browser_keeps_engine_diagnostics_hidden():
    rows = interface.process_rows()
    rendered = " ".join(display + " " + canonical for display, canonical in rows).lower()
    assert "diagnostic" not in rendered
    assert "controlnet test" not in rendered


def test_process_meta_is_human_facing_not_engine_facing():
    assert interface.process_meta("Clean → Chaos · sequence").startswith("SEQUENCE")
    meta = interface.process_meta("Signal Rupture")
    assert "EXPERIMENTAL" in meta
    assert "controlnet" not in meta.lower()
    assert "sampler" not in meta.lower()


def test_v31_profile_metadata_remains_cache_compatible():
    old = {
        "app_version": "3.0",
        "checkpoint": "same",
        "sampler": "same",
        "simple_shell": {"version": "3.0"},
    }
    new = {
        "app_version": "3.1",
        "checkpoint": "same",
        "sampler": "same",
        "simple_shell": {
            "version": "3.0",
            "interface_version": "3.1",
            "layout": "responsive preview + visible process browser",
        },
    }
    assert interface.ComicFrameStudioApp._profile_without_director(old) == interface.ComicFrameStudioApp._profile_without_director(new)


def test_display_name_removes_internal_suffix_noise():
    assert interface.process_display_name("Graphic Shock · maximum print") == "Graphic Shock"
    assert interface.process_display_name("Clean → Chaos · sequence") == "Clean → Chaos"
    assert interface.process_display_name("VHS Horror") == "VHS Horror"
