# ComicFrame Studio v2.1 — WebUI Contract Audit

ComicFrame talks to AUTOMATIC1111-compatible Stable Diffusion WebUIs over HTTP. v2.1 treats that boundary as an external service contract instead of assuming every compatible backend/version exposes every optional route perfectly.

This audit was performed against current upstream source for:

- `AUTOMATIC1111/stable-diffusion-webui`
- `lllyasviel/stable-diffusion-webui-forge`
- `Mikubill/sd-webui-controlnet`

## Core img2img contract

Current A1111 and Forge both expose:

```text
POST /sdapi/v1/img2img
GET  /sdapi/v1/options
POST /sdapi/v1/options
GET  /sdapi/v1/samplers
GET  /sdapi/v1/schedulers
GET  /sdapi/v1/sd-models
GET  /sdapi/v1/memory
```

Their current img2img response models both use:

```json
{
  "images": ["<base64>"],
  "parameters": {},
  "info": "..."
}
```

ComicFrame requires returned image data, so v2.1 now sends the intent explicitly:

```text
send_images = true
save_images = false
include_init_images = false
batch_size = 1
n_iter = 1
```

The generated frame remains the first image ComicFrame consumes.

## Image response hardening

A1111/Forge encode API images using the backend's configured sample format. A backend configured for JPEG or WebP can therefore return valid JPEG/WebP bytes even though ComicFrame's frame path is named `frame_XXXXXX.png`.

Older ComicFrame builds wrote those decoded bytes directly to the `.png` path.

v2.1 instead:

1. validates the returned field is a non-empty string,
2. accepts raw base64 or `data:image/...;base64,...`,
3. validates base64,
4. decodes the image through Pillow,
5. converts to RGB,
6. writes an actual PNG to a temporary `.part` file,
7. verifies that temporary image,
8. atomically replaces the final frame path.

A malformed response therefore cannot masquerade as a completed PNG frame.

## Error envelopes

The upstream families are similar but not identical in how API failures are surfaced. Depending on backend and exception path, useful data can appear under fields such as:

```text
detail
message
error
errors
body
```

v2.1 reads all of those fields and emits one endpoint-aware error instead of assuming one specific error schema.

## Checkpoint inventory and loading

Current upstream A1111 and Forge expose `/sdapi/v1/sd-models`. Forge previously had a response-model regression involving the `config` field; current Forge source now supplies `config` safely.

ComicFrame still protects against older installs:

1. query `/sdapi/v1/sd-models`,
2. if it fails, call `/sdapi/v1/refresh-checkpoints`,
3. retry once,
4. if inventory is still broken, use the currently loaded checkpoint from `/sdapi/v1/options` as a one-item safe fallback.

Changing checkpoints is also verified. After `POST /sdapi/v1/options`, ComicFrame re-reads `/sdapi/v1/options` and confirms the requested checkpoint is actually active instead of trusting HTTP 200 alone.

Checkpoint comparison normalizes path, common checkpoint suffixes, and A1111/Forge hash suffixes.

## Samplers and schedulers

Current A1111 and Forge both expose sampler and scheduler catalogs and both accept an explicit `scheduler` in generation requests.

For compatibility with older servers:

- failure of the sampler catalog keeps the user's configured sampler and lets img2img perform final server-side validation,
- failure of the scheduler catalog clears the scheduler UI value and omits `scheduler` from the payload.

An optional discovery failure no longer makes the entire WebUI synchronization fail.

## Memory / VRAM report

Current A1111 and Forge expose the same important CUDA shape:

```text
cuda.system.free
cuda.system.used
cuda.system.total
```

ComicFrame's existing VRAM parser reads `cuda.system.total`, so the RTX-3060-class automatic inference selection remains compatible with both current backends.

## LoRA inventory

Both current upstream families expose the built-in LoRA API at:

```text
GET  /sdapi/v1/loras
POST /sdapi/v1/refresh-loras
```

LoRA discovery remains optional because users can disable/remove the built-in extension. Core img2img remains usable without it.

## Backend fingerprinting

The runtime uses capabilities, not branding, to decide behavior. For diagnostics only, current route differences provide a useful hint:

```text
Forge: /sdapi/v1/sd-modules
A1111: /sdapi/v1/sd-vae
```

If OpenAPI is unavailable, ComicFrame simply labels the server `A1111-compatible` and continues probing concrete routes.

## ControlNet v3 contract

Current `sd-webui-controlnet` reports API version 3 and exposes:

```text
GET /controlnet/version
GET /controlnet/model_list
GET /controlnet/module_list
GET /controlnet/control_types
GET /controlnet/settings
```

ComicFrame already probes those routes directly instead of requiring them to appear in `/openapi.json`.

The current ControlNet unit contract validates:

```text
enabled
module
model
weight
image
resize_mode
low_vram
processor_res
threshold_a
threshold_b
guidance_start
guidance_end
pixel_perfect
control_mode
save_detected_map
```

v2.1 retains the existing v3 enum normalization:

```text
control_mode:
  Balanced
  My prompt is more important
  ControlNet is more important

resize_mode:
  Just Resize
  Crop and Resize
  Resize and Fill
```

### Shot Memory isolation

ControlNet's current input-selection code gives an explicit `ControlNetUnit.image` priority over the normal A1111 `p.init_images` fallback.

That validates ComicFrame v2.0's architecture:

```text
img2img init_images  = memory-conditioned current frame
ControlNet unit image = untouched current source frame
```

Shot Memory can therefore influence the diffusion starting point without becoming structural ControlNet guidance.

### Detected maps

ControlNet v3 defaults its API-only `save_detected_map` field to true. ComicFrame does not consume detected/preprocessor maps, so v2.1 forces:

```text
save_detected_map = false
```

This reduces API response bandwidth and removes unnecessary extra images from the response surface.

## v2.1 runtime policy

Endpoints fall into two classes.

### Required control-plane contract

```text
/sdapi/v1/options
/sdapi/v1/img2img
```

If the WebUI cannot satisfy that basic contract, ComicFrame fails clearly rather than pretending synchronization succeeded.

### Optional/degradable discovery

```text
/openapi.json
/sdapi/v1/sd-models
/sdapi/v1/samplers
/sdapi/v1/schedulers
/sdapi/v1/memory
/sdapi/v1/loras
/controlnet/*
```

Failures here either have a documented fallback or disable only the associated optional feature.

The `2B · API contract · v2.1` panel shows the capabilities ComicFrame actually found on the running local server.
