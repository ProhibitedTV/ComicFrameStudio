#!/usr/bin/env python3
"""Stable ComicFrame Studio entrypoint."""
from comicframe_app import ComicFrameStudioApp as BaseComicFrameStudioApp
from comicframe_controlnet import DirectControlNetProbeMixin
from comicframe_preflight import ControlNetPreflightMixin
from comicframe_video_lock import ControlNetFirstVideoMixin


class ComicFrameStudioApp(
    ControlNetPreflightMixin,
    ControlNetFirstVideoMixin,
    DirectControlNetProbeMixin,
    BaseComicFrameStudioApp,
):
    """Canonical runtime with ControlNet-first, motion-aware video continuity."""


def main():
    ComicFrameStudioApp().mainloop()


if __name__ == "__main__":
    main()
