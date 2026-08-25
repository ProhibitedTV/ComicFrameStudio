# ComicFrame Studio

ComicFrame Studio is a local desktop GUI for turning ordinary video into source-faithful AI-stylized animation through an AUTOMATIC1111/Forge-compatible Stable Diffusion WebUI API.

The source video is never overwritten.

## Current version: v2.0

v2.0 adds **Shot Memory** on top of the v1.9 optical-flow engine, v1.8 artistic library, v1.7 pipeline-aware style packs, and v1.6 ControlNet-first continuity stack.

ComicFrame now attacks frame consistency in three different places:

1. **Before diffusion** — Shot Memory optical-flow warps trusted parts of the previous stylized frame into the current img2img initialization.
2. **During diffusion** — Canny ControlNet receives the untouched current source frame and anchors pose, products, architecture, silhouette and camera geometry.
3. **After diffusion** — optical-flow temporal transport warps the prior finished style into current-frame coordinates and confidence-gates the final stabilization blend.

That split is intentional: style memory can persist without becoming structural guidance.

## Pipeline

```text
source video
    ↓
ffmpeg exact frame extraction
    ↓
current source + transported Shot Memory
    ↓
SDXL img2img
    + untouched-source Canny ControlNet
    + optional style LoRA
    ↓
shared deterministic Graphic Print Finish
    ↓
style-specific deterministic finish
    ↓
Optical Flow temporal transport
    ↓
periodic per-shot reference anchor
    ↓
video reassembly at source FPS
    ↓
original audio restoration
```

## What v2.0 adds

### Shot Memory

The previous stylized frame is motion-warped into current-frame coordinates **before Stable Diffusion runs**. Only high-confidence regions contribute. Scene cuts reset memory automatically.

Periodic stabilized references are stored under:

```text
shot_memory/full/references/
```

A low-strength palette lock can also carry shot-level color language without copying anchor geometry.

See [SHOT_MEMORY.md](SHOT_MEMORY.md).

### Optical-flow temporal engines

v1.9 remains the post-diffusion continuity layer:

```text
Off
Basic
Optical Flow · Fast
Optical Flow · Quality
```

**Optical Flow · Fast** is the normal default and computes motion near a 512-pixel long edge. **Quality** uses a 768-pixel proxy and a heavier Farnebäck solve.

See [OPTICAL_FLOW.md](OPTICAL_FLOW.md).

### Artistic library

ComicFrame includes **44+ pipeline-aware looks**, including 30 v1.8 artistic packs across:

- Fine Art
- Cinema & Genre
- Print & Poster
- Experimental
- Commercial
- Core / Diagnostic

Examples include Watercolor Wash, Oil Impasto, Charcoal Study, VHS Horror, Grindhouse Damage, Risograph Zine, Album Art, Liminal Haze, Signal Rupture, Luxury Ad, Hero Tech Promo, Corporate Propaganda, Dream Collapse, Manga Motion and Clean Graphic Novel.

A style pack controls more than prompt text. It can own:

- positive and negative prompting
- denoise / steps / CFG
- ControlNet weight and guidance end
- temporal strength and cut thresholds
- Graphic Print Finish components
- deterministic finishing behavior
- inference-resolution preference

See [ARTISTIC_STYLES.md](ARTISTIC_STYLES.md) and [STYLES.md](STYLES.md).

## Requirements

- Windows/Linux/macOS with Python 3.10+
- `ffmpeg` and `ffprobe` on `PATH`
- a running AUTOMATIC1111/Forge-compatible Stable Diffusion WebUI API
- `sd-webui-controlnet` for the normal production path
- an SDXL-compatible Canny ControlNet model
- optional SDXL illustration/comic/art LoRAs

Python packages are listed in `requirements.txt`:

- Requests
- Pillow
- NumPy
- OpenCV

Install manually with:

```powershell
py -m pip install -r requirements.txt
```

The Windows launcher now checks those imports and installs requirements automatically when they are missing.

A1111/Forge should normally be started with:

```text
--api
```

For roughly 8–16 GB VRAM with SDXL, a useful starting point is:

```text
--api --medvram-sdxl
```

Default API:

```text
http://127.0.0.1:7860
```

## Launch

Windows:

```text
run_comicframe_studio.bat
```

Or:

```powershell
py app.py
```

Canonical v2.0 window title:

```text
ComicFrame Studio 2.0 · Shot Memory + Optical Flow
```

## Recommended production starting point

For source-faithful animated footage on an RTX 3060-class system:

