#!/usr/bin/env python3
"""Path confinement for project-manifest controlled files.

ComicFrame normally writes its own subject/reference and Shot Memory manifests,
but project directories can be copied, shared, or hand-edited. Treat persisted
IDs/filenames as untrusted leaf components so a crafted manifest cannot escape
its project directory with ../, Windows separators, drive syntax, or symlinks.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any, Iterable

_SAFE_LEAF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def safe_leaf_path(root: Path, name: str) -> Path | None:
    """Return a confined direct child, or None for unsafe manifest input."""
    root = Path(root).expanduser().resolve()
    value = str(name or "").strip()
    if not value or not _SAFE_LEAF.fullmatch(value):
        return None
    if value in {".", ".."} or "/" in value or "\\" in value or ":" in value:
        return None
    candidate = root / value
    try:
        # resolve(strict=False) also catches an existing symlink leaf that points
        # outside the root. Generated ComicFrame references are regular files.
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(root)
    except Exception:
        return None
    return candidate


def safe_subject_root(subjects_root: Path, subject_id: str) -> Path:
    """Map malformed subject IDs to a harmless quarantine path inside the project."""
    root = Path(subjects_root).expanduser().resolve()
    safe = safe_leaf_path(root, subject_id)
    if safe is not None:
        return safe
    digest = hashlib.sha256(str(subject_id or "").encode("utf-8", errors="replace")).hexdigest()[:24]
    return root / "_invalid_subjects" / digest


def prune_shot_memory_ranges_safe(root: Path, ranges: Iterable[tuple[int, int]]) -> int:
    """Selectively prune Shot Memory anchors without trusting manifest filenames."""
    ranges = list(ranges)
    if not ranges:
        return 0
    memory_root = Path(root).expanduser().resolve() / "shot_memory" / "full"
    manifest_path = memory_root / "manifest.json"
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
            if any(start <= frame <= end for start, end in ranges):
                removed.append(entry)
            else:
                kept.append(entry)

        refs = memory_root / "references"
        for entry in removed:
            path = safe_leaf_path(refs, str(entry.get("file") or ""))
            if path is not None:
                path.unlink(missing_ok=True)
        data["anchors"] = kept
        temp = manifest_path.with_name(manifest_path.name + ".part")
        temp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        temp.replace(manifest_path)
        return len(removed)
    except Exception:
        # A malformed manifest is safer to discard than partially trust. This
        # operation is confined to ComicFrame's own Shot Memory directory.
        shutil.rmtree(memory_root)
        return -1
