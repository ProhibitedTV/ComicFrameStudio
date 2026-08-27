#!/usr/bin/env python3
"""Long-render backend resilience boundary for ComicFrame Studio.

This module is deliberately thin and loaded by ``app.py`` before the stable
entrypoint is re-exported. It leaves the existing renderer intact while adding
long-lived recovery for transient Forge/A1111 failures, a much larger img2img
read timeout for legitimately slow frames, backend-idle detection, and runtime
rehydration after a WebUI restart.

The policy is intentionally biased toward unattended renders: a transient local
backend problem should cost time, not a 99-hour job. Completed PNG frames remain
the durable checkpoint and are never deleted by this layer.
"""
from __future__ import annotations

import os
import re
import time
from typing import Any, Iterator

import requests

import comicframe_product as product
import comicframe_simple as simple
import comicframe_studio as legacy_transport


RESILIENCE_VERSION = "3.6.2"
RECOVERY_DELAYS = (5.0, 15.0, 30.0, 60.0)
RECOVERY_POLL_SECONDS = 60.0
FRAME_CONNECT_TIMEOUT_SECONDS = 30.0


def _hours_from_env(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.environ.get(name, default))
    except Exception:
        value = default
    return max(minimum, min(maximum, value))


# A slow SDXL + ControlNet frame can legitimately exceed the old one-hour HTTP
# read timeout. Six hours is deliberately generous; connection establishment is
# still capped at 30 seconds so a dead backend is detected quickly.
FRAME_READ_TIMEOUT_SECONDS = _hours_from_env(
    "COMICFRAME_FRAME_READ_TIMEOUT_HOURS", 6.0, 1.0, 24.0
) * 3600.0

# Once a genuine transport failure is detected, keep the app alive for up to a
# day by default. This covers overnight restarts, Windows sleep/wake, Forge
# reloads and a backend that is manually restarted hours later. Users can tune
# this without editing code.
BACKEND_RECOVERY_MAX_SECONDS = _hours_from_env(
    "COMICFRAME_BACKEND_RECOVERY_HOURS", 24.0, 0.25, 168.0
) * 3600.0

_BaseComicFrameStudioApp = product.ComicFrameStudioApp
_base_friendly_error_text = simple.friendly_error_text


class _RequestsProxy:
    """Only extend the legacy img2img request timeout.

    Rebinding ``comicframe_studio.requests`` avoids mutating the process-wide
    requests module used by the rest of ComicFrame. Every non-img2img call is
    forwarded unchanged.
    """

    def __init__(self, delegate):
        self._delegate = delegate

    def __getattr__(self, name):
        return getattr(self._delegate, name)

    def post(self, url, *args, **kwargs):
        if str(url or "").split("?", 1)[0].rstrip("/").endswith("/sdapi/v1/img2img"):
            kwargs["timeout"] = (FRAME_CONNECT_TIMEOUT_SECONDS, FRAME_READ_TIMEOUT_SECONDS)
        return self._delegate.post(url, *args, **kwargs)


# The actual network POST lives in the original v1 transport module at the
# bottom of the renderer MRO. Replace only that module's requests binding.
if not isinstance(legacy_transport.requests, _RequestsProxy):
    legacy_transport.requests = _RequestsProxy(legacy_transport.requests)


def recovery_waits(max_seconds: float = BACKEND_RECOVERY_MAX_SECONDS) -> Iterator[float]:
    """Yield bounded backoff intervals, then poll once per minute."""
    remaining = max(0.0, float(max_seconds))
    for delay in RECOVERY_DELAYS:
        if remaining <= 0:
            return
        actual = min(float(delay), remaining)
        yield actual
        remaining -= actual
    while remaining > 0:
        actual = min(RECOVERY_POLL_SECONDS, remaining)
        yield actual
        remaining -= actual


def friendly_error_text(exc: Exception | str) -> tuple[str, str]:
    """Keep transient long-render disconnects distinct from startup failures."""
    text = str(exc)
    if "stable diffusion connection was interrupted during rendering" in text.lower():
        return (
            "Stable Diffusion connection was interrupted",
            "Forge/A1111 stopped responding during the render. ComicFrame preserved completed frames. "
            "Restart or reconnect the WebUI, then process the same video with the same look again; "
            "ComicFrame will resume from the cached frames instead of starting over.",
        )
    return _base_friendly_error_text(exc)


