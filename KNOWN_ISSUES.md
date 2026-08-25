# Known Issues

## ControlNet installation is external to ComicFrame

ComicFrame can detect/use ControlNet when the Stable Diffusion WebUI exposes it, but the extension and its model files live inside the WebUI installation. A1111/Forge/ControlNet dependency conflicts can prevent the extension from loading even when ComicFrame itself is healthy.

Current recovery notes live in [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## Automatic recurring-subject detection is conservative, not semantic recognition

AutoPilot currently clusters very similar representative frames using deterministic image similarity. It is intentionally high-threshold and falls back to shot-local references when confidence is low. It is not a face/object recognition system.

Manual Subject Library assignments remain the authoritative override.

## Tk variables still double as runtime configuration

The current v2 stack grew from a desktop application and several rendering layers still read/temporarily change Tk variables during worker-driven rendering. This works under the normal running Tk main loop, but it is architectural debt.

A future refactor should snapshot immutable render configuration before launching a job and pass that configuration through explicit services instead of treating widgets as the configuration store.

## Cooperative mixin depth is high

The canonical runtime composes the historical rendering generations through cooperative mixins. CI covers the MRO and v2.8 centralizes cross-generation safety at `ComicFrameStudioApp`, but the stack is becoming expensive to reason about.

See [AUDIT.md](AUDIT.md) for the recommended service-oriented decomposition.

## Final upscale is conventional Lanczos

When final output is restored to source dimensions, ComicFrame uses ffmpeg/Lanczos. It is not an AI super-resolution pass. v2.8 now makes the target dimensions explicit so adaptive per-shot inference cannot make final resolution depend on the first frame.

## CI tests are still split between YAML smoke scripts and pytest

v2.8 introduces `tests/test_hardening.py`, but older suites still contain substantial inline Python inside GitHub Actions workflows. Moving those tests into `tests/` is future maintenance work, not a runtime blocker.
