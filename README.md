# ComicFrame Studio

ComicFrame Studio is a local desktop GUI for turning ordinary video into frame-accurate AI-stylized animation through an AUTOMATIC1111/Forge-compatible Stable Diffusion WebUI API.

The original video is never overwritten.

## Current version: v1.7

v1.7 adds **pipeline-aware style packs** on top of the ControlNet-first video-lock engine introduced in v1.6.

A style is no longer just a prompt. Applying one can change:

- positive and negative prompts
- img2img denoise, steps and CFG
- ControlNet weight and guidance end
- temporal-lock strength and thresholds
- Graphic Print Finish intensity/components
- deterministic style-specific final grading
- inference-resolution preference

The bundled library now includes:

- **Video Fidelity · RTX 3060**
- **Graphic Shock · maximum print**
- **Comic Punch · strong**
- **Clean Graphic Novel**
- **Neo-Noir**
- **Cyberpunk Print**
- **Pulp Horror**
- **Retro 70s Print**
- **Manga Motion**
- **Dream Collapse**
- **Corporate Propaganda**
- **Analog Broadcast**
- **Structure First · ControlNet test**
- **Diffusion Only · diagnostic**

See [STYLES.md](STYLES.md) for the intended use and behavior of each style.

## Pipeline

```text
source video
    ↓
ffmpeg frame extraction
    ↓
SDXL img2img
    + Canny ControlNet structural anchor
    + optional illustration/comic LoRA
    ↓
ComicFrame Graphic Print Finish
    ↓
style-specific deterministic grade
    ↓
motion-aware temporal lock
    ↓
video reassembly at source FPS
    ↓
original audio restoration
```

The important split is deliberate: diffusion redraws the frame, ControlNet protects source geometry, deterministic finishing supplies stable print language, and temporal lock suppresses neighboring-frame shimmer in visually stable regions.

## Source layout

```text
app.py                       canonical launcher / runtime composition
comicframe_app.py            render policy and core look controls
comicframe_ui.py             desktop UI, WebUI discovery, previews
comicframe_studio.py         stable frame/video/API core
comicframe_controlnet.py     direct ControlNet endpoint discovery
comicframe_controlnet_compat.py  ControlNet v3 API compatibility normalization
comicframe_preflight.py      race-safe ControlNet/GPU preflight
comicframe_video_lock.py     ControlNet-first continuity + temporal lock
comicframe_fx.py             shared deterministic graphic-print finishing
comicframe_styles.py         v1.7 pipeline-aware style packs and style finishers
```

Historical changes live in [CHANGELOG.md](CHANGELOG.md).

## Requirements

- Python 3.10+
- `ffmpeg` and `ffprobe` on `PATH`
- a running AUTOMATIC1111/Forge-compatible Stable Diffusion WebUI API
- `sd-webui-controlnet` for the normal production path
- an SDXL-compatible Canny ControlNet model
- optional: SDXL illustration/comic LoRAs

Install ComicFrame dependencies:

```powershell
py -m pip install -r requirements.txt
```

A1111 should normally be launched with API support:

```text
--api
```

For roughly 8–16 GB VRAM with SDXL, a useful starting point is:

```text
--api --medvram-sdxl
```

Default API address:

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

The canonical window title for this build is:

```text
ComicFrame Studio 1.7 · Style Packs + ControlNet Video Lock
```

## Recommended first test

For a source-faithful test on an RTX 3060-class system:

```text
Preset:          Video Fidelity · RTX 3060
Checkpoint:      SDXL-family checkpoint
Sampler:         DPM++ 2M
Inference:       1024 long edge
Seed:            fixed
ControlNet:      ON / required
Module:          canny
Model:           diffusers_xl_canny_mid
Weight:          0.95
Guidance end:    0.92
Temporal lock:   ON
Temporal strength: 0.35
Frames:          20–60 for a useful continuity test
```

For a cleaner talking-head or product shot, try **Clean Graphic Novel**. For exaggerated product-ad comedy, try **Corporate Propaganda**. For the most unstable digital-alienation look, try **Dream Collapse** or **Graphic Shock · maximum print**.

## ControlNet

ControlNet is the default production path in v1.7. Canny anchors:

- body silhouette and pose
- face/head placement
- product and prop edges
- furniture and wall geometry
- camera composition

The recommended SDXL model remains:

```text
diffusers_xl_canny_mid.safetensors
```

Use a smaller compatible variant if VRAM is tight. Full setup details are in [CONTROLNET.md](CONTROLNET.md).

ComicFrame directly probes ControlNet's `/controlnet/*` routes and normalizes current v3 enum values before submitting img2img requests.

## GPU behavior

ComicFrame probes A1111's CUDA memory report before production renders.

- **8 GiB or more**: 1024 long-edge inference is the normal recommendation.
- **Below 8 GiB**: ComicFrame forces the 768 long-edge low-VRAM ControlNet profile.

Inference resolution changes diffusion workload, not framing. The complete source frame is resized proportionally and the assembled output can be upscaled back to the original source resolution.

## Graphic Print Finish

The shared deterministic finishing stack runs after diffusion and can provide:

- reinforced ink edges
- posterized color/shadow blocks
- shadow-weighted halftone dots
- controlled CMYK-like channel misregistration
- print grain

Style packs can enable/disable these components independently and add a deterministic final grade. This is why **Neo-Noir**, **Manga Motion**, **Retro 70s Print**, and **Analog Broadcast** look materially different even when they use the same underlying SDXL checkpoint.

## LoRA support

ComicFrame queries A1111's LoRA API during **Sync WebUI**. Installed LoRAs appear under **Style LoRA** and are injected using normal A1111 syntax:

```text
<lora:MODEL_NAME:WEIGHT>
```

ComicFrame does not ship third-party model weights. Prefer SDXL LoRAs trained for illustration, ink, comic art, print, or stylized animation rather than photoreal LoRAs.

## Temporal lock

The v1.6+ temporal lock compares consecutive source frames and reuses the previous stylized frame only where the source remains visually stable.

- moving regions stay current
- static regions receive a controlled previous-frame contribution
- hard scene cuts bypass temporal blending
- style-specific finishing is applied before the temporal lock, so the lock stabilizes the actual chosen look

This is intentionally conservative. It is not optical-flow warping; large camera pans and fast movement naturally reduce how much stabilization is applied.

## Resume behavior

Full renders are resume-safe only when the render profile matches. ComicFrame records:

- app version
- checkpoint
- sampler/scheduler
- prompts
- diffusion strength
- seed behavior
- LoRA + LoRA weight
- ControlNet configuration
- inference resolution
- output scaling choice
- Graphic Print Finish settings
- temporal-lock parameters
- selected style-pack name and deterministic finish family

If those change, resume is blocked rather than silently mixing incompatible frames.

Test renders deliberately regenerate the requested range using the controls currently visible in the UI.

## Stable Diffusion errors

ComicFrame turns common backend failures into actionable errors:

- `NansException` → lower inference resolution, try upcast cross attention, then precision changes.
- `CUDA out of memory` → lower inference resolution, use `--medvram-sdxl`, and avoid full-precision SDXL unless required.
- ControlNet enum validation errors → current builds normalize legacy numeric ControlNet values to the string enums expected by ControlNet v3.

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## Project output

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
