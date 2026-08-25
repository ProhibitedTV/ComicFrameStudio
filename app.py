#!/usr/bin/env python3
"""Stable ComicFrame Studio entrypoint."""
from comicframe_app import ComicFrameStudioApp as BaseComicFrameStudioApp
from comicframe_controlnet import DirectControlNetProbeMixin
from comicframe_controlnet_compat import ControlNetV3CompatMixin
from comicframe_preflight import ControlNetPreflightMixin
from comicframe_styles import StylePackMixin
from comicframe_video_lock import ControlNetFirstVideoMixin


class ComicFrameStudioApp(
    ControlNetV3CompatMixin,
    ControlNetPreflightMixin,
    ControlNetFirstVideoMixin,
    StylePackMixin,
    DirectControlNetProbeMixin,
    BaseComicFrameStudioApp,
):
    """Canonical runtime with ControlNet-first continuity and pipeline-aware styles."""


def main():
    ComicFrameStudioApp().mainloop()


if __name__ == "__main__":
    main()
