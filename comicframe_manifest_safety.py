#!/usr/bin/env python3
"""Path confinement for project-manifest controlled files.

Persisted project IDs and filenames are untrusted input.  This module never
follows generated-path symlinks and never lets a manifest-selected leaf escape
its declared project directory.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any, Iterable

from comicframe_media import atomic_json_write

_SAFE_LEAF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def _unsafe_windows_leaf(value: str) -> bool:
    if value.endswith((".", " ")):
        return True
    stem = value.split(".", 1)[0].upper()
    return stem in _WINDOWS_RESERVED


def safe_leaf_path(root: Path, name: str) -> Path | None:
    """Return a confined direct child, or None for unsafe manifest input."""
    root_path = Path(root).expanduser()
    if root_path.is_symlink():
        return None
    root_resolved = root_path.resolve()
    value = str(name or "").strip()
    if not value or not _SAFE_LEAF.fullmatch(value):
        return None
    if value in {".", ".."} or "/" in value or "\\" in value or ":" in value or _unsafe_windows_leaf(value):
        return None
    candidate = root_resolved / value
    try:
        if candidate.is_symlink():
            return None
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(root_resolved)
    except Exception:
        return None
    return candidate


def confined_project_path(project_root: Path, *parts: str) -> Path | None:
    """Resolve a generated path only when every component is non-symlink and project-confined."""
    root_path = Path(project_root).expanduser()
    if root_path.is_symlink():
        return None
    root = root_path.resolve()
    candidate = root
    for raw in parts:
        value = str(raw or "")
        if not value or value in {".", ".."} or "/" in value or "\\" in value:
            return None
        candidate = candidate / value
        if candidate.is_symlink():
            return None
    try:
        candidate.resolve(strict=False).relative_to(root)
    except Exception:
        return None
    return candidate


def safe_subject_root(subjects_root: Path, subject_id: str) -> Path:
    """Map malformed subject IDs to a harmless direct child inside the subject root."""
    root_path = Path(subjects_root).expanduser()
    if root_path.is_symlink():
        raise RuntimeError("Subject root is a symlink; refusing to follow project-controlled paths.")
    root = root_path.resolve()
    safe = safe_leaf_path(root, subject_id)
    if safe is not None:
        return safe
    digest = hashlib.sha256(str(subject_id or "").encode("utf-8", errors="replace")).hexdigest()[:24]
    return root / f"_invalid_{digest}"


def prune_shot_memory_ranges_safe(root: Path, ranges: Iterable[tuple[int, int]]) -> int:
    """Selectively prune Shot Memory anchors without trusting directories or manifest filenames."""
    ranges = list(ranges)
    if not ranges:
        return 0
    project_root = Path(root).expanduser().resolve()
    memory_root = confined_project_path(project_root, "shot_memory", "full")
    if memory_root is None:
        raise RuntimeError("Shot Memory path is not safely confined to the ComicFrame project.")
    manifest_path = memory_root / "manifest.json"
    if manifest_path.is_symlink():
        raise RuntimeError("Shot Memory manifest is a symlink; refusing to follow it.")
    if not memory_root.exists():
        return 0
    if not manifest_path.exists():
        shutil.rmtree(memory_root)
        return -1
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("anchors"), list):
            raise ValueError("invalid Shot Memory manifest")
        kept: list[dict[str, Any]] = []
        removed: list[dict[str, Any]] = []
        for entry in data["anchors"]:
            if not isinstance(entry, dict):
                continue
            frame = int(entry.get("frame") or 0)
            if any(int(start) <= frame <= int(end) for start, end in ranges):
                removed.append(entry)
            else:
                kept.append(entry)

        refs = confined_project_path(project_root, "shot_memory", "full", "references")
        if refs is None:
            raise RuntimeError("Shot Memory reference path escapes the project.")
        for entry in removed:
            path = safe_leaf_path(refs, str(entry.get("file") or ""))
            if path is None and str(entry.get("file") or "").strip():
                raise RuntimeError("Unsafe Shot Memory reference filename in manifest.")
            if path is not None:
                path.unlink(missing_ok=True)
        data["anchors"] = kept
        atomic_json_write(manifest_path, data)
        return len(removed)
    except Exception:
        # The scope itself is proven project-confined above. A corrupt/hostile
        # manifest cannot be partially trusted, so discard only this generated scope.
        shutil.rmtree(memory_root)
        return -1
