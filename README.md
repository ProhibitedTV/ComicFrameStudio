# ComicFrame Studio

ComicFrame Studio is a local desktop GUI for frame-accurate AI video stylization with a Stable Diffusion WebUI API.

The pipeline is intentionally simple and inspectable:

1. Probe the source video with `ffprobe`.
2. Extract every source frame with `ffmpeg`.
3. Send each frame through Stable Diffusion `img2img`.
4. Optionally apply ControlNet for structural continuity.
5. Save every rendered frame individually.
6. Resume long renders by skipping completed frames.
7. Reassemble the styled frames at the original source FPS.
8. Restore the source audio and write `FINAL_STYLED.mp4`.

The app preserves the full source frame and aspect ratio by default. A 1920x1080 source is submitted to img2img as 1920x1080 rather than intentionally cropping or reframing the shot.

## Current status

The first live v1 test confirmed that the extraction/render/reassembly architecture works. The initial default render was structurally stable but **far too weak stylistically**: at `0.30` denoise with a photoreal-oriented checkpoint and no selected ControlNet model, the result looked close to lightly repainted source footage rather than a strong comic animation treatment.

### v1.2 WebUI-driven discovery

v1.2 stops guessing which ControlNet API routes a particular WebUI build exposes.

Click **Discover WebUI** and ComicFrame Studio first asks the running Stable Diffusion server for:

```text
/openapi.json
/sdapi/v1/options
/sdapi/v1/sd-models
```

The OpenAPI document is then used to enumerate the **actual GET routes exposed by that exact WebUI instance**. ComicFrame searches those advertised routes for ControlNet/control-model and module/preprocessor inventories, queries the matching endpoints, and fills the ControlNet dropdowns from the returned data.

This also gives useful diagnostics:

- all Stable Diffusion checkpoints reported by the core WebUI API
- the currently loaded checkpoint when available
- every control-related API route advertised by the running server
- the exact route selected for ControlNet model/module discovery
- HTTP results for each discovery request

Core Stable Diffusion checkpoints are shown for diagnostics only; they are **not incorrectly treated as ControlNet models**.

If no ControlNet routes are advertised by `/openapi.json`, ComicFrame disables ControlNet and allows an intentional plain-img2img baseline. If control routes exist but their response shape cannot yet be parsed, the log prints those exact routes so support can be added without guessing.

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

Forge and other WebUI variants may also work if they expose compatible API routes.

## Launch

Windows:

```text
run_comicframe_studio.bat
```

Or directly:

```bash
python comicframe_studio_v1_1.py
```

(The compatibility-layer filename remains `v1_1` for now; the window/behavior is v1.2.)

## Recommended workflow

1. Select a source video and project directory.
2. Start the Stable Diffusion WebUI.
3. Click **Test API**.
4. Click **Discover WebUI**.
5. Review the log and select the discovered ControlNet model/module if available.
6. Render a short test range.
7. Inspect `test_frames/`.
8. When satisfied, click **FULL RENDER**.

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

- Named style presets and a simpler stylization-strength control
- Built-in original-vs-styled test video generation
- Checkpoint selection from the discovered `/sdapi/v1/sd-models` inventory
- Better model-family compatibility feedback (SD1.5 / SDXL / SD3.x)
- Temporal conditioning / optical-flow-assisted consistency
- Keyframe + propagation workflows
- Optional proxy-resolution render and controlled upscale
- Better render ETA, throughput, and GPU telemetry
- Shot-aware processing

## License

No license has been selected yet.
