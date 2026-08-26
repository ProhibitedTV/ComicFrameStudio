#!/usr/bin/env python3
"""Project/source usability hotfixes for ComicFrame Studio v2.9.2.

The stability audit correctly became conservative about project ownership, but
v2.9.1 still had one lifecycle self-conflict: the legacy UI wrote
``_source_preview.jpg`` into the project directory *before* ownership was
established. The ownership guard then rejected ComicFrame's own preview file.

This boundary keeps source previews outside project storage, recovers the one
safe legacy case created by that bug, and makes ffprobe probing tolerant of
builds that do not accept the richest ``-show_entries`` expression.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

from comicframe_media import (
    GENERATED_DIRS,
    GENERATED_FILES,
    MEDIA_VERSION,
    PROJECT_MARKER,
    PROJECT_PRODUCT,
    atomic_json_write,
    choose_fps_expression,
)
from comicframe_stability import ComicFrameStudioApp as StabilityComicFrameStudioApp


USABILITY_VERSION = "2.9.2"
LEGACY_SOURCE_PREVIEW = "_source_preview.jpg"


def default_project_path_for_video(video: Path) -> Path:
    """Return the project path created by the normal Browse Video workflow."""
    video = Path(video).expanduser().resolve()
    return video.parent / f"{video.stem}_comicframe"


def source_preview_cache_path(video: Path, temp_root: Path | None = None) -> Path:
    """Return a stable UI-preview path that can never claim/dirty a project."""
    video = Path(video).expanduser().resolve()
    root = Path(temp_root) if temp_root is not None else Path(tempfile.gettempdir()) / "ComicFrameStudio"
    key = hashlib.sha256(str(video).encode("utf-8", errors="replace")).hexdigest()[:20]
    return root / f"source_preview_{key}.jpg"


def recover_preview_only_project(root: Path, video: Path) -> bool:
    """Claim only the exact auto-project shape created by the v2.9.1 preview bug.

    Safety remains conservative. Recovery is allowed only when:
    * the project path is exactly ``<video parent>/<video stem>_comicframe``;
    * no ownership marker exists yet;
    * the only reserved/generated path present is the old source preview; and
    * that preview is a regular file, not a symlink.

    Custom generic folders still go through the normal strict ownership guard.
    """
    root = Path(root).expanduser().resolve()
    video = Path(video).expanduser().resolve()
    if root != default_project_path_for_video(video).resolve():
        return False
    if (root / PROJECT_MARKER).exists():
        return False
    preview = root / LEGACY_SOURCE_PREVIEW
    if not preview.exists() or not preview.is_file() or preview.is_symlink():
        return False

    collisions = {
        name
        for name in (*GENERATED_DIRS, *GENERATED_FILES)
        if (root / name).exists()
    }
    if collisions != {LEGACY_SOURCE_PREVIEW}:
        return False

    marker = {
        "product": PROJECT_PRODUCT,
        "version": MEDIA_VERSION,
        "project_id": uuid.uuid4().hex,
        "migrated_legacy": True,
        "recovered_preview_only": True,
    }
    atomic_json_write(root / PROJECT_MARKER, marker)
    return True


def parse_video_probe(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize rich, portable, or full ffprobe JSON into ComicFrame metadata."""
    streams = list((data or {}).get("streams") or [])
    if not streams:
        raise RuntimeError("ffprobe found no video stream in the selected source.")
    stream = streams[0]
    coded_width = int(stream.get("width") or 0)
    coded_height = int(stream.get("height") or 0)
    if coded_width <= 0 or coded_height <= 0:
        raise RuntimeError("ffprobe returned invalid video dimensions.")

    fps_expr, fps = choose_fps_expression(stream.get("avg_frame_rate"), stream.get("r_frame_rate"))
    try:
        duration = max(0.0, float(((data or {}).get("format") or {}).get("duration") or 0.0))
    except Exception:
        duration = 0.0

    rotation = 0
    try:
        rotation = int(round(float((stream.get("tags") or {}).get("rotate") or 0)))
    except Exception:
        rotation = 0
    for side in stream.get("side_data_list") or []:
        if isinstance(side, dict) and side.get("rotation") is not None:
            try:
                rotation = int(round(float(side.get("rotation") or 0)))
            except Exception:
                pass

    return {
        "width": coded_width,
        "height": coded_height,
        "coded_width": coded_width,
        "coded_height": coded_height,
        "rotation": rotation,
        "fps": fps,
        "fps_expr": fps_expr,
        "duration": duration,
        "nb_frames": stream.get("nb_frames"),
    }


