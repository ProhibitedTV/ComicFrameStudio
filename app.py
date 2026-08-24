#!/usr/bin/env python3
"""Stable ComicFrame Studio entrypoint."""
from comicframe_app import ComicFrameStudioApp as BaseComicFrameStudioApp
from comicframe_controlnet import DirectControlNetProbeMixin


class ComicFrameStudioApp(DirectControlNetProbeMixin, BaseComicFrameStudioApp):
    """Canonical runtime with robust ControlNet discovery."""


def main():
    ComicFrameStudioApp().mainloop()


if __name__ == "__main__":
    main()
