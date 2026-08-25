# Changelog

## v1.7 — pipeline-aware style packs

- Added `comicframe_styles.py`, a dedicated style-pack layer that keeps look-specific behavior out of the core renderer.
- Expanded the preset library with **Clean Graphic Novel**, **Neo-Noir**, **Cyberpunk Print**, **Pulp Horror**, **Retro 70s Print**, **Manga Motion**, **Dream Collapse**, **Corporate Propaganda**, and **Analog Broadcast** while preserving the existing fidelity, shock, punch, structure-test, and diagnostic presets.
- Promoted presets from prompt aliases to complete pipeline configurations: denoise, steps, CFG, ControlNet weight/guidance, temporal-lock behavior, Graphic Print Finish switches, negative prompting, and inference preference are now applied together.
- Added deterministic style-specific finishing for noir monochrome, manga screentone contrast, warm 1970s print aging, pulp-horror grading, cyberpunk saturation, heroic product-ad cleanup, CRT scanlines/signal ghosting, and displaced-edge dream-collapse effects.
- Kept style-specific finishing deterministic so new looks do not reintroduce random frame shimmer.
- Added style-pack metadata to render profiles so resume safety can distinguish different style families.
- Added `STYLES.md` with intended use, structural pressure, and temporal behavior for every bundled style.
- Added CI coverage that validates all style-pack parameter ranges and runs a deterministic Neo-Noir image smoke test.
- Bumped the canonical runtime and render manifests to v1.7.

## v1.6 — ControlNet-first video lock / RTX 3060 profile

- Promoted ControlNet from an optional advanced feature to the default production continuity path.
- Added `comicframe_video_lock.py` with a source-faithful **Video Fidelity · RTX 3060** preset tuned to restyle the shot instead of redesigning it.
- Added ControlNet-required render preflight with a deliberate diagnostic opt-out.
- Added automatic Canny model/module selection with checkpoint-family preference and SDXL-vs-SD1.5 mismatch protection.
- Added race-safe first-render ControlNet inventory probing so rendering cannot start before the Tk combo population callback finishes.
- Added ControlNet weight, guidance-end, pixel-perfect, processor-resolution, and low-VRAM request hardening.
- Added WebUI GPU-memory probing through `/sdapi/v1/memory`; sub-8 GiB systems automatically prefer the 768 long-edge / low-VRAM ControlNet path while 8+ GiB systems stay on the 1024 profile.
- Added motion-aware temporal stabilization that reuses the previous stylized frame only in visually stable source regions.
- Added scene-cut detection so temporal stabilization is bypassed on hard shot changes.
- Forced fixed-seed behavior for video-lock renders to eliminate avoidable stochastic drift.
- Extended resume manifests with ControlNet guidance and temporal-lock parameters so resumed videos cannot silently mix incompatible continuity settings.
- Added CI coverage for the canonical ControlNet-first runtime and a temporal-lock image smoke test.

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
- Fixed ControlNet discovery for A1111 installations where `sd-webui-controlnet` serves `/controlnet/*` normally but those routes are absent from `/openapi.json`. The canonical runtime now probes `/controlnet/version`, `/controlnet/model_list`, `/controlnet/module_list`, and `/controlnet/control_types` directly before falling back to route discovery.

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