class ComicFrameStudioApp(StabilityComicFrameStudioApp):
    """v2.9.1 renderer with friendlier source/project lifecycle behavior."""

    def __init__(self):
        super().__init__()
        self.title("ComicFrame Studio 2.9.2 · Project / Source Usability")

    # ---------- UI source preview ----------

    def _make_source_preview(self):
        video_text = str(self.video_var.get() or "").strip()
        if not video_text:
            return
        video = Path(video_text).expanduser().resolve()
        if not video.exists():
            self._log(f"Source preview skipped: file does not exist: {video}")
            return

        preview = source_preview_cache_path(video)
        preview.parent.mkdir(parents=True, exist_ok=True)
        command = [
            "ffmpeg", "-y", "-loglevel", "error", "-ss", "0", "-i", str(video),
            "-frames:v", "1", "-q:v", "2", str(preview),
        ]
        try:
            completed = subprocess.run(command, text=True, capture_output=True, check=False)
            if completed.returncode != 0:
                detail = (completed.stderr or completed.stdout or "unknown ffmpeg error").strip()
                self._log(f"Source preview unavailable (rendering can still continue): {detail[:700]}")
                try:
                    self.after(0, lambda: self.source_preview_status.set("Preview unavailable"))
                except Exception:
                    pass
                return

            def apply_preview() -> None:
                self._show_image(preview, self.source_preview, "source")
                self.source_preview_status.set(video.name)

            self.after(0, apply_preview)
        except Exception as exc:
            self._log(f"Source preview unavailable (rendering can still continue): {exc}")

    # ---------- v2.9.1 stale-preview recovery ----------

    def _extract_frames(self):
        video_text = str(self.video_var.get() or "").strip()
        if video_text:
            video = Path(video_text).expanduser().resolve()
            try:
                root = self.project_paths()["root"]
                if recover_preview_only_project(root, video):
                    self._log(
                        "Recovered the auto-created ComicFrame project from the v2.9.1 source-preview ownership bug."
                    )
            except Exception as exc:
                # Recovery is convenience only. The canonical ownership guard is
                # still authoritative and will report a precise error if needed.
                self._log(f"Project recovery check skipped: {exc}")
        return super()._extract_frames()

    # ---------- Resilient ffprobe ----------

    def _probe_video(self, video):
        self._check_external()
        video = Path(video).expanduser().resolve()
        attempts = [
            (
                "rich",
                [
                    "-show_entries",
                    "stream=width,height,r_frame_rate,avg_frame_rate,nb_frames:stream_tags=rotate:stream_side_data=rotation:format=duration",
                ],
            ),
            (
                "portable",
                [
                    "-show_entries",
                    "stream=width,height,r_frame_rate,avg_frame_rate,nb_frames:stream_tags=rotate:format=duration",
                ],
            ),
            ("full", ["-show_streams", "-show_format"]),
        ]
        failures: list[str] = []

        for index, (label, extra) in enumerate(attempts):
            command = [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                *extra, "-of", "json", str(video),
            ]
            self._log("$ " + " ".join(str(part) for part in command))
            try:
                completed = subprocess.run(command, text=True, capture_output=True, check=False)
            except Exception as exc:
                failures.append(f"{label}: could not launch ffprobe: {exc}")
                continue

            if completed.returncode != 0:
                detail = (completed.stderr or completed.stdout or f"exit code {completed.returncode}").strip()
                failures.append(f"{label}: {detail[:900]}")
                if index < len(attempts) - 1:
                    self._log(f"ffprobe {label} query was rejected; trying a more portable probe.")
                continue

            try:
                data = json.loads(completed.stdout or "{}")
                info = parse_video_probe(data if isinstance(data, dict) else {})
                if index:
                    self._log(f"Source probe recovered with the {label} ffprobe query.")
                return info
            except Exception as exc:
                failures.append(f"{label}: invalid probe response: {exc}")
                if index < len(attempts) - 1:
                    self._log(f"ffprobe {label} response was incomplete; trying a more portable probe.")

        detail = " | ".join(failures[-3:]) or "ffprobe returned no usable diagnostic."
        raise RuntimeError(
            "ComicFrame could not read the selected video. It may be damaged, locked by another program, or unsupported by the installed FFmpeg build. "
            f"Source: {video}. ffprobe details: {detail}"
        )


def main():
    ComicFrameStudioApp().mainloop()


if __name__ == "__main__":
    main()
