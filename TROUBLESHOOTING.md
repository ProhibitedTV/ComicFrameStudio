# Troubleshooting

ComicFrame Studio talks to an existing Stable Diffusion WebUI. Most render failures therefore come from the WebUI environment rather than ComicFrame's frame pipeline.

## Stable Diffusion API works, but ControlNet does not

ControlNet is optional. Leave it disabled until the extension loads cleanly and exposes models.

A healthy A1111 install can still run ComicFrame with normal `img2img` even when ControlNet is unavailable.

## ControlNet: `mediapipe` has no attribute `solutions`

A recent failure seen with A1111 v1.10.x + `sd-webui-controlnet` looks like:

```text
AttributeError: module 'mediapipe' has no attribute 'solutions'
```

Run the fix inside the **Stable Diffusion WebUI venv**, not ComicFrame's Python environment:

```bat
venv\Scripts\python.exe -m pip uninstall -y mediapipe
venv\Scripts\python.exe -m pip install mediapipe==0.10.14
venv\Scripts\python.exe -c "import mediapipe as mp; print(mp.__version__); print(hasattr(mp, 'solutions'))"
```

The final command should report `True` for `solutions`.

## NumPy 2.x binary incompatibility

A ControlNet dependency install may disturb an older A1111 environment. Typical errors include:

```text
A module that was compiled using NumPy 1.x cannot be run in NumPy 2.x
```

or:

```text
ValueError: numpy.dtype size changed, may indicate binary incompatibility
```

A1111 v1.10.1's pinned dependency set uses NumPy 1.26.x. Repair the WebUI venv rather than the system Python environment. Example:

```bat
venv\Scripts\python.exe -m pip install --force-reinstall numpy==1.26.2
venv\Scripts\python.exe -m pip install --force-reinstall --no-deps scikit-image==0.21.0
```

Then verify imports before relaunching WebUI.

## `NansException` / tensor with NaNs in UNet

This is a Stable Diffusion numerical failure, not a corrupt source frame.

ComicFrame v1.4 defaults to a 1280-pixel long-edge inference proxy to reduce the likelihood of this failure while preserving the complete frame and aspect ratio.

Try, in order:

1. Use **1280 long edge** or **1024 long edge** inference instead of native 1080p diffusion.
2. Try a different checkpoint or sampler.
3. In A1111, enable **Upcast cross attention layer to float32**.
4. If needed, launch A1111 with full-precision options such as:

```text
--precision full --no-half --no-half-vae
```

Avoid `--disable-nan-check` as the first response; it suppresses detection rather than fixing the unstable math.

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
