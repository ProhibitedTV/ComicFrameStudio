"""Real CPU media checks; GPU/backend independent, with generated footage."""

from __future__ import annotations

import json
import shutil
import subprocess
from types import SimpleNamespace

import pytest

import app  # noqa: F401 - installs the canonical FFmpeg boundary
from comicframe_media import ensure_project_owned
from comicframe_runtime_v29 import ComicFrameStudioApp as Runtime
from comicframe_studio import ComicFrameStudio


class Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


pytestmark = pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="ffmpeg + ffprobe required",
)


@pytest.mark.parametrize("variable", [False, True])
def test_real_source_timing_reconstruction_audio_and_atomic_failure(tmp_path, variable):
    source = tmp_path / "input with spaces.mp4"
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        "testsrc2=s=384x216:r=25:d=1.2",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:duration=2.4",
    ]
    if variable:
        command += [
            "-vf",
            r"setpts=if(lt(N\,15)\,N\,15+3*(N-15))/(25*TB)",
            "-fps_mode",
            "vfr",
        ]
    command += ["-c:v", "libx264", "-c:a", "aac", "-shortest", str(source)]
    subprocess.run(command, check=True, capture_output=True)
    source_before = source.read_bytes()
    root = tmp_path / "owned project"
    ensure_project_owned(root)
    paths = ComicFrameStudio.project_paths(SimpleNamespace(work_var=Var(str(root))))
    paths.update(
        timing_dir=root / "cache" / "timing",
        source_timing=root / "cache" / "timing" / "source_timing.json",
        styled_concat=root / "cache" / "timing" / "styled.ffconcat",
    )
    for name in ("frames", "styled"):
        paths[name].mkdir()
    runner = SimpleNamespace(
        video_var=Var(str(source)),
        _workspace_partial_render=False,
        _audit2_timing=None,
        _log=lambda *_: None,
        _set_progress=lambda *_: None,
    )
    runner.project_paths = lambda: paths
    runner._run = lambda args, capture=False: ComicFrameStudio._run(
        runner, args, capture
    )
    runner._ffprobe_json = lambda path: json.loads(
        runner._run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(path),
            ],
            True,
        )
    )
    runner._audit2_temp_media = Runtime._audit2_temp_media
    runner._audit2_validate_media = lambda *args, **kwargs: (
        Runtime._audit2_validate_media(runner, *args, **kwargs)
    )
    runner._hardening_final_dimensions = lambda info: (info["width"], info["height"])
    # Exercise the engine's existing legacy command through the compatibility boundary.
    runner._run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-vsync",
            "0",
            str(paths["frames"] / "frame_%06d.png"),
        ]
    )
    frames = sorted(paths["frames"].glob("frame_*.png"))
    assert len(frames) == 30
    for frame in frames:
        shutil.copyfile(frame, paths["styled"] / frame.name)
    timing = Runtime._audit2_probe_timing(
        runner, source, {"fps": 25}, len(frames), "fixture"
    )
    assert timing["variable"] is variable
    # A corrupt checkpoint must fail before replacing an existing final video.
    paths["final"].write_bytes(b"previous validated result")
    corrupt = paths["styled"] / frames[5].name
    corrupt.write_bytes(b"partial cached PNG")
    with pytest.raises(RuntimeError, match="corrupt"):
        Runtime._assemble(runner, {"width": 384, "height": 216, "fps": 25})
    assert paths["final"].read_bytes() == b"previous validated result"
    shutil.copyfile(frames[5], corrupt)
    Runtime._assemble(runner, {"width": 384, "height": 216, "fps": 25})
    result = runner._ffprobe_json(paths["final"])
    assert {s["codec_type"] for s in result["streams"]} == {"video", "audio"}
    assert abs(float(result["format"]["duration"]) - timing["total_duration"]) < 0.15
    video = next(s for s in result["streams"] if s["codec_type"] == "video")
    assert int(video["nb_frames"]) == len(frames)
    assert (int(video["width"]), int(video["height"])) == (384, 216)
    assert source.read_bytes() == source_before
    assert not list(root.glob(".*.mp4"))
