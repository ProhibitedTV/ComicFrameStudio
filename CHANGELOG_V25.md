# v2.5 — Render Intelligence

## Added

- Easy Mode Performance selector: Fast / Balanced / Quality.
- Per-shot CPU difficulty analysis using motion, detail, artistic intensity and subject-lock pressure.
- Adaptive diffusion-step targets and inference resolution per shot.
- Persistent raw optical-flow cache shared by Shot Memory and post-render temporal transport.
- Automatic one-frame 1024/native → 768 retry for recognized VRAM allocation failures.
- Render-plan and source-feature caches under the project `cache/` directory.
- Efficiency-aware per-frame invalidation for projects once a v2.5 rendered timeline exists.
- Dedicated Render Intelligence CI.

## Compatibility

- Existing v2.4 completed frames are preserved on upgrade.
- WebUI, ControlNet, Shot Memory, Shot Director, Reference Lock and Project Workspace contracts remain underneath unchanged.
- Canny detector-map caching is deliberately deferred because replacing ControlNet's source/preprocessor contract without backend/version validation can change Pixel Perfect semantics.
