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


def _resume_profile(*, controlnet=True, steps=36, style_library="3.5", checkpoint="model-a"):
    return {
        "app_version": "3.5",
        "checkpoint": checkpoint,
        "sampler": "DPM++ 2M",
        "scheduler": "Automatic",
        "inference": "1024 long edge",
        "creative_controls": {
            "version": "3.5",
            "controlnet": controlnet,
            "steps": steps,
            "style_policy": "aggressive-by-default",
            "style_library": style_library,
        },
        "backend_resilience": {
            "version": "3.6.2",
            "frame_read_timeout_seconds": 21600,
        },
    }


def test_resume_profile_ignores_version_only_resilience_metadata():
    old = _resume_profile(style_library="3.5")
    old.pop("backend_resilience")
    new = _resume_profile(style_library="3.6")
    new["app_version"] = "3.6.3"
    new["creative_controls"]["version"] = "3.6.3"
    new["backend_resilience"]["version"] = "3.6.3"

    assert resilience.normalize_resume_profile(old) == resilience.normalize_resume_profile(new)
    assert resilience.ComicFrameStudioApp._profile_without_director(old) == resilience.ComicFrameStudioApp._profile_without_director(new)


def test_resume_profile_still_rejects_real_controlnet_or_step_changes():
    baseline = resilience.normalize_resume_profile(_resume_profile(controlnet=True, steps=36))
    no_controlnet = resilience.normalize_resume_profile(_resume_profile(controlnet=False, steps=36))
    fewer_steps = resilience.normalize_resume_profile(_resume_profile(controlnet=True, steps=24))
    assert baseline != no_controlnet
    assert baseline != fewer_steps


def test_resume_profile_still_rejects_checkpoint_changes():
    old = resilience.normalize_resume_profile(_resume_profile(checkpoint="model-a"))
    new = resilience.normalize_resume_profile(_resume_profile(checkpoint="model-b"))
    assert old != new
