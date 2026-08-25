#!/usr/bin/env python3
"""Cross-cutting runtime hardening utilities for ComicFrame Studio.

This module intentionally contains pure/file-system helpers instead of another UI
feature mixin.  The canonical app boundary uses these helpers to make source
identity, resume invalidation, shot-memory pruning, and persistent caches safer.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any, Iterable

HARDENING_VERSION = "2.8-audit"
_FRAME_RE = re.compile(r"^frame_(\d{6})\.png$")

DERIVED_DIRS = (
    "frames",
    "styled_frames",
    "test_frames",
    "shot_memory",
    "cache",
    "previews",
    "subjects",
    "director_preview_frames",
)

DERIVED_FILES = (
    "source_info.json",
    "comicframe_timeline.json",
    "comicframe_timeline.rendered.json",
    "comicframe_profile.json",
    "comicframe_test_profile.json",
    "render_settings.json",
    "styled_silent.mp4",
    "FINAL_STYLED.mp4",
    "DIRECTOR_PREVIEW.jpg",
)


def atomic_json_write(path: Path, data: dict[str, Any]) -> None:
    """Write JSON through a sibling temp file so a crash cannot truncate state."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".part")
    temp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    temp.replace(path)


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def runtime_source_key(path: Path) -> tuple[str, int, int]:
    path = Path(path).expanduser().resolve()
    stat = path.stat()
    return str(path), int(stat.st_size), int(stat.st_mtime_ns)


