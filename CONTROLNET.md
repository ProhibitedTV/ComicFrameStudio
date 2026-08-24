# ControlNet setup for ComicFrame Studio

ControlNet is optional. ComicFrame works with ordinary `img2img`, but ControlNet can preserve scene edges, pose, and object geometry when style strength is pushed high.

## 1. Install the extension

For AUTOMATIC1111, install:

```text
https://github.com/Mikubill/sd-webui-controlnet.git
```

Then completely restart the WebUI, including the terminal process.

A healthy startup should report a ControlNet version and register its UI callback.

## 2. Install an SDXL ControlNet model

If your Stable Diffusion checkpoint is SDXL, use an **SDXL** ControlNet model. Do not mix SD1.5 ControlNet weights with an SDXL checkpoint.

For ComicFrame's first continuity pass, use Canny edge guidance.

### Recommended

```text
diffusers_xl_canny_mid.safetensors
```

This is the best first balance for ComicFrame. The community mirror is roughly 545 MB.

### Lower-VRAM fallback

```text
diffusers_xl_canny_small.safetensors
```

This variant is roughly 320 MB.

### Heavy variant

```text
diffusers_xl_canny_full.safetensors
```

This variant is roughly 2.5 GB and is not the first choice for a 12 GB GPU.

The extension's official model-download documentation points SDXL users to community models, and the ControlNet maintainers mirror supported SDXL Canny weights here:

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
4. Click **Detect** under Advanced continuity.
5. Enable **Use ControlNet structural guidance**.
6. Choose the discovered Canny model.

Suggested first settings:

```text
Module: canny
Model: diffusers_xl_canny_mid
Weight: 0.80–0.90
Style strength: 0.45–0.55
Inference: 1024 long edge for first test
Seed: fixed
```

## 5. 12 GB VRAM guidance

SDXL + img2img + ControlNet can be expensive. The ControlNet maintainers recommend `--medvram-sdxl` for roughly 8–16 GB VRAM systems.

A practical A1111 launch baseline is:

```text
--opt-sdp-attention --listen --api --skip-torch-cuda-test --medvram-sdxl
```

Avoid running all of SDXL in full precision unless it is actually needed. Flags such as:

```text
--precision full --no-half --no-half-vae
```

consume substantially more VRAM.

If half precision gives a UNet NaN error, try these before full `--no-half`:

1. A1111 **Upcast cross attention layer to float32** setting.
2. `--upcast-sampling`, which A1111 documents as giving behavior similar to `--no-half` with better performance and lower memory use.
3. ComicFrame 1024 or 768 long-edge inference.

If full precision is still required, stay at the lower ComicFrame inference modes.

## 6. What Canny ControlNet is doing here

ComicFrame sends the original video frame to img2img for stylization. Canny ControlNet additionally supplies an edge map from that frame.

That lets the diffusion model change rendering style while receiving a strong hint that:

- the person's silhouette should remain in place
- furniture edges should remain in place
- walls and room geometry should not crawl between frames
- the camera composition should remain recognizable

It does **not** solve temporal consistency by itself. It is a structural anchor; temporal conditioning remains a separate roadmap item.

## Troubleshooting

### ComicFrame says `Extension route found, but no models exposed`

The extension is loaded but it cannot see a model file. Confirm the `.safetensors` file is in `models\ControlNet`, restart A1111, and refresh the model list.

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
