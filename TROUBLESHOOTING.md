# Troubleshooting

ComicFrame Studio talks to an existing Stable Diffusion WebUI. Most render failures therefore come from the WebUI environment rather than ComicFrame's frame pipeline.

## Stable Diffusion API works, but ControlNet does not

ControlNet is optional. Leave it disabled until the extension loads cleanly and exposes models.

A healthy A1111 install can still run ComicFrame with normal `img2img` even when ControlNet is unavailable.

If ControlNet loads but ComicFrame says `Extension route found, but no models exposed`, follow [CONTROLNET.md](CONTROLNET.md) and install an SDXL Canny model under `stable-diffusion-webui\models\ControlNet\`.

## ControlNet: `mediapipe` has no attribute `solutions`

A failure seen with A1111 v1.10.x + `sd-webui-controlnet` looks like:

```text
AttributeError: module 'mediapipe' has no attribute 'solutions'
```

Run the fix inside the **Stable Diffusion WebUI venv**, not ComicFrame's Python environment:

```bat
venv\Scripts\python.exe -m pip uninstall -y mediapipe
venv\Scripts\python.exe -m pip install mediapipe==0.10.14
venv\Scripts\python.exe -c "import mediapipe as mp; print(mp.__version__); print(hasattr(mp, 'solutions'))"
```

The final command should report `0.10.14` and `True` for `solutions`.

### Important: check NumPy after installing MediaPipe

Pip may try to pull NumPy 2.x while satisfying MediaPipe/JAX dependencies. Older A1111 builds depend on NumPy 1.x binary wheels. Check immediately:

```bat
venv\Scripts\python.exe -c "import numpy; print(numpy.__version__)"
```

For A1111 v1.10.1, the pinned dependency set uses NumPy 1.26.2. If the command reports 2.x, restore it before troubleshooting anything else:

```bat
venv\Scripts\python.exe -m pip install --force-reinstall numpy==1.26.2
```

A normal A1111 startup may also reinstall its pinned requirements.

## NumPy 2.x binary incompatibility

Typical errors include:

```text
A module that was compiled using NumPy 1.x cannot be run in NumPy 2.x
```

or:

```text
ValueError: numpy.dtype size changed, may indicate binary incompatibility
```

Repair the WebUI venv rather than the system Python environment:

```bat
venv\Scripts\python.exe -m pip install --force-reinstall numpy==1.26.2
venv\Scripts\python.exe -m pip install --force-reinstall --no-deps scikit-image==0.21.0
```

Then verify imports before relaunching WebUI.

## `NansException` / tensor with NaNs in UNet

This is a Stable Diffusion numerical failure, not a corrupt source frame.

ComicFrame defaults to a 1280-pixel long-edge inference proxy to reduce the likelihood of this failure while preserving the complete frame and aspect ratio.

Try, in order:

1. Use **1024 long edge** or **768 long edge** inference.
2. Try a different checkpoint or sampler.
3. In A1111, enable **Upcast cross attention layer to float32**.
4. Only if needed, test full-precision options such as `--no-half`.

Avoid `--disable-nan-check` as the first response; it suppresses detection rather than fixing the unstable math.

## CUDA out of memory / `OutOfMemoryError`

SDXL img2img is memory-heavy, and ControlNet adds more memory pressure. Full-precision launch flags multiply the cost.

For a roughly 12 GB GPU, start with:

```text
ComicFrame inference: 1024 long edge
A1111: --medvram-sdxl
ControlNet: off until plain img2img succeeds
```

A practical A1111 launch baseline is:

```text
--opt-sdp-attention --listen --api --skip-torch-cuda-test --medvram-sdxl
```

If you previously added:

```text
--precision full --no-half --no-half-vae
```

for a NaN problem, remove those flags again when testing VRAM usage. Full precision can turn a numerically stable render into an out-of-memory render.

If NaNs return after restoring half precision, prefer **Upcast cross attention layer to float32** plus lower ComicFrame inference resolution before putting the entire SDXL model back into full precision.

When ControlNet is added, begin with the Canny SMALL or MID model and 768/1024 inference.

## WebUI API connection

ComicFrame expects an AUTOMATIC1111/Forge-compatible API at the configured address, normally:

```text
http://127.0.0.1:7860
```

A1111 is commonly launched with:

```text
--api
```

ComicFrame's **Sync WebUI** button should populate checkpoints and samplers from the running server. If it reports connection failure, confirm `/sdapi/v1/options` is reachable in a browser.

## ffmpeg / ffprobe missing

Both executables must be available on `PATH`.

On Windows, one option is:

```powershell
winget install Gyan.FFmpeg
```

Open a new terminal after installation and verify:

```text
ffmpeg -version
ffprobe -version
```
