"""Small, Tk-independent boundary for real first-frame rendering experiments.

The engine still renders the image. This module captures public choices,
extracts one lossless source frame, and presents the actual result beside it.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw, ImageOps

from comicframe_hardening import load_json, runtime_source_key
from comicframe_media import (
    FULL_FINGERPRINT_ALGO,
    atomic_bytes_write,
    atomic_json_write,
    ensure_project_owned,
    full_file_sha256,
    safe_reset_generated_state,
    validate_png,
)


@dataclass(frozen=True)
class RenderRequest:
    source: Path
    project: Path
    look: str
    controlnet: bool
    steps: int
    preview: bool = False

    @property
    def engine_project(self) -> Path:
        return (
            self.project / "previews" / "first_frame" if self.preview else self.project
        )


def extract_preview_frame(
    request: RenderRequest, paths: dict, run: Callable, probe: Callable, stop_event
) -> dict:
    """Decode exactly one frame, retaining ownership and exact source identity."""
    if stop_event.is_set():
        raise InterruptedError("Preview cancelled")
    ensure_project_owned(request.project)
    root = request.engine_project
    if root.is_symlink() or root.parent.is_symlink():
        raise RuntimeError("Preview project must not be a symlink.")
    ensure_project_owned(root)
    if Path(paths["root"]).resolve() != root.resolve():
        raise RuntimeError("Preview paths do not match the captured render request.")
    before = runtime_source_key(request.source)
    fingerprint = full_file_sha256(request.source)
    old = load_json(paths["meta"])
    if old and old.get("source_fingerprint") != fingerprint:
        safe_reset_generated_state(root)
    for name in ("frames", "styled", "test"):
        Path(paths[name]).mkdir(parents=True, exist_ok=True)
    info = dict(probe(request.source))
    target = Path(paths["frames"]) / "frame_000001.png"
    valid, _reason = validate_png(target)
    if not valid or old.get("source_fingerprint") != fingerprint:
        temp = target.with_name("first_frame.part.png")
        try:
            run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(request.source),
                    "-map",
                    "0:v:0",
                    "-frames:v",
                    "1",
                    str(temp),
                ]
            )
            valid, reason = validate_png(temp)
            if not valid:
                raise RuntimeError(
                    f"Preview extraction produced an invalid PNG: {reason}"
                )
            if stop_event.is_set():
                raise InterruptedError("Preview cancelled")
            temp.replace(target)
        finally:
            temp.unlink(missing_ok=True)
    if runtime_source_key(request.source) != before:
        safe_reset_generated_state(root)
        raise RuntimeError(
            "Source video changed during preview extraction; retry with a stable source."
        )
    with Image.open(target) as frame:
        info["width"], info["height"] = frame.size
    info.update(
        {
            "frame_count": 1,
            "source_path": str(request.source),
            "source_fingerprint": fingerprint,
            "source_fingerprint_algo": FULL_FINGERPRINT_ALGO,
            "source_bytes": before[1],
            "source_mtime_ns": before[2],
            "preview": "first-frame-only",
        }
    )
    atomic_json_write(paths["meta"], info)
    return info


def make_preview_comparison(source: Path, styled: Path, target: Path) -> Path:
    """Label the source and actual diffusion output; no surrogate filter."""
    sheet = Image.new("RGB", (820, 300), (16, 17, 22))
    draw = ImageDraw.Draw(sheet)
    for column, (path, label) in enumerate(
        ((source, "ORIGINAL"), (styled, "STYLIZED - DIFFUSION"))
    ):
        with Image.open(path) as opened:
            image = ImageOps.contain(
                opened.convert("RGB"), (402, 260), Image.Resampling.LANCZOS
            )
        x = column * 410 + (410 - image.width) // 2
        sheet.paste(image, (x, 32 + (260 - image.height) // 2))
        draw.text((column * 410 + 10, 10), label, fill=(238, 241, 247))
    buffer = BytesIO()
    sheet.save(buffer, format="PNG")
    atomic_bytes_write(target, buffer.getvalue())
    return target
