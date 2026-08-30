from __future__ import annotations

import subprocess

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


def test_audio_mux_retries_preserve_video_and_add_guards():
    retries = dict(fix.build_audio_mux_retries(MUX_COMMAND))

    guarded = retries["larger mux queue + timestamp normalization"]
    assert guarded[guarded.index("-c:v") + 1] == "copy"
    assert guarded[guarded.index("-c:a") + 1] == "aac"
    assert guarded[guarded.index("-max_muxing_queue_size") + 1] == "4096"
    assert guarded[guarded.index("-avoid_negative_ts") + 1] == "make_zero"

    copied = retries["source-audio stream copy"]
    assert copied[copied.index("-c:v") + 1] == "copy"
    assert copied[copied.index("-c:a") + 1] == "copy"
    assert "-b:a" not in copied

    repaired = retries["AAC timestamp repair"]
    assert repaired[repaired.index("-c:a") + 1] == "aac"
    assert repaired[repaired.index("-af") + 1] == "aresample=async=1:first_pts=0"
    assert "-shortest" in repaired


def test_mux_runner_retries_and_recovers_without_rerender(monkeypatch):
    attempts: list[list[str]] = []

    def fake_run(command, capture):
        attempts.append(list(command))
        if len(attempts) < 3:
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="mux failed")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(fix, "_run_mux_attempt", fake_run)
    runner = DummyRunner()
    assert fix._run_with_mux_recovery(runner, MUX_COMMAND, capture=False) == ""
    assert len(attempts) == 3
    assert any("recovered with source-audio stream copy" in line for line in runner.logs)


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
