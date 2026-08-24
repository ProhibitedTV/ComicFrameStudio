# Known Issues

## ControlNet installation is external to ComicFrame

ComicFrame can detect/use ControlNet when the Stable Diffusion WebUI exposes it, but the extension and its model files live inside the WebUI installation. A1111/ControlNet dependency conflicts can prevent the extension from loading even when ComicFrame itself is healthy.

Current recovery notes live in [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## Temporal flicker is not solved yet

v1.4 still stylizes frames independently. Fixed seeds, lower style strength, and optional ControlNet can reduce drift, but they do not provide true temporal conditioning.

Temporal consistency is the primary v1.5 roadmap item.

## Final upscale is conventional Lanczos

The v1.4 "upscale final video" option restores source dimensions with ffmpeg/Lanczos. It is not an AI super-resolution pass.

## Legacy implementation files remain

`comicframe_studio.py`, `comicframe_studio_v1_1.py`, and `comicframe_studio_v1_3.py` are retained because newer versions currently layer on top of them. `app.py` is the stable entrypoint. A package/refactor cleanup is intentionally deferred until the v1.x feature surface stabilizes.
