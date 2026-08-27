from __future__ import annotations

import requests

import app
import comicframe_product as product
import comicframe_resilience as resilience
import comicframe_simple as simple
import comicframe_studio as legacy_transport


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


def test_recovery_delays_back_off_then_poll_for_hours():
    assert resilience.RECOVERY_DELAYS == tuple(sorted(resilience.RECOVERY_DELAYS))
    assert resilience.RECOVERY_DELAYS[0] >= 1
    assert resilience.RECOVERY_POLL_SECONDS >= resilience.RECOVERY_DELAYS[-1]
    assert resilience.BACKEND_RECOVERY_MAX_SECONDS >= 6 * 3600
    waits = list(resilience.recovery_waits(230.0))
    assert waits[:4] == list(resilience.RECOVERY_DELAYS)
    assert sum(waits) == 230.0
    assert all(wait > 0 for wait in waits)


def test_img2img_transport_gets_multi_hour_read_timeout(monkeypatch):
    captured = {}

    class Delegate:
        def post(self, url, *args, **kwargs):
            captured.update(kwargs)
            return object()

    proxy = resilience._RequestsProxy(Delegate())
    proxy.post("http://127.0.0.1:7860/sdapi/v1/img2img", json={}, timeout=3600)
    assert captured["timeout"][0] == resilience.FRAME_CONNECT_TIMEOUT_SECONDS
    assert captured["timeout"][1] == resilience.FRAME_READ_TIMEOUT_SECONDS
    assert resilience.FRAME_READ_TIMEOUT_SECONDS >= 3600


def test_transport_proxy_is_scoped_to_legacy_renderer_module():
    assert isinstance(legacy_transport.requests, resilience._RequestsProxy)
    assert requests is not legacy_transport.requests


def test_transient_classifier_retries_network_failures_but_not_oom():
    assert resilience.ComicFrameStudioApp._resilience_is_transient(
        requests.exceptions.ReadTimeout("read timed out")
    )
    assert resilience.ComicFrameStudioApp._resilience_is_transient(
        RuntimeError("Stable Diffusion API HTTP 503: temporarily unavailable")
    )
    assert resilience.ComicFrameStudioApp._resilience_is_transient(
        RuntimeError("Stable Diffusion API HTTP 429: busy")
    )
    assert not resilience.ComicFrameStudioApp._resilience_is_transient(
        RuntimeError("HTTP 500 CUDA out of memory")
    )
