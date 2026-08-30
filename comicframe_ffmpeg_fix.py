#!/usr/bin/env python3
"""Targeted ffmpeg audio-remux recovery for ComicFrame Studio.

Long renders should not be lost because the final ``styled_silent.mp4`` + source
 audio mux hits one of ffmpeg's timestamp/interleave edge cases.  The canonical
v2.9 assembler is intentionally left alone; this module patches only the shared
``_run`` boundary and only intercepts the final audio-restore command shape.

Normal ffmpeg commands continue through the original runner unchanged.  For the
final remux we capture stderr, preserve a useful diagnostic, and retry with two
safe recovery strategies before surfacing the failure.
"""
from __future__ import annotations

import subprocess
from typing import Iterable, Sequence

from comicframe_studio import ComicFrameStudio as _BaseStudio

FFMPEG_MUX_FIX_VERSION = "1.0"
_PATCH_FLAG = "_comicframe_ffmpeg_mux_fix_v1"
_ORIGINAL_RUN_ATTR = "_comicframe_ffmpeg_mux_original_run"


def _parts(args: Sequence[object] | Iterable[object]) -> list[str]:
    return [str(value) for value in args]


def _exe_name(value: str) -> str:
    return str(value).replace("\\", "/").rsplit("/", 1)[-1].lower()


def _option_values(parts: list[str], option: str) -> list[str]:
    values: list[str] = []
    for index, value in enumerate(parts[:-1]):
        if value == option:
            values.append(parts[index + 1])
    return values


def is_audio_restore_command(args: Sequence[object] | Iterable[object]) -> bool:
    """Return True only for the final styled-video + original-audio mux."""
    parts = _parts(args)
    if not parts or _exe_name(parts[0]) not in {"ffmpeg", "ffmpeg.exe"}:
        return False
    maps = _option_values(parts, "-map")
    video_codecs = _option_values(parts, "-c:v")
    audio_codecs = _option_values(parts, "-c:a")
    inputs = _option_values(parts, "-i")
    return (
        len(inputs) >= 2
        and "0:v:0" in maps
        and any(value.startswith("1:a:") or value == "1:a?" for value in maps)
        and "copy" in video_codecs
        and bool(audio_codecs)
    )


def _remove_option_pair(parts: list[str], option: str) -> list[str]:
    result: list[str] = []
    index = 0
    while index < len(parts):
        if parts[index] == option and index + 1 < len(parts):
            index += 2
            continue
        result.append(parts[index])
        index += 1
    return result


def _set_option_value(parts: list[str], option: str, value: str) -> list[str]:
    result = list(parts)
    for index in range(len(result) - 1):
        if result[index] == option:
            result[index + 1] = value
            return result
    # Output options belong immediately before the output path.
    return result[:-1] + [option, value, result[-1]]


def _ensure_output_option(parts: list[str], option: str, value: str) -> list[str]:
    if option in parts:
        return parts
    return parts[:-1] + [option, value, parts[-1]]


def _ensure_output_flag(parts: list[str], flag: str) -> list[str]:
    if flag in parts:
        return parts
    return parts[:-1] + [flag, parts[-1]]


def build_audio_mux_retries(args: Sequence[object] | Iterable[object]) -> list[tuple[str, list[str]]]:
    """Build conservative remux retries without touching the encoded video stream.

    Retry 1 keeps AAC transcoding but gives ffmpeg substantially more muxing room
    and normalizes negative timestamps.  Retry 2 copies the source audio packets
    directly, which avoids decoder/encoder failures on otherwise valid camera
    audio while still stream-copying the already-rendered video.

    A final timestamp-repair AAC pass is kept as the broadest compatibility path
    for sources whose audio cannot be copied into MP4.
    """
    original = _parts(args)

    guarded = _ensure_output_option(original, "-max_muxing_queue_size", "4096")
    guarded = _ensure_output_option(guarded, "-avoid_negative_ts", "make_zero")

    copied = _set_option_value(guarded, "-c:a", "copy")
    copied = _remove_option_pair(copied, "-b:a")

    repaired = _set_option_value(guarded, "-c:a", "aac")
    repaired = _ensure_output_option(repaired, "-b:a", "192k")
    if "-af" not in repaired and "-filter:a" not in repaired:
        repaired = repaired[:-1] + ["-af", "aresample=async=1:first_pts=0", repaired[-1]]
    repaired = _ensure_output_flag(repaired, "-shortest")

    return [
        ("larger mux queue + timestamp normalization", guarded),
        ("source-audio stream copy", copied),
        ("AAC timestamp repair", repaired),
    ]


def _stderr_tail(text: str | None, max_lines: int = 14, max_chars: int = 5000) -> str:
    lines = [line.rstrip() for line in str(text or "").splitlines() if line.strip()]
    tail = "\n".join(lines[-max_lines:])
    if len(tail) > max_chars:
        tail = tail[-max_chars:]
    return tail or "(ffmpeg produced no stderr text)"


def _run_mux_attempt(command: list[str], capture: bool) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE,
    )


def _run_with_mux_recovery(self, args, capture=False):
    original_run = getattr(_BaseStudio, _ORIGINAL_RUN_ATTR)
    if not is_audio_restore_command(args):
        return original_run(self, args, capture)

    command = _parts(args)
    self._log("$ " + " ".join(command))
    attempts: list[tuple[str, list[str]]] = [("standard audio restore", command)]
    attempts.extend(build_audio_mux_retries(command))
    failures: list[tuple[str, int, str]] = []

    for index, (label, candidate) in enumerate(attempts):
        if index:
            self._log(f"ffmpeg audio restore retry {index}/{len(attempts) - 1}: {label}")
        completed = _run_mux_attempt(candidate, bool(capture))
        if completed.returncode == 0:
            if index:
                self._log(f"ffmpeg audio restore recovered with {label}.")
            return (completed.stdout or "").strip() if capture else ""

        detail = _stderr_tail(completed.stderr)
        failures.append((label, int(completed.returncode), detail))
        self._log(f"ffmpeg audio restore failed ({label}, exit {completed.returncode}):\n{detail}")

    summary = "\n\n".join(
        f"{label} (exit {code}):\n{detail}"
        for label, code, detail in failures
    )
    raise RuntimeError(
        "ffmpeg could not restore the source audio after automatic recovery attempts. "
        "The rendered styled frames and styled_silent.mp4 are preserved, so the render does not need to be repeated.\n\n"
        + summary
    )


def install_ffmpeg_mux_fix() -> None:
    if getattr(_BaseStudio, _PATCH_FLAG, False):
        return
    if not hasattr(_BaseStudio, _ORIGINAL_RUN_ATTR):
        setattr(_BaseStudio, _ORIGINAL_RUN_ATTR, _BaseStudio._run)
    _BaseStudio._run = _run_with_mux_recovery
    setattr(_BaseStudio, _PATCH_FLAG, True)


install_ffmpeg_mux_fix()
