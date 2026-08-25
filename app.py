#!/usr/bin/env python3
"""Stable ComicFrame Studio entrypoint."""
from comicframe_app import ComicFrameStudioApp as BaseComicFrameStudioApp
from comicframe_artistic import ArtisticExpansionMixin
from comicframe_controlnet import DirectControlNetProbeMixin
from comicframe_controlnet_compat import ControlNetV3CompatMixin
from comicframe_optical_flow import OpticalFlowTemporalMixin
from comicframe_preflight import ControlNetPreflightMixin
from comicframe_shot_memory import ShotMemoryMixin
from comicframe_styles import StylePackMixin
from comicframe_video_lock import ControlNetFirstVideoMixin


class ComicFrameStudioApp(
    ControlNetV3CompatMixin,
    ShotMemoryMixin,
    OpticalFlowTemporalMixin,
    ArtisticExpansionMixin,
    ControlNetPreflightMixin,
    ControlNetFirstVideoMixin,
    StylePackMixin,
    DirectControlNetProbeMixin,
    BaseComicFrameStudioApp,
):
    """Canonical runtime with shot memory, optical flow, ControlNet and artistic styles."""

    def __init__(self):
        super().__init__()
        self.title("ComicFrame Studio 2.0 · Shot Memory + Optical Flow")


def main():
    ComicFrameStudioApp().mainloop()


if __name__ == "__main__":
    main()
