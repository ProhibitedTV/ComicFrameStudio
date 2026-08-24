# ComicFrame Studio

ComicFrame Studio is a local desktop GUI for turning ordinary video into frame-accurate AI-stylized animation through an AUTOMATIC1111/Forge-compatible Stable Diffusion WebUI API.

The pipeline is intentionally inspectable:

1. Probe the source video with `ffprobe`.
2. Extract every source frame with `ffmpeg`.
3. Run each frame through Stable Diffusion `img2img`.
4. Optionally use ControlNet for stronger structural guidance.
5. Optionally inject an A1111 LoRA for learned illustration/comic style.
6. Apply ComicFrame's deterministic whole-frame graphic-print finishing stack.
7. Save every styled frame individually and resume safely after interruption.
8. Reassemble the sequence at the original FPS.
9. Restore the source audio.

The original video is never overwritten.

## Current version: v1.5

v1.5 is the first pass aimed at **aggressive mixed-media comic animation**, rather than merely making the source look cel shaded.

New in v1.5:

- deterministic whole-frame **Graphic Print Finish**
- hard ink-edge reinforcement
- color posterization / graphic shadow blocking
- shadow-weighted halftone dot screens
- controlled CMYK-like channel misregistration
- print grain
- A1111 **LoRA discovery and selection**
- render manifests now record LoRA + print-FX settings
- graphic-FX CI smoke test
- stronger presets including **Graphic Shock · maximum print**

The intended stack is now:

```text
source frame
    ↓
SDXL img2img
    + optional Canny ControlNet structural anchor
    + optional illustration/comic LoRA
    ↓
ComicFrame deterministic Graphic Print Finish
    ↓
ink + posterization + halftone + CMYK split + grain
    ↓
video reassembly
```

The important distinction is that diffusion handles the redraw while ComicFrame handles print-language effects that need to remain visually consistent across neighboring frames.

## Consolidated source layout

Runtime code does not use version-numbered implementation filenames.

```text
app.py                 stable launcher / entrypoint
comicframe_app.py      current render policy and v1.5 behavior
comicframe_ui.py       desktop UI, WebUI discovery, previews
comicframe_fx.py       deterministic graphic-print finishing stack
comicframe_studio.py   stable frame/video/API core
```

Historical behavior belongs in `CHANGELOG.md`, not a chain of `*_v1_*.py` wrappers.

## Inference resolution vs output resolution

A 1920x1080 source does not need to be diffused natively at 1920x1080.

Recommended workflow on a 12 GB SDXL system:

```text
1920x1080 source frame
        ↓
resize complete frame to 1024-pixel long edge
        ↓
SDXL + optional ControlNet
        ↓
Graphic Print Finish
        ↓
optional Lanczos upscale to 1920x1080
        ↓
final video
```

Nothing is cropped. Lower inference resolution substantially reduces GPU load and helps avoid SDXL numerical and memory failures.

Available modes:

```text
1280 long edge · recommended
1024 long edge · fast / stable
768 long edge · emergency / low VRAM
Source / native · heavy
```

For a 12 GB GPU, **1024 long edge is the safer first test**.

## Requirements

- Python 3.10+
- `ffmpeg` and `ffprobe` on `PATH`
- a running Stable Diffusion WebUI with an AUTOMATIC1111/Forge-compatible API
- optional: `sd-webui-controlnet`
- optional: SDXL LoRAs installed in A1111

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

## Recommended next test

For the first structural + high-intensity test:

```text
Preset:          Structure First · ControlNet test
Checkpoint:      SDXL-family checkpoint
Sampler:         DPM++ 2M
Inference:       1024 long edge
Seed:            fixed
ControlNet:      ON
Module:          canny
Model:           diffusers_xl_canny_mid
Weight:          0.85–0.90
Style LoRA:      none for the first structural comparison
Graphic Finish:  ON
FX intensity:    ~0.62
Frames:          2–5
```

That test answers one question cleanly: can Canny ControlNet stop the person/room from melting while the new deterministic finishing stack supplies a much stronger graphic-print look?

If structure holds, the next step is to install/select an **SDXL illustration/comic LoRA** and run the `Graphic Shock · maximum print` preset.

## Graphic Print Finish

The finishing stack applies after diffusion to the complete frame.

Controls:

- **Ink** — reinforces meaningful image edges with dark print-like contours.
- **Posterize** — reduces continuous photographic gradients into stronger graphic color/shadow blocks.
- **Halftone** — places shadow-weighted dots primarily in midtones and dark areas.
- **CMYK split** — introduces a small controlled red/blue registration offset.
- **Grain** — adds subtle print texture.
- **Intensity** — globally scales how hard the finishing stack hits.

Halftone and registration use tiny deterministic frame cycles rather than random offsets, avoiding arbitrary per-frame noise.

## LoRA support

ComicFrame queries A1111's LoRA API during **Sync WebUI**.

If LoRAs are installed, they appear under **Style LoRA**. Selecting one injects the normal A1111 token automatically:

```text
<lora:MODEL_NAME:WEIGHT>
```

ComicFrame itself does not ship third-party model weights.

For this project, prefer SDXL LoRAs trained for illustration, comic art, screen print, ink, or stylized animation rather than photoreal LoRAs.

## ControlNet

ControlNet is optional. ComicFrame works with ordinary `img2img` without it.

For our current workflow, Canny ControlNet is valuable because it can anchor:

- body silhouette and pose
- furniture edges
- wall/room geometry
- camera composition

For SDXL, the recommended first model is:

```text
diffusers_xl_canny_mid.safetensors
```

Use the SMALL variant if VRAM is tight. Full installation instructions are in [CONTROLNET.md](CONTROLNET.md).

## Resume behavior

Full renders are resume-safe **only when the render profile matches**. ComicFrame records:

- checkpoint
- sampler/scheduler
- prompts
- diffusion strength
- seed behavior
- LoRA + LoRA weight
- ControlNet configuration
- inference resolution
- output scaling choice
- all Graphic Print Finish settings

If those change, resume is blocked rather than silently mixing incompatible frame styles.

Test renders deliberately regenerate the requested test range using the controls currently visible in the UI.

## Stable Diffusion errors

ComicFrame turns common backend failures into actionable errors:

- `NansException` → lower inference resolution, try upcast cross attention, then precision changes.
- `CUDA out of memory` → lower inference resolution, use `--medvram-sdxl`, and avoid full-precision SDXL unless required.

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

## Development

CI:

- installs ComicFrame's Python dependencies
- compiles all Python sources
- imports the canonical runtime stack
- runs a small Graphic Print Finish image smoke test

Version history is tracked in [CHANGELOG.md](CHANGELOG.md). Future work is tracked in [ROADMAP.md](ROADMAP.md).

## License

No license has been selected yet.
