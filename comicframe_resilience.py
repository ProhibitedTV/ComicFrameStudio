#!/usr/bin/env python3
"""Long-render backend resilience boundary for ComicFrame Studio.

This module is deliberately thin and loaded by ``app.py`` before the stable
entrypoint is re-exported.  It leaves the existing renderer untouched while
adding a recovery window for transient Forge/A1111 disconnects and a truthful
resume-safe error message when the backend does not come back.
"""
from __future__ import annotations

from typing import Any

import requests

import comicframe_product as product
import comicframe_simple as simple


RESILIENCE_VERSION = "3.6.1"
RECOVERY_DELAYS = (5.0, 15.0, 30.0, 60.0)

_BaseComicFrameStudioApp = product.ComicFrameStudioApp
_base_friendly_error_text = simple.friendly_error_text


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
    """Recover long renders when the local Stable Diffusion API briefly disappears."""

    def __init__(self):
        super().__init__()
        self.title(f"ComicFrame Studio {RESILIENCE_VERSION}")

    @staticmethod
    def _resilience_backend_ready(api_url: str) -> tuple[bool, str]:
        url = str(api_url or "").strip().rstrip("/")
        if not url:
            return False, "API URL is empty"
        try:
            response = requests.get(f"{url}/sdapi/v1/options", timeout=10)
            if response.ok:
                return True, f"HTTP {response.status_code}"
            return False, f"HTTP {response.status_code}"
        except Exception as exc:
            return False, str(exc)

    def _render_one(self, frame_path, out_path, settings, width, height, frame_number):
        """Add a recovery window around the audited per-frame retry layer.

        v2.9 already performs three quick retries for transient failures.  That is
        good for a single reset, but an overnight render can outlive a brief WebUI
        restart, model reload, or local HTTP hiccup.  If those quick retries are
        exhausted, wait for the API to become healthy and resume the same frame.
        """
        try:
            return super()._render_one(frame_path, out_path, settings, width, height, frame_number)
        except Exception as exc:
            if self.stop_event.is_set() or not self._audit2_transient_render_error(exc):
                raise
            last_error: Exception = exc

        for delay in RECOVERY_DELAYS:
            self._log(
                f"Stable Diffusion connection interrupted on frame {frame_number}; "
                f"completed frames are preserved. Waiting {int(delay)}s for Forge/A1111 to recover."
            )
            if self.stop_event.wait(delay):
                raise last_error

            ready, detail = self._resilience_backend_ready(settings.api_url)
            if not ready:
                self._log(f"Backend still unavailable after {int(delay)}s wait: {detail}")
                continue

            self._log(f"Backend recovered ({detail}); resuming frame {frame_number}.")
            try:
                return super()._render_one(frame_path, out_path, settings, width, height, frame_number)
            except Exception as exc:
                if self.stop_event.is_set() or not self._audit2_transient_render_error(exc):
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
            "completed_frames_preserved": True,
        }
        return profile


# ``comicframe_simple`` imported friendly_error_text by name, so replace that
# module-level alias.  Also replace the product class global: product.main()
# resolves ComicFrameStudioApp at call time, preserving the established public
# entrypoint and existing interface-contract tests.
simple.friendly_error_text = friendly_error_text
product.ComicFrameStudioApp = ComicFrameStudioApp


__all__ = ["ComicFrameStudioApp", "RESILIENCE_VERSION", "RECOVERY_DELAYS", "friendly_error_text"]
