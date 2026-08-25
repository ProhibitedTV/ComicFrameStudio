# ControlNet setup for ComicFrame Studio

ControlNet is now the **default production path** for ComicFrame Studio's video-lock renderer. The app can still run plain `img2img` for diagnostics, but normal full renders are expected to use ControlNet so source edges, pose, object geometry, and camera composition stay anchored while the frame is stylized.

## 1. Install the extension

For AUTOMATIC1111, install:

```text
https://github.com/Mikubill/sd-webui-controlnet.git
```

Then completely restart the WebUI, including the terminal process.

A healthy startup should report a ControlNet version and register its API routes. ComicFrame also probes the canonical `/controlnet/*` endpoints directly because some extension builds do not advertise them through `/openapi.json`.

## 2. Install a checkpoint-compatible Canny model

If your Stable Diffusion checkpoint is SDXL, use an **SDXL** ControlNet model. Do not mix SD1.5 ControlNet weights with an SDXL checkpoint.

For ComicFrame's production continuity pass, use Canny edge guidance.

### Recommended

```text
diffusers_xl_canny_mid.safetensors
```

This is the preferred first balance for a desktop RTX 3060 with 12 GB VRAM.

### Lower-VRAM fallback

```text
diffusers_xl_canny_small.safetensors
```

Use the smaller variant when VRAM is tight. ComicFrame also enables ControlNet low-VRAM mode and forces 768-long-edge inference when the WebUI reports less than 8 GiB of CUDA memory.

### Heavy variant

```text
diffusers_xl_canny_full.safetensors
```

The full model is not the first choice for an RTX 3060-class workflow.

The ControlNet maintainers mirror supported SDXL Canny weights here:

```text
https://huggingface.co/lllyasviel/sd_control_collection/tree/main
```

Open the model file on Hugging Face and use its **Download** button. Do not save the HTML page itself as a `.safetensors` file.

## 3. Put the model in the correct folder

Preferred location:

```text
stable-diffusion-webui\models\ControlNet\
```

For example:

```text
stable-diffusion-webui\models\ControlNet\diffusers_xl_canny_mid.safetensors
```

The extension also supports its own models folder:

```text
stable-diffusion-webui\extensions\sd-webui-controlnet\models\
```

Use one location, not duplicate copies in both.

## 4. Refresh / restart

After copying the model:

1. Completely restart AUTOMATIC1111, or use the ControlNet model refresh control in the WebUI.
2. Open ComicFrame Studio.
3. Click **Sync WebUI**.
4. ComicFrame will probe ControlNet and automatically select a compatible Canny module/model when possible.
5. Leave **Use ControlNet structural guidance** and **Require for render** enabled for production work.

Recommended first production settings on a desktop RTX 3060:

```text
Preset: Video Fidelity · RTX 3060
Module: canny
Model: diffusers_xl_canny_mid
Weight: 0.95
Guidance end: 0.92
Inference: 1024 long edge
Seed: fixed
Temporal lock: enabled
Temporal strength: 0.35
```

## 5. RTX 3060 / VRAM guidance

SDXL + img2img + ControlNet is expensive. ComicFrame queries AUTOMATIC1111's `/sdapi/v1/memory` endpoint during sync/render preflight:

- **8 GiB or more:** 1024-long-edge inference remains the recommended production profile.
- **Below 8 GiB:** ComicFrame enables ControlNet low-VRAM mode and forces 768-long-edge inference.

A practical A1111 launch baseline for SDXL is:

```text
--opt-sdp-attention --listen --api --skip-torch-cuda-test --medvram-sdxl
```

Avoid running all of SDXL in full precision unless it is actually required. Flags such as:

```text
--precision full --no-half --no-half-vae
```

consume substantially more VRAM.

If half precision gives a UNet NaN error, try these before full `--no-half`:

1. A1111 **Upcast cross attention layer to float32**.
2. `--upcast-sampling`.
3. ComicFrame 1024 or 768 long-edge inference.

## 6. What ControlNet is doing here

ComicFrame sends the original video frame to img2img for stylization. Canny ControlNet additionally supplies an edge representation derived from that same source frame.

That gives diffusion a strong structural target so:

- the person's silhouette stays in place
- pose and hands are less likely to redraw unpredictably
- furniture edges stay in place
- walls and room geometry crawl less between frames
- camera composition remains recognizable

ControlNet handles **spatial structure**. ComicFrame v1.6 additionally applies a **motion-aware temporal lock** after stylization: unchanged regions borrow some appearance from the previous stylized frame, moving regions stay current, and hard cuts bypass the temporal blend. Together, those two mechanisms are the main continuity strategy.

## Troubleshooting

### ComicFrame says ControlNet is required but unavailable

The extension may be missing, disabled, or unable to see any model files. Confirm the `.safetensors` file is in a supported ControlNet models directory, restart A1111, and click **Sync WebUI** again.

### ComicFrame detects the wrong checkpoint family

The production preflight rejects obvious SDXL-checkpoint / SD1.5-ControlNet mismatches. Select or install a matching Canny model.

### ControlNet fails with `mediapipe has no attribute solutions`

See `TROUBLESHOOTING.md`. A known A1111/ControlNet combination may require MediaPipe `0.10.14` in the WebUI venv.

### CUDA out of memory

Start with:

```text
Inference: 768 or 1024 long edge
ControlNet: Canny SMALL or MID
A1111: --medvram-sdxl
```

Do not use native 1920x1080 diffusion as the first troubleshooting step.

### Need an img2img-only diagnostic render

Disable **Require for render** and then disable ControlNet. This is intended for troubleshooting only; normal production video renders should keep ControlNet enabled.