```text
Preset:                    Video Fidelity · RTX 3060
Checkpoint:                SDXL-family checkpoint
Inference:                 1024 long edge
Seed behavior:             fixed
ControlNet:                ON / required
ControlNet module:         canny
ControlNet model:          diffusers_xl_canny_mid
ControlNet weight:         0.95
Guidance end:              0.92
Temporal engine:           Optical Flow · Fast
Temporal strength:         0.35
Flow confidence floor:     0.35
Shot Memory:               ON
Shot Memory strength:      0.22
Shot palette lock:         0.10
Shot anchor interval:      24 frames
Shot confidence floor:     0.45
Test range:                30–60 frames
```

Use motion in the test range: head turns, hands, walking, camera movement, or a moving product are much more informative than a static talking head.

## Continuity stack

### ControlNet

ControlNet is the structural foundation. Canny anchors:

- body silhouette and pose
- face/head placement
- products and prop edges
- furniture and architecture
- camera composition

The recommended SDXL model remains:

```text
diffusers_xl_canny_mid.safetensors
```

Full setup: [CONTROLNET.md](CONTROLNET.md).

### Shot Memory — pre diffusion

Shot Memory blends a confidence-masked, motion-warped version of the previous stylized frame into the next img2img starting image. The current source remains dominant and ControlNet still receives the clean source frame.

This is especially useful for painterly styles, facial rendering, product highlights and repeated surface treatment.

### Optical Flow — post diffusion

After the frame is rendered and all deterministic style finishing runs, v1.9 optical flow transports the previous final style through measured motion and blends it only where forward/backward flow and photometric agreement are trustworthy.

### Fixed seed

Video-lock renders force fixed seed behavior to remove avoidable stochastic drift between neighboring frames.

## Graphic / artistic finishing

ComicFrame's deterministic post stack can include:

- reinforced ink edges
- posterization
- halftone
- CMYK-like registration offsets
- grain
- watercolor / gouache / impasto treatments
- charcoal / ink wash
- VHS / grindhouse / surveillance signal language
- risograph / screenprint / xerox treatments
- glitch displacement / signal rupture
- commercial cleanup and product-focused grading

Effects are deterministic for a given frame number so post-processing does not become a random flicker source.

## GPU behavior

ComicFrame probes A1111's CUDA memory report before production renders.

- **8 GiB or more**: 1024 long-edge inference is the normal recommendation.
- **Below 8 GiB**: ComicFrame prefers the 768 long-edge low-VRAM ControlNet profile.

Optical flow is computed on a reduced-resolution CPU proxy and is relatively cheap compared with SDXL diffusion.

## Resume safety

Full renders only resume when the complete render profile matches. Current profiles include:

- checkpoint / sampler / scheduler
- prompts
- denoise / CFG / steps
- seed behavior
- LoRA settings
- ControlNet configuration
- inference resolution and upscale behavior
- selected style pack / deterministic finisher
- Graphic Print Finish controls
- temporal engine / flow confidence settings
- Shot Memory strength / palette / anchor interval / confidence settings

If those change, ComicFrame blocks the resume rather than silently mixing incompatible generations.

Test renders deliberately regenerate the selected range and use a separate temporary Shot Memory scope.

## Project output

```text
frames/
styled_frames/
test_frames/
shot_memory/
    full/
        manifest.json
        references/
    test/
source_info.json
render_settings.json
comicframe_profile.json
comicframe_test_profile.json
styled_silent.mp4
FINAL_STYLED.mp4
```

## Source layout

```text
app.py                         canonical launcher / runtime composition
comicframe_studio.py           stable frame/video/API core
comicframe_ui.py               desktop UI, WebUI discovery, previews
comicframe_app.py              render policy, LoRA and Graphic Print Finish
comicframe_controlnet.py       direct ControlNet discovery
comicframe_controlnet_compat.py ControlNet v3 enum normalization
comicframe_preflight.py        ControlNet/GPU preflight
comicframe_video_lock.py       ControlNet-first basic temporal lock
comicframe_optical_flow.py     v1.9 motion transport
comicframe_shot_memory.py      v2.0 pre-diffusion shot memory
comicframe_styles.py           core pipeline-aware style packs
comicframe_artistic.py         v1.8 artistic expansion library
comicframe_fx.py               shared deterministic print finish
```

## Troubleshooting

ComicFrame surfaces common backend failures with actionable guidance:

- `NansException` → lower inference resolution, try upcast cross attention, then precision changes.
- CUDA OOM → use 1024/768 inference and `--medvram-sdxl`.
- missing OpenCV/NumPy → rerun the launcher or install `requirements.txt`.
- missing ControlNet/model → Sync WebUI / Detect and install a checkpoint-compatible Canny model.
- ControlNet v3 enum errors → current builds normalize legacy numeric enum values automatically.

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

Historical changes live in [CHANGELOG.md](CHANGELOG.md).
