#!/usr/bin/env python3
"""Stable ComicFrame Studio entrypoint."""
import json

from comicframe_app import ComicFrameStudioApp as BaseComicFrameStudioApp
from comicframe_artistic import ArtisticExpansionMixin
from comicframe_autopilot import AutoPilotMixin
from comicframe_controlnet import DirectControlNetProbeMixin
from comicframe_controlnet_compat import ControlNetV3CompatMixin
from comicframe_director import EasyShotDirectorMixin
from comicframe_efficiency import RenderIntelligenceMixin
from comicframe_optical_flow import OpticalFlowTemporalMixin
from comicframe_preflight import ControlNetPreflightMixin
from comicframe_reference_lock import ReferenceLockMixin
from comicframe_shot_memory import ShotMemoryMixin
from comicframe_styles import StylePackMixin
from comicframe_subjects import SubjectLibraryMixin
from comicframe_video_lock import ControlNetFirstVideoMixin
from comicframe_webui_contract import WebUIContractMixin
from comicframe_workspace import ProjectWorkspaceMixin


class ComicFrameStudioApp(
    ControlNetV3CompatMixin,
    AutoPilotMixin,
    SubjectLibraryMixin,
    RenderIntelligenceMixin,
    ProjectWorkspaceMixin,
    ReferenceLockMixin,
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
    """Canonical runtime with one-click AutoPilot over the full v2 engine."""

    def __init__(self):
        super().__init__()
        self.title("ComicFrame Studio 2.7 · AutoPilot")
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

    @staticmethod
    def _profile_without_director(profile: dict) -> dict:
        """Let timeline dependencies govern selective render invalidation."""
        normalized = json.loads(json.dumps(profile))
        normalized.pop("shot_director", None)
        normalized.pop("reference_lock", None)
        normalized.pop("workspace", None)
        normalized.pop("render_intelligence", None)
        normalized.pop("subject_library", None)
        normalized.pop("autopilot", None)
        # v2.7 reuses v2.6 frames when the actual per-shot dependencies match.
        normalized.pop("app_version", None)
        return normalized

    def _render_profile(self) -> dict:
        profile = super()._render_profile()
        profile["app_version"] = "2.7"
        return profile


def main():
    ComicFrameStudioApp().mainloop()


if __name__ == "__main__":
    main()
