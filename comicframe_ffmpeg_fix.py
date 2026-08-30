#!/usr/bin/env python3
"""Targeted ffmpeg audio-remux recovery for ComicFrame Studio.

Long renders should not be lost because the final ``styled_silent.mp4`` + source
audio mux hits a codec, timestamp, or old-FFmpeg compatibility edge case. The
canonical renderer remains untouched; this module patches only the shared
``_run`` boundary and only intercepts the final audio-restore command shape.

The recovery order deliberately starts with the most portable operation possible:
stream-copy the source audio into the already-rendered video. That path works on
very old FFmpeg builds and avoids AAC encoding entirely. Newer timestamp/muxing
repairs are attempted only after the legacy-safe path. Completed GPU frames are
never discarded by this layer.
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Iterable, Sequence

from comicframe_studio import ComicFrameStudio as _BaseStudio

FFMPEG_MUX_FIX_VERSION = "1.2"
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


def _last_option_value(parts: list[str], option: str, default: str = "") -> str:
    values = _option_values(parts, option)
    return values[-1] if values else default


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
    return result[:-1] + [option, value, result[-1]]


def _ensure_output_option(parts: list[str], option: str, value: str) -> list[str]:
    if option in parts:
        return parts
    return parts[:-1] + [option, value, parts[-1]]


def _ensure_output_flag(parts: list[str], flag: str) -> list[str]:
    if flag in parts:
        return parts
    return parts[:-1] + [flag, parts[-1]]


def build_legacy_stream_copy_command(args: Sequence[object] | Iterable[object]) -> list[str]:
    """Build a compatibility-first mux with no modern-only FFmpeg options.

    The source audio is already AAC for the common phone/camera MP4 case, so the
    safest recovery is packet copy. This also avoids old FFmpeg builds where the
    native AAC encoder exists but is marked experimental.
    """
    command = _parts(args)
    command = _set_option_value(command, "-c:a", "copy")
    for option in ("-b:a", "-max_muxing_queue_size", "-avoid_negative_ts", "-af", "-filter:a"):
        command = _remove_option_pair(command, option)
    return command


def build_legacy_aac_command(args: Sequence[object] | Iterable[object]) -> list[str]:
    """Enable the historical native AAC encoder used by FFmpeg 1.x/2.x builds."""
    command = _parts(args)
    command = _set_option_value(command, "-c:a", "aac")
    command = _ensure_output_option(command, "-b:a", "192k")
    command = _ensure_output_option(command, "-strict", "-2")
    for option in ("-max_muxing_queue_size", "-avoid_negative_ts", "-af", "-filter:a"):
        command = _remove_option_pair(command, option)
    return command


def build_audio_mux_retries(args: Sequence[object] | Iterable[object]) -> list[tuple[str, list[str]]]:
    """Build portable first, then modern, then historical AAC recovery paths."""
    original = _parts(args)
    legacy_copy = build_legacy_stream_copy_command(original)

    guarded = _ensure_output_option(original, "-max_muxing_queue_size", "4096")
    guarded = _ensure_output_option(guarded, "-avoid_negative_ts", "make_zero")
    guarded_copy = _set_option_value(guarded, "-c:a", "copy")
    guarded_copy = _remove_option_pair(guarded_copy, "-b:a")

    repaired = _set_option_value(guarded, "-c:a", "aac")
    repaired = _ensure_output_option(repaired, "-b:a", "192k")
    if "-af" not in repaired and "-filter:a" not in repaired:
        repaired = repaired[:-1] + ["-af", "aresample=async=1:first_pts=0", repaired[-1]]
    repaired = _ensure_output_flag(repaired, "-shortest")

    legacy_aac = build_legacy_aac_command(original)

    return [
        ("legacy-safe source-audio stream copy", legacy_copy),
        ("larger mux queue + timestamp normalization", guarded_copy),
        ("AAC timestamp repair", repaired),
        ("legacy AAC encoder compatibility", legacy_aac),
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


def _record_failure(
    self,
    failures: list[tuple[str, int, str]],
    label: str,
    completed: subprocess.CompletedProcess[str],
) -> None:
    detail = _stderr_tail(completed.stderr)
    failures.append((label, int(completed.returncode), detail))
    self._log(f"ffmpeg audio restore failed ({label}, exit {completed.returncode}):\n{detail}")


def _recovery_temp_audio(output: Path) -> Path:
    return output.parent / f".comicframe_audio_recovery.{time.time_ns()}.m4a"


def build_detached_audio_commands(args: Sequence[object] | Iterable[object], audio_temp: Path) -> list[tuple[str, list[str]]]:
    """Detach source AAC without encoding, then mux the clean audio file back in."""
    parts = _parts(args)
    inputs = _option_values(parts, "-i")
    if len(inputs) < 2:
        return []
    silent, source = inputs[0], inputs[1]
    output = parts[-1]
    duration = _last_option_value(parts, "-t")

    extract = [
        "ffmpeg", "-y",
        "-i", source,
        "-map", "0:a:0", "-vn",
        "-c:a", "copy",
        str(audio_temp),
    ]

    remux = [
        "ffmpeg", "-y",
        "-i", silent, "-i", str(audio_temp),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "copy",
    ]
    if duration:
        remux += ["-t", duration]
    remux += ["-movflags", "+faststart", output]

    return [
        ("detached source-audio packet copy", extract),
        ("detached-audio legacy-safe remux", remux),
    ]


def build_frame_rebuild_command(self, args: Sequence[object] | Iterable[object], audio_temp: Path) -> list[str] | None:
    """Rebuild MP4 from completed styled frames without requiring AAC encoding."""
    parts = _parts(args)
    output = parts[-1]
    duration = _last_option_value(parts, "-t")
    try:
        paths = self.project_paths()
        concat = Path(paths["styled_concat"])
        silent = Path(_option_values(parts, "-i")[0])
        if not concat.exists() or not audio_temp.exists():
            return None

        width = height = 0
        probe = self._ffprobe_json(silent)
        for stream in probe.get("streams") or []:
            if str(stream.get("codec_type")) == "video":
                width = int(stream.get("width") or 0)
                height = int(stream.get("height") or 0)
                break
        if width <= 0 or height <= 0:
            return None
    except Exception:
        return None

    command = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat),
        "-i", str(audio_temp),
        "-map", "0:v:0", "-map", "1:a:0",
        "-vsync", "vfr",
        "-vf", f"scale={width}:{height}:flags=lanczos,setpts=PTS-STARTPTS",
        "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p",
        "-c:a", "copy",
    ]
    if duration:
        command += ["-t", duration]
    command += ["-movflags", "+faststart", output]
    return command


def _write_diagnostic_log(self, failures: list[tuple[str, int, str]]) -> Path | None:
    try:
        root = Path(self.project_paths()["root"])
        root.mkdir(parents=True, exist_ok=True)
        path = root / "ffmpeg_audio_recovery.log"
        text = "\n\n".join(
            f"=== {label} · exit {code} ===\n{detail}"
            for label, code, detail in failures
        )
        path.write_text(text + "\n", encoding="utf-8")
        return path
    except Exception:
        return None


def _looks_like_ancient_ffmpeg(failures: list[tuple[str, int, str]]) -> bool:
    text = "\n".join(detail.lower() for _label, _code, detail in failures)
    return (
        "copyright (c) 2000-2013" in text
        or "encoder 'aac' is experimental" in text
        or "unrecognized option 'max_muxing_queue_size'" in text
    )


def _run_with_mux_recovery(self, args, capture=False):
    original_run = getattr(_BaseStudio, _ORIGINAL_RUN_ATTR)
    if not is_audio_restore_command(args):
        return original_run(self, args, capture)

    command = _parts(args)
    self._log("$ " + " ".join(command))
    failures: list[tuple[str, int, str]] = []

    standard = _run_mux_attempt(command, bool(capture))
    if standard.returncode == 0:
        return (standard.stdout or "").strip() if capture else ""
    _record_failure(self, failures, "standard audio restore", standard)

    retries = build_audio_mux_retries(command)
    for index, (label, candidate) in enumerate(retries, 1):
        self._log(f"ffmpeg audio restore retry {index}/{len(retries)}: {label}")
        completed = _run_mux_attempt(candidate, bool(capture))
        if completed.returncode == 0:
            if _looks_like_ancient_ffmpeg(failures):
                self._log("ffmpeg compatibility note: detected a legacy FFmpeg build; portable mux path succeeded.")
            self._log(f"ffmpeg audio restore recovered with {label}.")
            return (completed.stdout or "").strip() if capture else ""
        _record_failure(self, failures, label, completed)

    output = Path(command[-1])
    audio_temp = _recovery_temp_audio(output)
    try:
        detached = build_detached_audio_commands(command, audio_temp)
        if detached:
            label, extract_command = detached[0]
            self._log("ffmpeg recovery: detaching source audio with packet copy (no AAC encoder required).")
            extracted = _run_mux_attempt(extract_command, False)
            if extracted.returncode == 0 and audio_temp.exists() and audio_temp.stat().st_size > 0:
                label, remux_command = detached[1]
                remuxed = _run_mux_attempt(remux_command, bool(capture))
                if remuxed.returncode == 0:
                    self._log("ffmpeg audio restore recovered after detached-audio packet copy.")
                    return (remuxed.stdout or "").strip() if capture else ""
                _record_failure(self, failures, label, remuxed)

                rebuild = build_frame_rebuild_command(self, command, audio_temp)
                if rebuild:
                    self._log(
                        "ffmpeg recovery: rebuilding final MP4 from completed styled frames "
                        "(CPU encode only; source audio packet copy; no GPU rerender)."
                    )
                    rebuilt = _run_mux_attempt(rebuild, bool(capture))
                    if rebuilt.returncode == 0:
                        self._log("ffmpeg audio restore recovered by rebuilding from styled frames.")
                        return (rebuilt.stdout or "").strip() if capture else ""
                    _record_failure(self, failures, "styled-frame rebuild with audio copy", rebuilt)
            else:
                _record_failure(self, failures, label, extracted)
    finally:
        audio_temp.unlink(missing_ok=True)

    diagnostic = _write_diagnostic_log(self, failures)
    final_label, final_code, final_detail = failures[-1]
    compatibility_note = (
        " ComicFrame detected an extremely old FFmpeg build; install/update FFmpeg if this compatibility path also fails."
        if _looks_like_ancient_ffmpeg(failures)
        else ""
    )
    log_note = f" Full diagnostics: {diagnostic}" if diagnostic is not None else ""
    raise RuntimeError(
        "ffmpeg still could not build the final MP4 after all automatic recovery paths. "
        "The completed styled frames are preserved, so the render does not need to be repeated."
        f"{compatibility_note} Last failure: {final_label} (exit {final_code}).{log_note}\n\n{final_detail}"
    )


def install_ffmpeg_mux_fix() -> None:
    if getattr(_BaseStudio, _PATCH_FLAG, False):
        return
    if not hasattr(_BaseStudio, _ORIGINAL_RUN_ATTR):
        setattr(_BaseStudio, _ORIGINAL_RUN_ATTR, _BaseStudio._run)
    _BaseStudio._run = _run_with_mux_recovery
    setattr(_BaseStudio, _PATCH_FLAG, True)


install_ffmpeg_mux_fix()
