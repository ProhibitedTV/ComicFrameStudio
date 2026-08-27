from __future__ import annotations

import app
import comicframe_product as product
import comicframe_resilience as resilience
import comicframe_simple as simple


def test_stable_entrypoint_installs_resilience_boundary():
    assert product.ComicFrameStudioApp is resilience.ComicFrameStudioApp
    assert app.ComicFrameStudioApp is resilience.ComicFrameStudioApp
    assert issubclass(resilience.ComicFrameStudioApp, resilience._BaseComicFrameStudioApp)
    assert app.main.__module__ == "comicframe_product"


def test_interrupted_connection_message_is_resume_safe():
    title, detail = simple.friendly_error_text(
        RuntimeError(
            "Stable Diffusion connection was interrupted during rendering and did not recover inside the retry window."
        )
    )
    assert "interrupted" in title.lower()
    assert "preserved" in detail.lower()
    assert "resume" in detail.lower()
    assert "start over" in detail.lower()


def test_normal_startup_connection_error_keeps_existing_guidance():
    title, detail = simple.friendly_error_text(ConnectionError("connection refused"))
    assert title == "Stable Diffusion WebUI is not connected"
    assert "Start Forge/A1111" in detail


def test_recovery_delays_are_bounded_and_back_off():
    assert resilience.RECOVERY_DELAYS == tuple(sorted(resilience.RECOVERY_DELAYS))
    assert sum(resilience.RECOVERY_DELAYS) <= 120
    assert resilience.RECOVERY_DELAYS[0] >= 1
