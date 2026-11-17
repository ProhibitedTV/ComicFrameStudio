# Known Limitations and Maintenance Debt

This file tracks limitations of the v3.6 product shell, v3.7 style library and retained v2 engine boundaries. Backend resilience remains v3.6.3; FFmpeg compatibility is v1.3.

## Dream Rotoscope needs real-backend artistic acceptance

Synthetic transport tests and mocked WebUI integration validate implementation behavior, not the quality of an animated painting. This release has no real diffusion visual comparison, face/hand acceptance review, or RTX 3060 throughput measurement. The public preview renders one actual diffusion frame when a backend is available; it cannot establish temporal quality. A short sequence preview is the next product milestone.

## ControlNet installation is external to ComicFrame

ComicFrame can detect and use ControlNet when the Stable Diffusion WebUI exposes it, but the extension and its model files live inside the WebUI installation. A1111/Forge/ControlNet dependency conflicts can prevent the extension from loading even when ComicFrame itself is healthy.

ComicFrame now checks model family, available preprocessors/reference backends and configured ControlNet unit capacity, but it cannot repair a broken external WebUI installation. Recovery notes live in [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## Automatic recurring-subject detection is conservative, not semantic recognition

AutoPilot clusters very similar representative frames using deterministic image similarity. It is intentionally high-threshold and falls back to shot-local references when confidence is low. It is not a face/object recognition system.

Manual Subject Library assignments remain the authoritative override.

## Tk still owns part of the configuration surface

The current v2 stack grew from a desktop application and several rendering layers still read or temporarily change Tk variables while a worker job is active. The public source/project/Look/ControlNet/Steps are now captured in a frozen `RenderRequest`, and hidden job defaults are applied before the worker starts. Internal engine settings still use Tk variables. Configuration locking and context reconciliation remain in place.

The next architecture milestone is a complete immutable engine configuration and explicit backend service boundary so widgets stop doubling as the configuration store.

## Cooperative mixin depth remains high

The canonical rendering engine still composes historical generations through cooperative mixins. The audited launcher now keeps v2.8, v2.9 and the final v2.9.1 stability boundary in explicit modules, and CI covers the MRO, but the stack is expensive to reason about.

The next major engineering target is decomposition without changing the v2.9.1 project/render contract.

## Final upscale is conventional Lanczos

When final output is restored to source dimensions, ComicFrame uses ffmpeg/Lanczos. It is not an AI super-resolution pass. Adaptive per-shot inference cannot silently change final output dimensions; an AI upscale is an optional future quality feature.

## Native and platform coverage

CI runs pytest, including generated CFR/VFR/audio integration checks when FFmpeg is available, and small inline import/registry checks. Windows native preview-to-full-render smoke is reproducible with `tools/smoke_desktop.py`; its backend responses are mocked. Screenshot capture was unavailable in this validation environment, so native geometry assertions are not a visual layout review. Other OS desktop behavior and high-DPI layouts need broader review.

## External backend behavior can still vary

Forge, AUTOMATIC1111 and `sd-webui-controlnet` versions are not one frozen protocol implementation. ComicFrame capability-detects routes and translates common failures, but a future backend release can still change request/response behavior. WebUI contract CI protects ComicFrame's expected side of that boundary; real backend upgrades should still be tested before committing a very long render.
