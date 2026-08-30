#!/usr/bin/env python3
"""Targeted ffmpeg audio-remux recovery for ComicFrame Studio.

Long renders should not be lost because the final ``styled_silent.mp4`` + source
audio mux hits one of ffmpeg's timestamp/interleave edge cases. The canonical
v2.9 assembler is intentionally left alone; this module patches only the shared
``_run`` boundary and only intercepts the final audio-restore command shape.

Normal ffmpeg commands continue through the original runner unchanged. For the
final remux we capture stderr, try conservative stream-copy/AAC repairs, detach
and normalize the source audio, and finally rebuild the final MP4 directly from
the lossless styled-frame concat if necessary. Completed GPU frames are never
discarded by this recovery layer.
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Iterable, Sequence

from comicframe_studio import ComicFrameStudio as _BaseStudio

FFMPEG_MUX_FIX_VERSION = "1.1"
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


def build_audio_mux_retries(args: Sequence[object] | Iterable[object]) -> list[tuple[str, list[str]]]:
    """Build conservative remux retries without touching the encoded video stream."""
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
    """Normalize source audio independently, then retry muxing it with the styled video."""
    parts = _parts(args)
    inputs = _option_values(parts, "-i")
    if len(inputs) < 2:
        return []
    silent, source = inputs[0], inputs[1]
    output = parts[-1]
    duration = _last_option_value(parts, "-t")

    extract = [
        "ffmpeg", "-y", "-fflags", "+genpts",
        "-i", source,
        "-map", "0:a:0", "-vn",
        "-c:a", "aac", "-b:a", "192k",
        "-af", "aresample=async=1:first_pts=0",
        "-movflags", "+faststart",
        str(audio_temp),
    ]

    remux = [
        "ffmpeg", "-y", "-fflags", "+genpts",
        "-i", silent, "-i", str(audio_temp),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "copy",
        "-max_muxing_queue_size", "8192",
        "-avoid_negative_ts", "make_zero",
    ]
    if duration:
        remux += ["-t", duration]
    remux += ["-movflags", "+faststart", output]

    return [
        ("detached source-audio normalization", extract),
        ("detached-audio remux", remux),
    ]


def build_frame_rebuild_command(self, args: Sequence[object] | Iterable[object], audio_temp: Path) -> list[str] | None:
    """Rebuild the MP4 from lossless styled frames when stream-copy timestamps are unusable."""
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
        "-af", "aresample=async=1:first_pts=0",
        "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-max_muxing_queue_size", "8192",
        "-avoid_negative_ts", "make_zero",
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
        _record_failure(self, failures, label, completed)

    output = Path(command[-1])
    audio_temp = _recovery_temp_audio(output)
    try:
        detached = build_detached_audio_commands(command, audio_temp)
        if detached:
            label, extract_command = detached[0]
            self._log("ffmpeg recovery: detaching and normalizing source audio.")
            extracted = _run_mux_attempt(extract_command, False)
            if extracted.returncode == 0 and audio_temp.exists() and audio_temp.stat().st_size > 0:
                label, remux_command = detached[1]
                remuxed = _run_mux_attempt(remux_command, bool(capture))
                if remuxed.returncode == 0:
                    self._log("ffmpeg audio restore recovered after detached-audio normalization.")
                    return (remuxed.stdout or "").strip() if capture else ""
                _record_failure(self, failures, label, remuxed)

                rebuild = build_frame_rebuild_command(self, command, audio_temp)
                if rebuild:
                    self._log(
                        "ffmpeg recovery: rebuilding final MP4 from completed styled frames "
                        "(CPU encode only; no GPU rerender)."
                    )
                    rebuilt = _run_mux_attempt(rebuild, bool(capture))
                    if rebuilt.returncode == 0:
                        self._log("ffmpeg audio restore recovered by rebuilding from styled frames.")
                        return (rebuilt.stdout or "").strip() if capture else ""
                    _record_failure(self, failures, "lossless styled-frame rebuild", rebuilt)
            else:
                _record_failure(self, failures, label, extracted)
    finally:
        audio_temp.unlink(missing_ok=True)

    diagnostic = _write_diagnostic_log(self, failures)
    final_label, final_code, final_detail = failures[-1]
    log_note = f" Full diagnostics: {diagnostic}" if diagnostic is not None else ""
    raise RuntimeError(
        "ffmpeg still could not build the final MP4 after all automatic recovery paths. "
        "The completed styled frames are preserved; do not rerender them. "
        f"Last failure: {final_label} (exit {final_code}).{log_note}\n\n{final_detail}"
    )


def install_ffmpeg_mux_fix() -> None:
    if getattr(_BaseStudio, _PATCH_FLAG, False):
        return
    if not hasattr(_BaseStudio, _ORIGINAL_RUN_ATTR):
        setattr(_BaseStudio, _ORIGINAL_RUN_ATTR, _BaseStudio._run)
    _BaseStudio._run = _run_with_mux_recovery
    setattr(_BaseStudio, _PATCH_FLAG, True)


install_ffmpeg_mux_fix()
