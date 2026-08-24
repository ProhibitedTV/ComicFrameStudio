# ComicFrame Studio

ComicFrame Studio is a local desktop GUI for frame-accurate AI video stylization with a Stable Diffusion WebUI API.

The v1 pipeline is intentionally simple and inspectable:

1. Probe the source video with `ffprobe`.
2. Extract every source frame with `ffmpeg`.
3. Send each frame through Stable Diffusion `img2img`.
4. Optionally apply ControlNet for structural continuity.
5. Save every rendered frame individually.
6. Resume long renders by skipping completed frames.
7. Reassemble the styled frames at the original source FPS.
8. Restore the source audio and write `FINAL_STYLED.mp4`.

The app preserves the full source frame and aspect ratio by default. A 1920x1080 source is submitted to img2img as 1920x1080 rather than intentionally cropping or reframing the shot.

## Current status: v1 baseline

The first live v1 test confirmed that the extraction/render/reassembly architecture works. The initial default render was structurally stable but **far too weak stylistically**: at `0.30` denoise with a photoreal-oriented checkpoint and no selected ControlNet model, the result looked close to lightly repainted source footage rather than a strong comic animation treatment.

That is now a useful baseline for v2 development. Near-term priorities include stronger style presets, preflight validation, ControlNet model warnings, easier A/B test assembly, and temporal-consistency options.

## Requirements

- Python 3.10+
- `ffmpeg` and `ffprobe` available on `PATH`
- A local Stable Diffusion WebUI exposing an AUTOMATIC1111/Forge-compatible API
- Optional but strongly recommended: ControlNet

Install Python dependencies:

```bash
python -m pip install -r requirements.txt
```

On Windows:

```powershell
py -m pip install -r requirements.txt
```

## Stable Diffusion API

AUTOMATIC1111 should be launched with API support, commonly by adding this to `webui-user.bat`:

```bat
set COMMANDLINE_ARGS=--api
```

The GUI defaults to:

```text
http://127.0.0.1:7860
```

Forge and other WebUI variants may also work if they expose compatible `/sdapi/v1/*` endpoints.

## Launch

Windows:

```text
run_comicframe_studio.bat
```

Or directly:

```bash
python comicframe_studio.py
```

## Recommended v1 workflow

1. Select a source video and project directory.
2. Start the Stable Diffusion WebUI.
3. Click **Test API**.
4. If using ControlNet, click **Refresh ControlNet** and choose a compatible model.
5. Render a short test range.
6. Inspect `test_frames/`.
7. When satisfied, click **FULL RENDER**.

Project output includes:

```text
frames/
styled_frames/
test_frames/
source_info.json
render_settings.json
styled_silent.mp4
FINAL_STYLED.mp4
```

The original source video is never overwritten.

## Original v1 defaults

```text
Steps:              24
CFG:                6
Denoise:            0.30
Seed:               123456
Seed mode:          fixed
ControlNet:         enabled
ControlNet module:  canny
ControlNet weight:  0.90
Canny low:          100
Canny high:         200
```

For a stronger comic transformation, the first parameters to test are higher denoise around `0.45`, a real selected Canny/Lineart ControlNet model, and a checkpoint tuned toward illustration/comic/cel-shaded output.

## Continuity

A fixed seed is the default because the input video frames already provide motion. Reusing the seed encourages neighboring frames to make similar stylistic decisions.

ControlNet becomes increasingly important as denoise rises. Low denoise preserves the source but can barely stylize it; high denoise increases stylistic freedom but also identity, geometry, and temporal drift.

## Resume behavior

Long renders are resume-safe. Existing nontrivial styled frames are skipped, so an interrupted full render can be restarted without beginning at frame 1.

## Roadmap

- Preflight warning when ControlNet is enabled but no model is selected
- Named style presets and a simpler stylization-strength control
- Built-in original-vs-styled test video generation
- Better checkpoint/model discovery
- Temporal conditioning / optical-flow-assisted consistency
- Keyframe + propagation workflows
- Optional proxy-resolution render and controlled upscale
- Better render ETA, throughput, and GPU telemetry
- Shot-aware processing

## License

No license has been selected yet.
