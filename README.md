# ComicFrame Studio

ComicFrame Studio is a local desktop GUI for turning ordinary video into frame-accurate AI-stylized animation through an AUTOMATIC1111/Forge-compatible Stable Diffusion WebUI API.

The pipeline is intentionally inspectable:

1. Probe the source video with `ffprobe`.
2. Extract every source frame with `ffmpeg`.
3. Run each frame through Stable Diffusion `img2img`.
4. Optionally use ControlNet for stronger structural guidance.
5. Save every styled frame individually and resume safely after interruption.
6. Reassemble the sequence at the original FPS.
7. Restore the source audio.

The original video is never overwritten.

## Current version: v1.4

v1.4 focuses on reliability and practical video rendering:

- dark two-pane desktop UI
- WebUI-native checkpoint/sampler/scheduler discovery
- checkpoint switching from inside ComicFrame
- comic look presets and editable prompts
- source + live latest-frame previews
- optional ControlNet integration
- adaptive inference resolution
- optional upscale back to source resolution
- profile-aware resume-safe long renders
- actionable Stable Diffusion NaN and CUDA out-of-memory diagnostics

## Consolidated source layout

Runtime code no longer uses version-numbered implementation filenames.

```text
app.py                 stable launcher / entrypoint
comicframe_app.py      current render policy and v1.4 behavior
comicframe_ui.py       desktop UI, WebUI discovery, previews, presets
comicframe_studio.py   stable frame/video/API core
```

Historical behavior belongs in `CHANGELOG.md`, not in a chain of `*_v1_1.py`, `*_v1_3.py`, etc.

## Why inference resolution is separate from output resolution

A 1920x1080 source does not need to be diffused natively at 1920x1080.

Recommended workflow:

```text
1920x1080 source frame
        ↓
resize the complete frame to 1280x720 (or 1024/768 long edge)
        ↓
Stable Diffusion img2img
        ↓
optional Lanczos upscale to 1920x1080
        ↓
final video
```

Nothing is cropped and the complete composition is preserved. Lower inference resolution substantially reduces GPU load and helps avoid SDXL numerical and memory failures.

Available modes:

```text
1280 long edge · recommended
1024 long edge · fast / stable
768 long edge · emergency / low VRAM
Source / native · heavy
```

For a 12 GB GPU running SDXL, **1024 long edge is the safer first render**. Move to 1280 after the pipeline is stable.

## Requirements

- Python 3.10+
- `ffmpeg` and `ffprobe` on `PATH`
- a running Stable Diffusion WebUI with an AUTOMATIC1111/Forge-compatible API
- optional: `sd-webui-controlnet`

Install ComicFrame's Python dependencies:

```powershell
py -m pip install -r requirements.txt
```

A1111 should normally be launched with API support:

```text
--api
```

The default API address is:

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
py app.py
```

## Recommended workflow

1. Start Stable Diffusion WebUI.
2. Launch ComicFrame Studio.
3. Select the source video and project directory.
4. Click **Sync WebUI**.
5. Choose a checkpoint and sampler.
6. Pick/apply a look preset.
7. Start at **1024 long edge** on a 12 GB SDXL setup, or 1280 if memory headroom is known-good.
8. Render a short test range.
9. Inspect the live styled preview and `test_frames/`.
10. Enable ControlNet only after plain img2img renders correctly.
11. Start the full render when satisfied.

Project output includes:

```text
frames/
styled_frames/
test_frames/
source_info.json
render_settings.json
comicframe_profile.json
comicframe_test_profile.json
styled_silent.mp4
FINAL_STYLED.mp4
```

## Good starting settings

The **Comic Punch** preset starts around:

```text
Steps:          28
CFG:            6.5
Style strength: 0.48
Seed:           123456
Seed behavior:  fixed
Inference:      1024–1280 long edge
ControlNet:     off until configured
```

If the result is too close to the source, increase style strength gradually. If identity or geometry becomes unstable, reduce style strength or enable structural guidance.

A fixed seed is recommended because neighboring source frames already provide motion; reusing the seed encourages similar stylistic decisions frame to frame.

## ControlNet

ControlNet is **optional**. ComicFrame works with ordinary `img2img` without it.

For this project, Canny ControlNet is useful when aggressive stylization begins changing room geometry, pose, or object edges.

For SDXL, the recommended first model is:

```text
diffusers_xl_canny_mid.safetensors
```

Use the SMALL variant if VRAM is tight. Full installation instructions, download sources, model locations, and first settings are in [CONTROLNET.md](CONTROLNET.md).

## Resume behavior

Full renders are resume-safe **only when the render profile matches**. ComicFrame records the checkpoint, sampler, scheduler, prompts, strength, seed, ControlNet settings, inference mode, and output-scaling choice that created the frame set. If those settings change, resume is blocked rather than silently mixing incompatible frames into one video.

Test renders behave differently by design: the requested test range is regenerated with the settings currently visible in the UI, so stale test frames do not masquerade as new results.

## Stable Diffusion errors

ComicFrame turns common backend failures into actionable errors:

- `NansException` / tensor with NaNs → lower inference resolution, try upcast cross attention, then consider precision changes.
- `CUDA out of memory` → lower inference resolution and avoid full-precision SDXL unless required.

For 8–16 GB SDXL systems, `--medvram-sdxl` is a useful A1111 option. See [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## Development

CI installs the small ComicFrame dependency set and compiles every Python source file.

Version history is tracked in [CHANGELOG.md](CHANGELOG.md). Future work is tracked in [ROADMAP.md](ROADMAP.md).

## License

No license has been selected yet.
