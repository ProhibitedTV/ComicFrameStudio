from __future__ import annotations

import shutil
import subprocess
import threading
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

import comicframe_product as product
import comicframe_simple as simple
from comicframe_media import ensure_project_owned, full_file_sha256, validate_png
from comicframe_preview import RenderRequest, extract_preview_frame
from comicframe_studio import ComicFrameStudio


class Var:
    def __init__(self, value, main_thread_only=False):
        self.value, self.main_thread_only = value, main_thread_only

    def get(self):
        if self.main_thread_only:
            assert threading.current_thread() is threading.main_thread()
        return self.value

    def set(self, value):
        if self.main_thread_only:
            assert threading.current_thread() is threading.main_thread()
        self.value = value


def paths_for(root):
    return ComicFrameStudio.project_paths(SimpleNamespace(work_var=Var(str(root))))


def request_for(tmp_path):
    source = tmp_path / "source with spaces.mp4"
    source.write_bytes(b"source fixture")
    return RenderRequest(
        source, tmp_path / "source_comicframe", "Dream Rotoscope", False, 18, True
    )


def mock_decode(command):
    Image.new("RGB", (96, 64), (140, 90, 60)).save(command[-1])


def probe(_source):
    return {"width": 96, "height": 64, "fps": 24, "duration": 10}


def test_public_render_request_is_immutable(tmp_path):
    request = request_for(tmp_path)
    with pytest.raises(FrozenInstanceError):
        request.steps = 36
    assert request.engine_project == request.project / "previews" / "first_frame"


def test_first_frame_extraction_is_bounded_and_does_not_touch_full_cache(tmp_path):
    request = request_for(tmp_path)
    ensure_project_owned(request.project)
    full = request.project / "styled_frames"
    full.mkdir()
    sentinel = full / "frame_000001.png"
    sentinel.write_bytes(b"full render checkpoint")
    commands = []

    def run(command):
        commands.append(command)
        mock_decode(command)

    paths = paths_for(request.engine_project)
    info = extract_preview_frame(request, paths, run, probe, threading.Event())
    assert info["frame_count"] == 1
    assert info["source_fingerprint"] == full_file_sha256(request.source)
    assert commands[0][commands[0].index("-frames:v") + 1] == "1"
    assert sentinel.read_bytes() == b"full render checkpoint"
    extract_preview_frame(request, paths, run, probe, threading.Event())
    assert len(commands) == 1
    (paths["frames"] / "frame_000001.png").write_bytes(b"corrupt")
    extract_preview_frame(request, paths, run, probe, threading.Event())
    assert len(commands) == 2


def test_preview_cancellation_never_publishes_a_partial_frame(tmp_path):
    request = request_for(tmp_path)
    paths, stop = paths_for(request.engine_project), threading.Event()

    def run(command):
        mock_decode(command)
        stop.set()

    with pytest.raises(InterruptedError):
        extract_preview_frame(request, paths, run, probe, stop)
    assert not (paths["frames"] / "frame_000001.png").exists()
    assert not (paths["frames"] / "first_frame.part.png").exists()


def test_source_mutation_rejects_preview_and_resets_only_preview_project(tmp_path):
    request = request_for(tmp_path)
    paths = paths_for(request.engine_project)

    def run(command):
        mock_decode(command)
        request.source.write_bytes(b"different source revision")

    with pytest.raises(RuntimeError, match="changed during preview extraction"):
        extract_preview_frame(request, paths, run, probe, threading.Event())
    assert not paths["frames"].exists()
    assert (request.project / ".comicframe_project.json").exists()


def test_preview_refuses_unowned_generated_directory(tmp_path):
    request = request_for(tmp_path)
    (request.project / "frames").mkdir(parents=True)
    with pytest.raises(RuntimeError, match="not a recognized ComicFrame project"):
        extract_preview_frame(
            request,
            paths_for(request.engine_project),
            mock_decode,
            probe,
            threading.Event(),
        )


