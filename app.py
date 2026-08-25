#!/usr/bin/env python3
"""Stable ComicFrame Studio entrypoint."""
from comicframe_app import ComicFrameStudioApp as BaseComicFrameStudioApp
from comicframe_artistic import ArtisticExpansionMixin
from comicframe_controlnet import DirectControlNetProbeMixin
from comicframe_controlnet_compat import ControlNetV3CompatMixin
from comicframe_director import EasyShotDirectorMixin
from comicframe_optical_flow import OpticalFlowTemporalMixin
from comicframe_preflight import ControlNetPreflightMixin
from comicframe_shot_memory import ShotMemoryMixin
from comicframe_styles import StylePackMixin
from comicframe_video_lock import ControlNetFirstVideoMixin
from comicframe_webui_contract import WebUIContractMixin


class ComicFrameStudioApp(
    ControlNetV3CompatMixin,
    ShotMemoryMixin,
    EasyShotDirectorMixin,
    OpticalFlowTemporalMixin,
    ArtisticExpansionMixin,
    ControlNetPreflightMixin,
    ControlNetFirstVideoMixin,
    StylePackMixin,
    DirectControlNetProbeMixin,
    WebUIContractMixin,
    BaseComicFrameStudioApp,
):
    """Canonical runtime with easy shot direction over the hardened v2 continuity stack."""

    def __init__(self):
        super().__init__()
        self.title("ComicFrame Studio 2.2 · Easy Shot Director")
        # Easy Mode is intentionally the normal product surface. Clarify the
        # checked state without changing the Director's simple boolean contract.
        try:
            for child in self.director_card.winfo_children():
                for widget in child.winfo_children():
                    try:
                        if widget.cget("text") == "Show advanced controls":
                            widget.configure(text="Easy Mode · hide advanced controls")
                    except Exception:
                        pass
        except Exception:
            pass

    def _render_profile(self) -> dict:
        profile = super()._render_profile()
        # Historical mixins annotate their own generation while unwinding the
        # MRO. The canonical application boundary is authoritative for resume.
        profile["app_version"] = "2.2"
        return profile


def main():
    ComicFrameStudioApp().mainloop()


if __name__ == "__main__":
    main()
