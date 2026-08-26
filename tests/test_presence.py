from __future__ import annotations

import comicframe_presence as presence


def test_render_progress_parser_reads_completed_frame_label():
    assert presence.parse_render_progress("34/641: frame_000034.png") == (
        34,
        641,
        "frame_000034.png",
        34,
    )
    assert presence.parse_render_progress("not rendering") is None
    assert presence.parse_render_progress("642/641: frame_000642.png") is None


def test_elapsed_clock_is_visibly_alive_for_long_jobs():
    assert presence.format_elapsed(0) == "00:00 elapsed"
    assert presence.format_elapsed(67) == "01:07 elapsed"
    assert presence.format_elapsed(3661) == "1:01:01 elapsed"


def test_live_preview_throttle_shows_first_then_every_fifth_frame():
    assert presence.should_refresh_live_preview(1, None)
    assert not presence.should_refresh_live_preview(2, 1)
    assert not presence.should_refresh_live_preview(5, 1)
    assert presence.should_refresh_live_preview(6, 1)
    assert not presence.should_refresh_live_preview(6, 6)
    assert presence.should_refresh_live_preview(11, 6)


def test_friendly_activity_turns_renderer_labels_into_operator_feedback():
    assert presence.friendly_activity("34/641: frame_000034.png") == (
        "Rendering frame 34 · 34 of 641 complete"
    )
    assert presence.friendly_activity("Extracting source frames…") == "Preparing source frames"
    assert presence.friendly_activity("Assembling final video…") == "Building final video"
    assert presence.friendly_activity("Restoring audio…") == "Restoring source audio"


def test_presence_profile_metadata_is_ui_only_for_cache_compatibility():
    old = {
        "app_version": "3.1",
        "checkpoint": "same",
        "sampler": "same",
        "simple_shell": {"interface_version": "3.1"},
    }
    new = {
        "app_version": "3.2",
        "checkpoint": "same",
        "sampler": "same",
        "simple_shell": {
            "interface_version": "3.1",
            "presence_version": "3.2",
            "live_preview_every": 5,
        },
    }
    assert presence.ComicFrameStudioApp._profile_without_director(old) == presence.ComicFrameStudioApp._profile_without_director(new)


def test_presence_layer_does_not_replace_the_render_engine():
    names = [cls.__name__ for cls in presence.ComicFrameStudioApp.__mro__]
    # This is an outer presentation class over the already-audited product shell.
    assert names[0] == "ComicFrameStudioApp"
    assert "InterfaceApp" not in names
    assert "RenderIntelligenceMixin" in names
    assert "ReferenceLockMixin" in names
