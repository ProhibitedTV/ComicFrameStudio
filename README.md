# ComicFrame Studio

ComicFrame Studio is a local desktop GUI for turning ordinary video into frame-accurate AI-stylized animation through an AUTOMATIC1111/Forge-compatible Stable Diffusion WebUI API.

The project is built around an inspectable pipeline:

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
- actionable Stable Diffusion NaN diagnostics

The stable launcher is now `app.py`; versioned implementation files can evolve without changing shortcuts or launch scripts.

## Why inference resolution is separate from output resolution

A 1920x1080 source no longer has to be diffused natively at 1920x1080.

The recommended v1.4 workflow is:

```text
1920x1080 source frame
        ↓
resize the complete frame to 1280x720
        ↓
Stable Diffusion img2img
        ↓
optional Lanczos upscale to 1920x1080
        ↓
final video
```

Nothing is cropped and the complete composition is preserved. Lower inference resolution substantially reduces GPU load and helps avoid numerical failures in SDXL.

Available modes:

```text
1280 long edge · recommended
1024 long edge · fast / stable
768 long edge · emergency / low VRAM
Source / native · heavy
```

## Requirements

- Python 3.10+
- `ffmpeg` and `ffprobe` on `PATH`
- a running Stable Diffusion WebUI with an AUTOMATIC1111/Forge-compatible API
- optional: `sd-webui-controlnet`

Install ComicFrame's Python dependencies:

```powershell
py -m pip install -r requirements.txt
```

A1111 should normally be launched with API support, e.g.:

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
7. Leave inference at **1280 long edge** initially.
8. Render a short test range.
9. Inspect the live styled preview and `test_frames/`.
10. Start the full render when satisfied.

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
Inference:      1280 long edge
ControlNet:     off unless configured
```

If the result is too close to the source, increase style strength gradually. If identity or geometry becomes unstable, reduce style strength.

A fixed seed is recommended because neighboring source frames already provide motion; reusing the seed encourages similar stylistic decisions frame to frame.

## ControlNet

ControlNet is **optional**. ComicFrame works with ordinary `img2img` without it.

For this project, Canny/Lineart ControlNet is useful when aggressive stylization begins changing room geometry, pose, or object edges. ComicFrame only enables it when the running WebUI exposes usable ControlNet models.

If ControlNet is failing to load, keep it disabled and see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## Resume behavior

Full renders are resume-safe **only when the render profile matches**. ComicFrame records the checkpoint, sampler, scheduler, prompts, strength, seed, ControlNet settings, inference mode, and output-scaling choice that created the frame set. If those settings change, resume is blocked rather than silently mixing incompatible frames into one video.

Test renders behave differently by design: the requested test range is regenerated with the settings currently visible in the UI, so stale test frames do not masquerade as new results.

## Stable Diffusion errors

If the WebUI returns `NansException` / `tensor with NaNs`, ComicFrame v1.4 reports practical recovery steps instead of a raw HTTP error. Start by lowering inference resolution before suppressing NaN checks.

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for the A1111/NumPy/MediaPipe/ControlNet issues encountered during real development testing.

## Development

CI installs the small ComicFrame dependency set and compiles every Python source file.

Version history is tracked in [CHANGELOG.md](CHANGELOG.md). Future work is tracked in [ROADMAP.md](ROADMAP.md).

## License

No license has been selected yet.
