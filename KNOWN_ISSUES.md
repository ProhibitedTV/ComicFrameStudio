# Known Limitations and Maintenance Debt

This file tracks non-blocking limitations of the current v2.9.1 runtime. Confirmed repo-owned correctness defects found during the v2.8/v2.9 audit were fixed and regression-tested rather than left here as accepted behavior.

## ControlNet installation is external to ComicFrame

ComicFrame can detect and use ControlNet when the Stable Diffusion WebUI exposes it, but the extension and its model files live inside the WebUI installation. A1111/Forge/ControlNet dependency conflicts can prevent the extension from loading even when ComicFrame itself is healthy.

ComicFrame now checks model family, available preprocessors/reference backends and configured ControlNet unit capacity, but it cannot repair a broken external WebUI installation. Recovery notes live in [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## Automatic recurring-subject detection is conservative, not semantic recognition

AutoPilot clusters very similar representative frames using deterministic image similarity. It is intentionally high-threshold and falls back to shot-local references when confidence is low. It is not a face/object recognition system.

Manual Subject Library assignments remain the authoritative override.

## Tk still owns part of the configuration surface

The current v2 stack grew from a desktop application and several rendering layers still read or temporarily change Tk variables while a worker job is active. v2.8+ locks configuration controls for the duration of a job, and v2.9.1 clears process-local state when project/source context changes, but this remains architecture debt.

The v3.0 roadmap calls for an immutable `RenderSession` snapshot and explicit services so widgets stop doubling as the configuration store.

## Cooperative mixin depth remains high

The canonical rendering engine still composes historical generations through cooperative mixins. The audited launcher now keeps v2.8, v2.9 and the final v2.9.1 stability boundary in explicit modules, and CI covers the MRO, but the stack is expensive to reason about.

The next major engineering target is decomposition without changing the v2.9.1 project/render contract.

## Final upscale is conventional Lanczos

When final output is restored to source dimensions, ComicFrame uses ffmpeg/Lanczos. It is not an AI super-resolution pass. Adaptive per-shot inference cannot silently change final output dimensions; an AI upscale is an optional future quality feature.

## CI is split between pytest and historical workflow smoke scripts

The hardening and stability audits use normal pytest modules, while several older subsystem workflows still contain substantial inline Python. This is maintenance debt, not a runtime blocker. The roadmap calls for migrating those scripts into reusable tests and adding Windows + ffmpeg integration coverage.

## External backend behavior can still vary

Forge, AUTOMATIC1111 and `sd-webui-controlnet` versions are not one frozen protocol implementation. ComicFrame capability-detects routes and translates common failures, but a future backend release can still change request/response behavior. WebUI contract CI protects ComicFrame's expected side of that boundary; real backend upgrades should still be tested before committing a very long render.