class ComicFrameStudioApp(_BaseComicFrameStudioApp):
    """Keep long renders alive through recoverable local-backend failures."""

    def __init__(self):
        super().__init__()
        self.title(f"ComicFrame Studio {RESILIENCE_VERSION}")

    @staticmethod
    def _resilience_is_transient(exc: Exception) -> bool:
        """Classify transport/server failures without masking OOM/NaN errors."""
        low = str(exc).lower()
        if any(token in low for token in (
            "cuda out of memory", "outofmemory", "out of vram",
            "nansexception", "nan was produced",
        )):
            return False
        try:
            if isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
                return True
        except Exception:
            pass
        if ComicFrameStudioApp._audit2_transient_render_error(exc):
            return True
        if any(token in low for token in (
            "incomplete read", "chunkedencodingerror", "connection broken",
            "remote disconnected", "expecting value", "json decode",
        )):
            return True
        match = re.search(r"\bhttp\s+(\d{3})\b", low)
        if match:
            status = int(match.group(1))
            return status in {408, 425, 429} or status >= 500
        return False

    @staticmethod
    def _resilience_backend_ready(api_url: str) -> tuple[bool, str]:
        """Require a healthy *and idle* backend before resubmitting a frame.

        A dropped client connection does not guarantee Forge stopped generating.
        Waiting for /progress to go idle prevents an accidental duplicate request
        from competing with the orphaned generation for VRAM.
        """
        url = str(api_url or "").strip().rstrip("/")
        if not url:
            return False, "API URL is empty"
        try:
            response = requests.get(f"{url}/sdapi/v1/options", timeout=10)
            if not response.ok:
                return False, f"HTTP {response.status_code}"
        except Exception as exc:
            return False, str(exc)

        try:
            progress_r = requests.get(
                f"{url}/sdapi/v1/progress?skip_current_image=true",
                timeout=10,
            )
            if progress_r.ok:
                payload = progress_r.json() or {}
                progress = float(payload.get("progress") or 0.0)
                state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
                job_count = int(state.get("job_count") or 0)
                sampling_step = int(state.get("sampling_step") or 0)
                if progress > 0.001 or job_count > 0 or sampling_step > 0:
                    return False, f"backend busy · progress={progress:.1%} jobs={job_count}"
        except Exception:
            # /progress is advisory. Older/variant WebUIs may not expose it; the
            # successful /options request is still enough to establish health.
            pass
        return True, f"HTTP {response.status_code} · idle"

    def _resilience_rehydrate_backend(self) -> None:
        """Restore runtime selections after Forge/A1111 has restarted."""
        self._log("Backend reachable again; refreshing WebUI capabilities and checkpoint state.")
        self._sync_webui()
        self._ensure_checkpoint_loaded()
        enforce = getattr(self, "_enforce_public_controlnet_choice", None)
        if callable(enforce):
            enforce()

    def _render_one(self, frame_path, out_path, settings, width, height, frame_number):
        """Add a long recovery window around the audited per-frame retry layer."""
        try:
            return super()._render_one(frame_path, out_path, settings, width, height, frame_number)
        except Exception as exc:
            if self.stop_event.is_set() or not self._resilience_is_transient(exc):
                raise
            last_error: Exception = exc

        recovery_started = time.monotonic()
        last_status_log = -300.0
        for delay in recovery_waits():
            elapsed = time.monotonic() - recovery_started
            if elapsed - last_status_log >= 300.0:
                self._log(
                    f"Stable Diffusion transport interrupted on frame {frame_number}; completed frames are preserved. "
                    f"Recovery mode active for up to {BACKEND_RECOVERY_MAX_SECONDS / 3600.0:.1f}h."
                )
                last_status_log = elapsed

            if self.stop_event.wait(delay):
                raise last_error

            ready, detail = self._resilience_backend_ready(settings.api_url)
            if not ready:
                # Busy is often good news: the request may have disconnected
                # while Forge kept rendering. Do not submit a competing frame.
                continue

            try:
                self._resilience_rehydrate_backend()
            except Exception as refresh_exc:
                if not self._resilience_is_transient(refresh_exc):
                    self._log(f"Backend refresh warning after reconnect: {refresh_exc}")
                last_error = refresh_exc
                continue

            self._log(f"Backend recovered ({detail}); retrying frame {frame_number} without touching completed frames.")
            try:
                return super()._render_one(frame_path, out_path, settings, width, height, frame_number)
            except Exception as exc:
                if self.stop_event.is_set() or not self._resilience_is_transient(exc):
                    raise
                last_error = exc

        raise RuntimeError(
            "Stable Diffusion connection was interrupted during rendering and did not recover inside the retry window. "
            "Completed frames were preserved; reconnect Forge/A1111 and process the same video/look again to resume. "
            f"Last backend error: {last_error}"
        ) from last_error

    def _render_profile(self) -> dict[str, Any]:
        profile = super()._render_profile()
        profile["app_version"] = RESILIENCE_VERSION
        profile["backend_resilience"] = {
            "version": RESILIENCE_VERSION,
            "recovery_delays_seconds": list(RECOVERY_DELAYS),
            "recovery_poll_seconds": RECOVERY_POLL_SECONDS,
            "max_recovery_seconds": BACKEND_RECOVERY_MAX_SECONDS,
            "frame_connect_timeout_seconds": FRAME_CONNECT_TIMEOUT_SECONDS,
            "frame_read_timeout_seconds": FRAME_READ_TIMEOUT_SECONDS,
            "wait_for_backend_idle": True,
            "rehydrate_after_restart": True,
            "completed_frames_preserved": True,
        }
        return profile


# ``comicframe_simple`` imported friendly_error_text by name, so replace that
# module-level alias. Also replace the product class global: product.main()
# resolves ComicFrameStudioApp at call time, preserving the established public
# entrypoint and existing interface-contract tests.
simple.friendly_error_text = friendly_error_text
product.ComicFrameStudioApp = ComicFrameStudioApp


__all__ = [
    "ComicFrameStudioApp",
    "RESILIENCE_VERSION",
    "RECOVERY_DELAYS",
    "RECOVERY_POLL_SECONDS",
    "BACKEND_RECOVERY_MAX_SECONDS",
    "FRAME_CONNECT_TIMEOUT_SECONDS",
    "FRAME_READ_TIMEOUT_SECONDS",
    "recovery_waits",
    "friendly_error_text",
]
