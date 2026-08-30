from __future__ import annotations

import subprocess
from pathlib import Path

import comicframe_ffmpeg_fix as fix


MUX_COMMAND = [
    "ffmpeg", "-y",
    "-i", r"C:\project\styled_silent.mp4",
    "-i", r"C:\camera\source.mp4",
    "-map", "0:v:0", "-map", "1:a:0?",
    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
    "-t", "21.557778000", "-movflags", "+faststart",
    r"C:\project\.FINAL_STYLED.temp.mp4",
]


class DummyRunner:
    def __init__(self):
        self.logs: list[str] = []

    def _log(self, text):
        self.logs.append(str(text))


def test_detects_only_final_audio_restore_shape():
    assert fix.is_audio_restore_command(MUX_COMMAND)
    assert not fix.is_audio_restore_command(["ffmpeg", "-y", "-i", "frames.ffconcat", "out.mp4"])
    assert not fix.is_audio_restore_command(["ffprobe", "-i", "source.mp4"])


def test_legacy_stream_copy_avoids_aac_encoder_and_modern_only_options():
    command = fix.build_legacy_stream_copy_command(MUX_COMMAND)
    assert command[command.index("-c:v") + 1] == "copy"
    assert command[command.index("-c:a") + 1] == "copy"
    assert "-b:a" not in command
    assert "-max_muxing_queue_size" not in command
    assert "-avoid_negative_ts" not in command


def test_audio_mux_retries_start_portable_then_add_modern_and_legacy_repairs():
    retries = dict(fix.build_audio_mux_retries(MUX_COMMAND))

    copied = retries["legacy-safe source-audio stream copy"]
    assert copied[copied.index("-c:v") + 1] == "copy"
    assert copied[copied.index("-c:a") + 1] == "copy"
    assert "-b:a" not in copied
    assert "-max_muxing_queue_size" not in copied

    guarded = retries["larger mux queue + timestamp normalization"]
    assert guarded[guarded.index("-c:v") + 1] == "copy"
    assert guarded[guarded.index("-c:a") + 1] == "copy"
    assert guarded[guarded.index("-max_muxing_queue_size") + 1] == "4096"
    assert guarded[guarded.index("-avoid_negative_ts") + 1] == "make_zero"

    repaired = retries["AAC timestamp repair"]
    assert repaired[repaired.index("-c:a") + 1] == "aac"
    assert repaired[repaired.index("-af") + 1] == "aresample=async=1:first_pts=0"
    assert "-shortest" in repaired

    legacy_aac = retries["legacy AAC encoder compatibility"]
    assert legacy_aac[legacy_aac.index("-c:a") + 1] == "aac"
    assert legacy_aac[legacy_aac.index("-strict") + 1] == "-2"
    assert "-max_muxing_queue_size" not in legacy_aac


def test_detached_audio_recovery_uses_packet_copy_only(tmp_path: Path):
    audio_temp = tmp_path / "normalized.m4a"
    commands = dict(fix.build_detached_audio_commands(MUX_COMMAND, audio_temp))

    extract = commands["detached source-audio packet copy"]
    assert extract[extract.index("-map") + 1] == "0:a:0"
    assert extract[extract.index("-c:a") + 1] == "copy"
    assert "-af" not in extract
    assert "-b:a" not in extract
    assert extract[-1] == str(audio_temp)

    remux = commands["detached-audio legacy-safe remux"]
    assert remux[remux.index("-c:v") + 1] == "copy"
    assert remux[remux.index("-c:a") + 1] == "copy"
    assert "-max_muxing_queue_size" not in remux
    assert remux[remux.index("-t") + 1] == "21.557778000"


def test_ancient_ffmpeg_signature_is_detected():
    failures = [
        (
            "standard audio restore",
            1,
            "ffmpeg version N-55702-g920046a Copyright (c) 2000-2013 the FFmpeg developers\n"
            "The encoder 'aac' is experimental but experimental codecs are not enabled",
        )
    ]
    assert fix._looks_like_ancient_ffmpeg(failures)


def test_mux_runner_recovers_on_first_portable_retry(monkeypatch):
    attempts: list[list[str]] = []

    def fake_run(command, capture):
        attempts.append(list(command))
        if len(attempts) == 1:
            return subprocess.CompletedProcess(
                command,
                1,
                stdout="",
                stderr="The encoder 'aac' is experimental but experimental codecs are not enabled",
            )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(fix, "_run_mux_attempt", fake_run)
    runner = DummyRunner()
    assert fix._run_with_mux_recovery(runner, MUX_COMMAND, capture=False) == ""
    assert len(attempts) == 2
    recovered = attempts[1]
    assert recovered[recovered.index("-c:a") + 1] == "copy"
    assert "-max_muxing_queue_size" not in recovered
    assert any("legacy-safe source-audio stream copy" in line for line in runner.logs)


def test_mux_runner_surfaces_ffmpeg_stderr_after_all_retries(monkeypatch):
    def fake_run(command, capture):
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="Too many packets buffered for output stream 0:0")

    monkeypatch.setattr(fix, "_run_mux_attempt", fake_run)
    runner = DummyRunner()
    try:
        fix._run_with_mux_recovery(runner, MUX_COMMAND, capture=False)
    except RuntimeError as exc:
        text = str(exc)
        assert "render does not need to be repeated" in text
        assert "Too many packets buffered" in text
    else:
        raise AssertionError("expected RuntimeError")
