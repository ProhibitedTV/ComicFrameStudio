#!/usr/bin/env python3
"""Media/project integrity helpers for ComicFrame Studio v2.9.

These helpers are intentionally independent of Tk and the cooperative renderer MRO.
They provide exact source identity, project ownership, PNG validation, VFR timing,
and crash-safe file writes for the canonical application boundary.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import statistics
import tempfile
import uuid
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageChops, ImageOps, ImageStat

MEDIA_VERSION = "2.9-audit2"
FULL_FINGERPRINT_ALGO = "sha256-full-v1"
PROJECT_MARKER = ".comicframe_project.json"
PROJECT_PRODUCT = "ComicFrameStudio"
_FRAME_RE = re.compile(r"^frame_(\d{6,})\.png$")

GENERATED_DIRS = (
    "frames",
    "styled_frames",
    "test_frames",
    "shot_memory",
    "cache",
    "previews",
    "subjects",
    "director_preview_frames",
)
GENERATED_FILES = (
    "source_info.json",
    "comicframe_timeline.json",
    "comicframe_timeline.rendered.json",
    "comicframe_profile.json",
    "comicframe_test_profile.json",
    "render_settings.json",
    "styled_silent.mp4",
    "FINAL_STYLED.mp4",
    "DIRECTOR_PREVIEW.jpg",
    "_source_preview.jpg",
)


def _replace_temp(temp: Path, target: Path) -> None:
    try:
        os.replace(temp, target)
    finally:
        if temp.exists():
            temp.unlink(missing_ok=True)


def atomic_bytes_write(path: Path, data: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, delete=False)
    temp = Path(handle.name)
    try:
        with handle:
            handle.write(data)
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError:
                pass
        _replace_temp(temp, path)
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def atomic_text_write(path: Path, text: str) -> None:
    atomic_bytes_write(Path(path), text.encode("utf-8"))


def atomic_json_write(path: Path, data: dict[str, Any]) -> None:
    atomic_text_write(Path(path), json.dumps(data, indent=2))


def full_file_sha256(path: Path, chunk_bytes: int = 4 * 1024 * 1024) -> str:
    """Hash the complete source. Source identity must favor correctness over startup speed."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(max(64 * 1024, int(chunk_bytes))), b""):
            digest.update(chunk)
    return digest.hexdigest()


def frame_numbers(directory: Path) -> list[int]:
    out: list[int] = []
    directory = Path(directory)
    if not directory.exists():
        return out
    for path in directory.glob("frame_*.png"):
        match = _FRAME_RE.match(path.name)
        if match:
            out.append(int(match.group(1)))
    return sorted(out)


def frame_sequence_report(directory: Path, expected_count: int | None = None) -> dict[str, Any]:
    numbers = frame_numbers(directory)
    count = len(numbers)
    contiguous = bool(numbers) and numbers[0] == 1 and numbers[-1] == count and all(
        value == index for index, value in enumerate(numbers, 1)
    )
    missing: list[int] = []
    extras: list[int] = []
    valid = contiguous
    if expected_count is not None:
        expected_count = max(0, int(expected_count))
        valid = contiguous and count == expected_count
        if not valid:
            number_set = set(numbers)
            missing = [n for n in range(1, expected_count + 1) if n not in number_set][:20]
            extras = [n for n in numbers if n > expected_count][:20]
    return {
        "count": count,
        "first": numbers[0] if numbers else 0,
        "last": numbers[-1] if numbers else 0,
        "contiguous": contiguous,
        "expected_count": expected_count,
        "valid": bool(numbers) and valid,
        "missing": missing,
        "extras": extras,
    }


def validate_png(path: Path, expected_size: tuple[int, int] | None = None) -> tuple[bool, str]:
    path = Path(path)
    if path.is_symlink():
        return False, "symlink"
    if not path.exists():
        return False, "missing"
    if path.stat().st_size < 64:
        return False, "tiny"
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            size = image.size
            if expected_size is not None and size != expected_size:
                return False, f"size {size[0]}x{size[1]} != {expected_size[0]}x{expected_size[1]}"
            image.load()
        return True, "ok"
    except Exception as exc:
        return False, f"invalid PNG: {exc}"


def invalid_png_numbers(directory: Path, numbers: Iterable[int]) -> list[tuple[int, str]]:
    invalid: list[tuple[int, str]] = []
    for number in sorted({int(n) for n in numbers if int(n) > 0}):
        path = Path(directory) / f"frame_{number:06d}.png"
        if not path.exists() and not path.is_symlink():
            continue
        ok, reason = validate_png(path)
        if not ok:
            invalid.append((number, reason))
    return invalid