@pytest.mark.parametrize(
    "preview,outcome",
    [
        (True, "success"),
        (True, "cancel"),
        (True, "backend-error"),
        (True, "source-changed"),
        (False, "cancel"),
    ],
)
def test_preview_worker_uses_snapshot_restores_context_and_never_publishes_full_video(
    tmp_path, preview, outcome, monkeypatch
):
    request = replace(request_for(tmp_path), preview=preview)
    if not preview:
        request.project.mkdir()
        (request.project / "FINAL_STYLED.mp4").write_bytes(b"stale earlier output")
    app = SimpleNamespace(
        _simple_busy=False,
        worker=None,
        video_var=Var(str(request.source)),
        work_var=Var(str(request.project)),
        simple_process_var=Var(request.look, True),
        simple_controlnet_var=Var(False, True),
        simple_steps_var=Var(18, True),
        control_enabled_var=Var(True),
        steps_var=Var(24),
        simple_result_var=Var(""),
        progress=Var(0),
        progress_label_var=Var(""),
        stop_event=threading.Event(),
        _simple_output_path=None,
        _simple_preview_source_info=None,
    )
    callbacks, errors, calls = [], [], []
    app.after = lambda _delay, callback: callbacks.append(callback)
    app._log = lambda text: None
    app._set_progress = lambda pct, label: None
    app._simple_set_result_buttons = lambda value: None
    app._simple_set_busy = lambda value: setattr(app, "_simple_busy", value)
    app._simple_show_image = lambda path: calls.append(("show", path))
    app._simple_apply_hidden_defaults = lambda: (
        simple.ComicFrameStudioApp._simple_apply_hidden_defaults(app)
    )
    app._sync_webui = lambda: None
    app._save_director_timeline = lambda: None
    app._analyze_shots = lambda: {"shots": [{"id": 1, "start": 1, "end": 1}]}
    app.project_paths = lambda: paths_for(Path(app.work_var.get()))
    app._run, app._probe_video = mock_decode, probe

    def extract():
        if preview:
            return simple.ComicFrameStudioApp._extract_frames(app)
        app.project_paths()["test"].mkdir()
        return probe(request.source)

    app._extract_frames = extract
    app._stability_source_matches_metadata = lambda *_args: outcome != "source-changed"
    monkeypatch.setattr(
        simple.messagebox, "showerror", lambda *args: errors.append(args)
    )

    def render(start, count, test_only):
        calls.append(("render", start, count, test_only))
        assert app._simple_render_request.steps == 18
        assert app._simple_render_request.controlnet is False
        if outcome == "backend-error":
            raise RuntimeError("WebUI HTTP 503 unavailable")
        paths = app.project_paths()
        Image.new("RGB", (96, 64), "purple").save(paths["test"] / "frame_000001.png")
        if outcome == "cancel":
            app.stop_event.set()

    app._render_range = render

    def worker(job):
        app.worker = threading.Thread(target=job)
        app.worker.start()

    app._run_worker = worker
    simple.ComicFrameStudioApp._simple_start_render(app, preview)
    app.worker.join(timeout=10)
    assert not app.worker.is_alive()
    # Tk callbacks run only after returning to the main thread.
    for callback in callbacks:
        callback()
    assert app.work_var.get() == str(request.project)
    assert app._simple_render_request is None and not app._simple_busy
    assert app._simple_output_path is None
    if preview:
        assert not (request.project / "FINAL_STYLED.mp4").exists()
    else:
        assert (
            request.project / "FINAL_STYLED.mp4"
        ).read_bytes() == b"stale earlier output"
        assert not list(tmp_path.glob("*_comicframe_dream-rotoscope*.mp4"))
    if outcome == "success":
        assert ("render", 1, 1, True) in calls
        assert "actual diffusion" in app.progress_label_var.get()
        assert calls[-1][0] == "show" and validate_png(calls[-1][1])[0]
        assert not errors
    elif outcome == "cancel":
        assert "Stopped" in app.progress_label_var.get() and not errors
    else:
        assert errors
        assert not (
            request.engine_project / "previews" / "ORIGINAL_VS_STYLIZED.png"
        ).exists()


def test_controlnet_policy_uses_captured_choice_without_reading_public_tk_vars(
    tmp_path,
):
    request = request_for(tmp_path)
    app = SimpleNamespace(
        _simple_render_request=request,
        simple_controlnet_var=Var(True, True),
        control_enabled_var=Var(True),
        control_required_var=Var(True),
    )
    thread = threading.Thread(
        target=lambda: product.ComicFrameStudioApp._enforce_public_controlnet_choice(
            app
        )
    )
    thread.start()
    thread.join()
    assert (
        app.control_enabled_var.get() is False
        and app.control_required_var.get() is False
    )


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="ffmpeg + ffprobe required",
)
def test_real_ffmpeg_preview_decodes_one_frame_with_windows_spaces(tmp_path):
    source = tmp_path / "source with spaces.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=96x64:r=12:d=1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(source),
        ],
        check=True,
    )
    request = RenderRequest(
        source, tmp_path / "preview project", "Dream Rotoscope", False, 18, True
    )
    paths = paths_for(request.engine_project)
    commands = []

    def run(command):
        commands.append(command)
        subprocess.run(command, capture_output=True, check=True)

    info = extract_preview_frame(request, paths, run, probe, threading.Event())
    assert info["width"] == 96 and info["height"] == 64
    assert len(list(paths["frames"].glob("frame_*.png"))) == 1
    assert validate_png(paths["frames"] / "frame_000001.png", (96, 64))[0]
    assert "-frames:v" in commands[0]