def sampled_file_sha256(path: Path, sample_bytes: int = 1024 * 1024) -> str:
    """Strong-enough source identity without hashing an entire large video.

    Size plus first/middle/last 1 MiB catches normal replacement/edit cases while
    keeping startup I/O bounded for large source videos.
    """
    path = Path(path)
    size = int(path.stat().st_size)
    sample_bytes = max(4096, int(sample_bytes))
    offsets = sorted({
        0,
        max(0, size // 2 - sample_bytes // 2),
        max(0, size - sample_bytes),
    })
    digest = hashlib.sha256()
    digest.update(f"size:{size}\n".encode("ascii"))
    with path.open("rb") as handle:
        for offset in offsets:
            handle.seek(offset)
            chunk = handle.read(sample_bytes)
            digest.update(f"offset:{offset}:len:{len(chunk)}\n".encode("ascii"))
            digest.update(chunk)
    return digest.hexdigest()


def source_fingerprint(path: Path) -> str:
    return sampled_file_sha256(Path(path))


def _parse_int(value: Any) -> int | None:
    try:
        parsed = int(str(value))
        return parsed if parsed > 0 else None
    except Exception:
        return None


def frame_numbers(directory: Path) -> list[int]:
    directory = Path(directory)
    if not directory.exists():
        return []
    numbers: list[int] = []
    for path in directory.glob("frame_*.png"):
        match = _FRAME_RE.match(path.name)
        if match:
            numbers.append(int(match.group(1)))
    return sorted(numbers)


def frame_sequence_report(directory: Path, expected_count: int | None = None) -> dict[str, Any]:
    numbers = frame_numbers(directory)
    count = len(numbers)
    contiguous = bool(numbers) and numbers == list(range(1, numbers[-1] + 1))
    if expected_count is not None:
        expected_count = max(0, int(expected_count))
        expected = list(range(1, expected_count + 1))
        exact = numbers == expected
        missing = [n for n in expected if n not in set(numbers)][:20]
        extras = [n for n in numbers if n > expected_count][:20]
    else:
        exact = contiguous
        missing = []
        extras = []
    return {
        "count": count,
        "first": numbers[0] if numbers else 0,
        "last": numbers[-1] if numbers else 0,
        "contiguous": contiguous,
        "expected_count": expected_count,
        "valid": bool(numbers) and exact,
        "missing": missing,
        "extras": extras,
    }


def legacy_source_compatible(meta: dict[str, Any], info: dict[str, Any], frames_dir: Path) -> bool:
    """One-time safe migration for pre-fingerprint projects.

    Old versions stored dimensions/FPS/duration but not source content identity.
    We preserve their caches only when those facts and the extracted sequence are
    internally consistent; otherwise the project is reset instead of guessed at.
    """
    try:
        if int(meta.get("width") or 0) != int(info.get("width") or 0):
            return False
        if int(meta.get("height") or 0) != int(info.get("height") or 0):
            return False
        if abs(float(meta.get("fps") or 0.0) - float(info.get("fps") or 0.0)) > 1e-4:
            return False
        old_duration = float(meta.get("duration") or 0.0)
        new_duration = float(info.get("duration") or 0.0)
        tolerance = max(0.10, 2.0 / max(1.0, float(info.get("fps") or 30.0)))
        if old_duration and new_duration and abs(old_duration - new_duration) > tolerance:
            return False
    except Exception:
        return False

    expected = _parse_int(meta.get("frame_count")) or _parse_int(meta.get("nb_frames"))
    report = frame_sequence_report(frames_dir, expected)
    if expected is not None:
        return bool(report["valid"])
    return bool(report["contiguous"] and report["count"] > 0)


def build_source_metadata(
    video: Path,
    info: dict[str, Any],
    fingerprint: str,
    frame_count: int,
) -> dict[str, Any]:
    out = dict(info)
    out.update({
        "source_fingerprint": str(fingerprint),
        "source_path": str(Path(video).expanduser().resolve()),
        "source_bytes": int(Path(video).stat().st_size),
        "frame_count": int(frame_count),
        "hardening_version": HARDENING_VERSION,
    })
    return out


def clear_directory(directory: Path) -> None:
    directory = Path(directory)
    if not directory.exists():
        return
    for child in directory.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink(missing_ok=True)


def project_has_derived_state(root: Path) -> bool:
    root = Path(root)
    return any((root / name).exists() for name in (*DERIVED_DIRS, *DERIVED_FILES))


def reset_project_for_new_source(root: Path) -> None:
    """Delete only ComicFrame-generated state when the source content changes."""
    root = Path(root)
    for name in DERIVED_DIRS:
        path = root / name
        if path.exists():
            shutil.rmtree(path)
    for name in DERIVED_FILES:
        path = root / name
        if path.exists():
            path.unlink()


def canonical_frame_signature(timeline: dict[str, Any], frame_number: int) -> str:
    """Use the newest dependency signature that the timeline actually understands."""
    if isinstance(timeline.get("autopilot"), dict):
        from comicframe_autopilot import autopilot_frame_signature
        return autopilot_frame_signature(timeline, int(frame_number))
    if isinstance(timeline.get("subject_library"), dict) or any(
        isinstance(s, dict) and s.get("subject_id") for s in timeline.get("shots", [])
    ):
        from comicframe_subjects import subject_dependency_signature
        return subject_dependency_signature(timeline, int(frame_number))
    if isinstance(timeline.get("render_intelligence"), dict):
        from comicframe_efficiency import efficiency_frame_signature
        return efficiency_frame_signature(timeline, int(frame_number))
    if any(
        isinstance(s, dict) and (
            s.get("reference_frame")
            or s.get("reference_backend_resolved")
            or s.get("subject_lock")
        )
        for s in timeline.get("shots", [])
    ):
        from comicframe_reference_lock import reference_plan_signature
        return reference_plan_signature(timeline, int(frame_number))
    from comicframe_director import frame_plan_signature
    return frame_plan_signature(timeline, int(frame_number))


def changed_frame_numbers(old: dict[str, Any], new: dict[str, Any]) -> list[int]:
    old_total = int(old.get("total_frames") or 0)
    new_total = int(new.get("total_frames") or 0)
    total = max(old_total, new_total)
    changed: list[int] = []
    for number in range(1, total + 1):
        if number > old_total or number > new_total:
            changed.append(number)
            continue
        if canonical_frame_signature(old, number) != canonical_frame_signature(new, number):
            changed.append(number)
    return changed


def collapse_ranges(numbers: Iterable[int]) -> list[tuple[int, int]]:
    values = sorted({int(value) for value in numbers if int(value) > 0})
    if not values:
        return []
    ranges: list[tuple[int, int]] = []
    start = previous = values[0]
    for value in values[1:]:
        if value == previous + 1:
            previous = value
            continue
        ranges.append((start, previous))
        start = previous = value
    ranges.append((start, previous))
    return ranges


def _intersects(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]


def affected_shot_ranges(
    old: dict[str, Any],
    new: dict[str, Any],
    changed_frames: Iterable[int],
) -> list[tuple[int, int]]:
    """Expand changed frames to whole affected director shots for memory pruning."""
    changed_ranges = collapse_ranges(changed_frames)
    if not changed_ranges:
        return []
    expanded = list(changed_ranges)
    for timeline in (old, new):
        for shot in timeline.get("shots", []):
            if not isinstance(shot, dict):
                continue
            shot_range = (int(shot.get("start") or 0), int(shot.get("end") or 0))
            if shot_range[0] <= 0 or shot_range[1] < shot_range[0]:
                continue
            if any(_intersects(shot_range, changed) for changed in changed_ranges):
                expanded.append(shot_range)
    expanded.sort()
    merged: list[tuple[int, int]] = []
    for start, end in expanded:
        if not merged or start > merged[-1][1] + 1:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged


def prune_shot_memory_ranges(root: Path, ranges: Iterable[tuple[int, int]]) -> int:
    """Remove stale palette anchors only for shots that actually changed.

    If the manifest is unreadable we remove the memory scope entirely rather than
    risk reusing stale style state.
    """
    ranges = list(ranges)
    if not ranges:
        return 0
    memory_root = Path(root) / "shot_memory" / "full"
    manifest_path = memory_root / "manifest.json"
    if not memory_root.exists():
        return 0
    if not manifest_path.exists():
        shutil.rmtree(memory_root)
        return -1
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        anchors = list(data.get("anchors") or [])
        kept: list[dict[str, Any]] = []
        removed: list[dict[str, Any]] = []
        for entry in anchors:
            if not isinstance(entry, dict):
                continue
            frame = int(entry.get("frame") or 0)
            if any(start <= frame <= end for start, end in ranges):
                removed.append(entry)
            else:
                kept.append(entry)
        refs = memory_root / "references"
        for entry in removed:
            name = str(entry.get("file") or "").strip()
            if name:
                (refs / name).unlink(missing_ok=True)
        data["anchors"] = kept
        atomic_json_write(manifest_path, data)
        return len(removed)
    except Exception:
        shutil.rmtree(memory_root)
        return -1


def analysis_signature(source_fp: str, frame_count: int, cut_setting: float) -> str:
    payload = {
        "algorithm": "director-cuts-v2.8",
        "source": str(source_fp),
        "frames": int(frame_count),
        "cut_setting": round(float(cut_setting), 6),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def trim_cache_directory(
    directory: Path,
    max_bytes: int,
    max_files: int,
    target_ratio: float = 0.85,
) -> dict[str, int]:
    """Bound a persistent cache by oldest mtime, returning removal statistics."""
    directory = Path(directory)
    if not directory.exists():
        return {"removed_files": 0, "removed_bytes": 0, "remaining_files": 0, "remaining_bytes": 0}
    entries: list[tuple[float, int, Path]] = []
    for path in directory.iterdir():
        if not path.is_file():
            continue
        try:
            stat = path.stat()
            entries.append((float(stat.st_mtime), int(stat.st_size), path))
        except OSError:
            continue
    total_bytes = sum(size for _mtime, size, _path in entries)
    if len(entries) <= max_files and total_bytes <= max_bytes:
        return {
            "removed_files": 0,
            "removed_bytes": 0,
            "remaining_files": len(entries),
            "remaining_bytes": total_bytes,
        }
    target_bytes = int(max_bytes * max(0.1, min(1.0, target_ratio)))
    target_files = int(max_files * max(0.1, min(1.0, target_ratio)))
    removed_files = removed_bytes = 0
    for _mtime, size, path in sorted(entries, key=lambda item: item[0]):
        if len(entries) - removed_files <= target_files and total_bytes - removed_bytes <= target_bytes:
            break
        try:
            path.unlink()
            removed_files += 1
            removed_bytes += size
        except OSError:
            pass
    return {
        "removed_files": removed_files,
        "removed_bytes": removed_bytes,
        "remaining_files": max(0, len(entries) - removed_files),
        "remaining_bytes": max(0, total_bytes - removed_bytes),
    }


def touch(path: Path) -> None:
    try:
        os.utime(path, None)
    except OSError:
        pass
