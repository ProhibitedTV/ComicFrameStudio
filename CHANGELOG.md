# Changelog

## v1.5 — graphic print intensity / LoRA style stack

- Added `comicframe_fx.py`, a deterministic whole-frame finishing layer that runs after diffusion.
- Added hard ink-edge reinforcement.
- Added color posterization and stronger graphic contrast/saturation shaping.
- Added shadow-weighted halftone dot screens.
- Added controlled CMYK-like channel misregistration with deterministic frame cycling rather than random jitter.
- Added subtle print grain.
- Added **Graphic Print Finish** controls and global FX intensity in the desktop UI.
- Added stronger presets, including **Graphic Shock · maximum print** and **Structure First · ControlNet test**.
- Added A1111 LoRA discovery through `/sdapi/v1/loras`.
- Added Style LoRA selection and weight controls; selected LoRAs are injected using normal A1111 prompt syntax.
- Extended render manifests to record LoRA and all Graphic Print Finish settings for resume safety.
- Defaulted v1.5 to 1024 long-edge inference for safer first tests on 12 GB SDXL systems.
- Expanded negative prompting against invented machinery, transformed furniture, and circular-object hallucinations observed in real test footage.
- Added a CI image-processing smoke test for the complete Graphic Print Finish stack.
- Updated README with the intended SDXL + ControlNet + LoRA + deterministic print pipeline and a recommended next-test recipe.

## v1.4 — adaptive rendering / resilience

- Added 1280, 1024, 768, and native inference modes.
- Defaulted diffusion work to a lower long-edge proxy while preserving the complete frame and aspect ratio.
- Added optional Lanczos upscale of the final video back to source resolution.
- Added live latest-frame preview updates during rendering.
- Added actionable `NansException` diagnostics.
- Added actionable CUDA out-of-memory diagnostics with lower-resolution and A1111 VRAM guidance.
- Added profile-aware resume protection so full renders cannot silently mix frames made with different checkpoints, prompts, samplers, strengths, ControlNet settings, or inference resolutions.
- Test renders now overwrite the requested test range instead of silently reusing stale test frames from older settings.
- Added a stable `app.py` entrypoint.
- Consolidated runtime modules into semantic filenames: `comicframe_app.py`, `comicframe_ui.py`, and `comicframe_studio.py`.
- Removed obsolete version-numbered runtime wrappers.
- Expanded CI to compile all Python sources.
- Added `CONTROLNET.md` with SDXL Canny model installation and first-run guidance.
- Expanded troubleshooting documentation for A1111, NumPy, MediaPipe, ControlNet, UNet NaNs, and VRAM exhaustion.

## v1.3 — usable desktop UI

- Rebuilt the application around a dark two-pane interface.
- Added WebUI-native checkpoint, sampler, and scheduler discovery.
- Added checkpoint loading before renders.
- Added source and styled-frame previews.
- Added comic style presets and stronger default stylization.
- Demoted ControlNet to optional advanced structural guidance.

## v1.2 — WebUI discovery

- Queried the running WebUI's OpenAPI surface instead of assuming one ControlNet API layout.
- Added core Stable Diffusion checkpoint inventory diagnostics.

## v1.1 — ControlNet diagnostics

- Distinguished missing ControlNet, missing models, and ready states.
- Blocked misleading renders where ControlNet was enabled with no selected model.

## v1.0 — initial pipeline

- Exact frame extraction with ffmpeg.
- Stable Diffusion img2img API rendering.
- Resume-safe per-frame output.
- Reassembly at source FPS.
- Original audio restoration.