def representative_numbers(frame_count: int, samples: int = 5) -> list[int]:
    frame_count = max(0, int(frame_count))
    if frame_count <= 0:
        return []
    samples = max(1, min(int(samples), frame_count))
    if samples == 1:
        return [1]
    return sorted({1 + int(round(index * (frame_count - 1) / float(samples - 1))) for index in range(samples)})


def image_similarity(a: Path, b: Path, edge: int = 192) -> float:
    """Return deterministic 0..1 visual similarity for legacy source-cache verification."""
    with Image.open(a) as first, Image.open(b) as second:
        aa = ImageOps.contain(first.convert("L"), (edge, edge), Image.Resampling.BILINEAR)
        bb = ImageOps.contain(second.convert("L"), aa.size, Image.Resampling.BILINEAR)
        if bb.size != aa.size:
            bb = bb.resize(aa.size, Image.Resampling.BILINEAR)
        difference = ImageChops.difference(aa, bb)
        mean = float(ImageStat.Stat(difference).mean[0]) / 255.0
        return max(0.0, min(1.0, 1.0 - mean))


def display_dimensions_from_frame(frame_path: Path) -> tuple[int, int]:
    with Image.open(frame_path) as image:
        return int(image.width), int(image.height)


def choose_fps_expression(avg: Any, nominal: Any, default: str = "30/1") -> tuple[str, float]:
    """Choose the first finite positive ffprobe rate; 0/0 must never win."""
    for candidate in (avg, nominal, default):
        text = str(candidate or "").strip()
        if not text:
            continue
        try:
            if "/" in text:
                numerator, denominator = text.split("/", 1)
                value = float(numerator) / float(denominator)
            else:
                value = float(text)
            if value > 0 and value < 1000 and value == value:
                return text, value
        except Exception:
            continue
    return "30/1", 30.0


def frame_timing_from_probe(
    frames: list[dict[str, Any]],
    expected_count: int,
    fallback_fps: float,
) -> dict[str, Any]:
    """Normalize ffprobe frame timestamps into one duration per extracted frame."""
    expected_count = max(0, int(expected_count))
    fallback = 1.0 / max(0.001, float(fallback_fps or 30.0))
    rows = list(frames or [])
    timestamps: list[float | None] = []
    packets: list[float | None] = []
    for row in rows[:expected_count]:
        if not isinstance(row, dict):
            timestamps.append(None)
            packets.append(None)
            continue
        raw_ts = row.get("best_effort_timestamp_time")
        raw_duration = row.get("pkt_duration_time") or row.get("duration_time")
        try:
            timestamps.append(float(raw_ts) if raw_ts is not None else None)
        except Exception:
            timestamps.append(None)
        try:
            duration = float(raw_duration) if raw_duration is not None else None
            packets.append(duration if duration and duration > 0 else None)
        except Exception:
            packets.append(None)

    durations: list[float] = []
    mode = "constant-fallback"
    if len(timestamps) == expected_count and expected_count > 0:
        timestamp_durations: list[float] = []
        valid = True
        for previous, current in zip(timestamps, timestamps[1:]):
            if previous is None or current is None or current <= previous:
                valid = False
                break
            timestamp_durations.append(current - previous)
        if valid:
            last = packets[-1] if packets else None
            if last is None:
                last = statistics.median(timestamp_durations) if timestamp_durations else fallback
            durations = timestamp_durations + [float(last)]
            mode = "timestamps"

    if not durations and len(packets) == expected_count and expected_count > 0 and all(value is not None for value in packets):
        durations = [float(value) for value in packets if value is not None]
        mode = "packet-durations"

    if len(durations) != expected_count:
        durations = [fallback] * expected_count
        mode = "constant-fallback"

    durations = [max(1e-6, min(10.0, float(value))) for value in durations]
    median = statistics.median(durations) if durations else fallback
    variable = any(abs(value - median) > max(0.0005, median * 0.02) for value in durations)
    return {
        "version": MEDIA_VERSION,
        "mode": mode,
        "variable": bool(variable),
        "durations": durations,
        "total_duration": float(sum(durations)),
        "median_duration": float(median),
        "frame_count": expected_count,
    }


def _concat_quote(path: Path) -> str:
    # Forward slashes avoid ffconcat treating Windows backslashes as escapes.
    return Path(path).resolve().as_posix().replace("'", "'\\''")


