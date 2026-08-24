# ComicFrame Studio

ComicFrame Studio is a local desktop GUI for frame-accurate AI video stylization with a Stable Diffusion WebUI API.

The core pipeline is simple:

1. Probe the source video with `ffprobe`.
2. Extract every source frame with `ffmpeg`.
3. Send each frame through Stable Diffusion `img2img`.
4. Save every rendered frame individually.
5. Resume long renders by skipping completed frames.
6. Reassemble at the original source FPS.
7. Restore the source audio and write `FINAL_STYLED.mp4`.

The full source frame and aspect ratio are preserved by default.

## v1.3 — UI/UX + WebUI-native controls

v1.3 moves the app away from ControlNet-centric setup and makes the normal Stable Diffusion WebUI the primary source of truth.

### WebUI sync

ComicFrame now populates controls directly from the running WebUI:

```text
/sdapi/v1/options
/sdapi/v1/sd-models
/sdapi/v1/samplers
/sdapi/v1/schedulers   (when exposed)
/openapi.json
```

The UI provides:

- a real **Checkpoint** dropdown sourced from `/sdapi/v1/sd-models`
- a real **Sampler** dropdown sourced from `/sdapi/v1/samplers`
- a **Scheduler** dropdown when supported by the WebUI
- automatic loading of the selected checkpoint before a render
- visible WebUI connection/model status

### Dark UI

v1.3 introduces a dark desktop interface with clearer sections for source, WebUI settings, look/style, optional continuity controls, rendering, previews, and activity logs.

### Source + output previews

The right side of the app now shows:

- a preview frame extracted from the selected source video
- the latest generated test/styled frame

This makes it possible to tune the look without constantly jumping between folders.

### Comic presets

v1.3 includes three starting presets:

- **Comic Punch (recommended)** — stronger stylization (`0.48` style strength)
- **Balanced Comic** — moderate transformation
- **Conservative / Stable** — close to the original v1 settings

The preset applies prompt, CFG, steps, and style strength, and everything remains editable afterward.

### ControlNet is optional now

ControlNet is no longer treated as a requirement.

It is an optional Stable Diffusion extension that can help lock edges, pose, and scene geometry when style strength is high. If the running WebUI does not expose ControlNet routes, ComicFrame simply disables that option and continues with normal `img2img`.

This is the expected behavior for the currently tested WebUI, which exposes the normal Stable Diffusion model/sampler API but no ControlNet API routes.

## Requirements

- Python 3.10+
- `ffmpeg` and `ffprobe` on `PATH`
- a local AUTOMATIC1111/compatible Stable Diffusion WebUI with API enabled

Install Python dependencies:

```powershell
py -m pip install -r requirements.txt
```

For AUTOMATIC1111, API support is commonly enabled in `webui-user.bat` with:

```bat
set COMMANDLINE_ARGS=--api
```

The default endpoint is:

```text
http://127.0.0.1:7860
```

## Launch

Windows:

```text
run_comicframe_studio.bat
```

Or directly:

```powershell
py comicframe_studio_v1_3.py
```

## Recommended workflow

1. Start Stable Diffusion WebUI.
2. Launch ComicFrame Studio.
3. Let **Sync WebUI** populate the checkpoint/sampler lists.
4. Select the checkpoint and sampler you want.
5. Choose a source video.
6. Apply **Comic Punch** as a first test.
7. Render 10–20 test frames.
8. Compare the source and styled previews.
9. Adjust style strength/prompt as needed.
10. Run **FULL RENDER** when satisfied.

## Project output

```text
frames/
styled_frames/
test_frames/
_source_preview.jpg
source_info.json
render_settings.json
styled_silent.mp4
FINAL_STYLED.mp4
```

The original source video is never overwritten.

## Continuity

A fixed seed remains the default because the input frames already supply the motion. Reusing the seed encourages neighboring frames to make similar visual decisions.

The current renderer still processes frames independently, so temporal shimmer is expected to become the main technical problem once the style itself is strong enough. That is the next major development target.

## Roadmap

- automatic original-vs-styled test-video assembly
- temporal consistency / prior-frame conditioning
- optical-flow-assisted guidance
- keyframe + propagation workflows
- model-family compatibility hints (SD1.5 / SDXL / SD3.x)
- proxy-resolution rendering + controlled upscale
- ETA / throughput / GPU telemetry
- shot-aware processing
- better preview scrubbing and frame comparison

## License

No license has been selected yet.