def write_ffconcat(path: Path, frame_dir: Path, numbers: list[int], durations: list[float]) -> None:
    if len(numbers) != len(durations) or not numbers:
        raise ValueError("ffconcat requires one duration per frame")
    lines = ["ffconcat version 1.0"]
    for number, duration in zip(numbers, durations):
        frame = Path(frame_dir) / f"frame_{int(number):06d}.png"
        lines.append(f"file '{_concat_quote(frame)}'")
        lines.append(f"duration {max(1e-6, float(duration)):.9f}")
    last = Path(frame_dir) / f"frame_{int(numbers[-1]):06d}.png"
    lines.append(f"file '{_concat_quote(last)}'")
    atomic_text_write(Path(path), "\n".join(lines) + "\n")


def _valid_marker(root: Path) -> bool:
    path = Path(root) / PROJECT_MARKER
    if not path.exists() or path.is_symlink():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return isinstance(data, dict) and data.get("product") == PROJECT_PRODUCT
    except Exception:
        return False


def _legacy_project_evidence(root: Path) -> bool:
    root = Path(root)
    source = root / "source_info.json"
    if not source.exists() or source.is_symlink():
        return False
    strong = (
        root / "frames",
        root / "comicframe_timeline.json",
        root / "comicframe_profile.json",
        root / "render_settings.json",
        root / "styled_frames",
    )
    return any(path.exists() for path in strong)


def _reject_generated_symlinks(root: Path) -> None:
    for name in (*GENERATED_DIRS, *GENERATED_FILES):
        path = Path(root) / name
        if path.is_symlink():
            raise RuntimeError(
                f"Project contains a generated-path symlink ({name}). ComicFrame will not follow project symlinks; "
                "remove it or choose a clean project directory."
            )


def ensure_project_owned(root: Path) -> str:
    """Claim a new/legacy ComicFrame project, but refuse ambiguous generic-folder collisions."""
    root = Path(root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    _reject_generated_symlinks(root)
    if _valid_marker(root):
        return "existing"
    if (root / PROJECT_MARKER).exists():
        raise RuntimeError("Project ownership marker exists but is invalid; choose a new project directory or repair the marker.")

    legacy = _legacy_project_evidence(root)
    collisions = [name for name in (*GENERATED_DIRS, *GENERATED_FILES) if (root / name).exists()]
    if collisions and not legacy:
        raise RuntimeError(
            "This folder contains names ComicFrame must own but is not a recognized ComicFrame project: "
            + ", ".join(collisions[:8])
            + ". Choose an empty/new project directory so unrelated files cannot be deleted."
        )

    marker = {
        "product": PROJECT_PRODUCT,
        "version": MEDIA_VERSION,
        "project_id": uuid.uuid4().hex,
        "migrated_legacy": bool(legacy),
    }
    atomic_json_write(root / PROJECT_MARKER, marker)
    return "legacy" if legacy else "new"


def safe_reset_generated_state(root: Path) -> None:
    """Reset only a verified ComicFrame-owned project directory."""
    root = Path(root).expanduser().resolve()
    if not _valid_marker(root):
        raise RuntimeError("Refusing to clear generated state: this folder is not marked as a ComicFrame project.")
    _reject_generated_symlinks(root)
    for name in GENERATED_DIRS:
        path = root / name
        if path.exists():
            shutil.rmtree(path)
    for name in GENERATED_FILES:
        path = root / name
        if path.is_file():
            path.unlink(missing_ok=True)


def safe_clear_generated_directory(root: Path, directory: Path) -> None:
    root = Path(root).expanduser().resolve()
    directory = Path(directory)
    if not _valid_marker(root):
        raise RuntimeError("Refusing to clear generated files outside a verified ComicFrame project.")
    if directory.is_symlink():
        raise RuntimeError("Refusing to clear a generated directory through a symlink.")
    try:
        resolved = directory.resolve(strict=False)
        resolved.relative_to(root)
    except Exception as exc:
        raise RuntimeError("Generated directory escapes the ComicFrame project.") from exc
    directory.mkdir(parents=True, exist_ok=True)
    for child in directory.iterdir():
        if child.is_symlink():
            raise RuntimeError(f"Refusing to follow symlink inside generated directory: {child.name}")
        if child.is_file():
            child.unlink(missing_ok=True)
        elif child.is_dir():
            shutil.rmtree(child)
