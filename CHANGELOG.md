# Changelog

## v3.6.3 — Resume Profile Migration

### Long-render resume compatibility
- Fixed a regression where the v3.6.2 resilience metadata itself was treated as a render-setting change, preventing an existing project from resuming after upgrading.
- Treat backend-resilience version/configuration metadata as operational state rather than pixel-affecting render state.
- Treat product/style-library version stamps as migration metadata while continuing to compare the actual public render controls.
- Checkpoint, sampler, scheduler, inference geometry, ControlNet on/off, steps, style policy, and lower-engine settings still invalidate incompatible caches normally.
- Added regression coverage proving a v3.5 project can resume under v3.6.3 when only version metadata changed, while real ControlNet, steps, or checkpoint changes are still rejected.

## v3.6.2 — Long-Render Resilience

### Backend survival
- Extended the legacy img2img HTTP read timeout from one hour to six hours by default so legitimately slow SDXL + ControlNet frames are not killed by the client.
- Added a 24-hour default recovery window for transient Forge/A1111 disconnects and restarts.
- Recovery uses bounded backoff followed by once-per-minute health polling.
- Waits for the backend to be healthy and idle before retrying an interrupted frame to avoid duplicate generations competing for VRAM.
- Refreshes WebUI capabilities and restores checkpoint/ControlNet state after a backend restart.
- Preserves completed frame checkpoints throughout recovery and keeps OOM/NaN errors distinct from recoverable transport failures.
- Added environment overrides for per-frame read timeout and backend recovery-window duration.

## v3.6 — Weighted Prompt Hierarchy

### Style authority
- Added explicit A1111/Forge `(text:weight)` attention to every public non-diagnostic Look.
- High-stability, Medium, and Experimental Looks now use different style-anchor, redraw, material, continuity, and anti-photo weight budgets.
- Experimental Looks receive the strongest visual-language and redraw emphasis; continuity stays deliberately lower so identity/action remain readable without overpowering the style.
- Added weighted negative pressure against photorealistic surface fidelity, literal camera texture, unchanged photographic materials, and weak filter-only stylization.
- Escapes literal `()[]` before wrapping weighted style anchors so generated prompts remain valid A1111/Forge attention syntax.
- Bumped the style-library cache version so v3.5 frames cannot be reused under the new prompt-attention policy.

## v3.5 — Simple Product Consolidation

### Product architecture
- Replaced the `simple → interface → presence → aggro → style_overhaul` production inheritance ladder with one canonical `comicframe_product.py` shell over `comicframe_simple.py`.
- Split public style registration into `comicframe_style_library.py`; style registration no longer owns or subclasses the application UI.
- Retired obsolete product-shell modules and their version-specific tests.
- Kept the mature engine/audit modules intact.

### Functional improvements
- Added a searchable Look browser for the expanded style library.
- Persist the last Look, ControlNet choice, and Steps between launches.
- Gate the primary action until a real source file exists.
- Preserve live rendered-frame preview, progress heartbeat, elapsed time, cancel, and result actions in the consolidated shell.
- Added Copy Path to result actions.
- Corrected `Chrome Nightmare` and `Neon Ruin` to use artistic finish implementations that actually exist.

### CI / repository cleanup
- Consolidated the workflow fanout into one CI workflow.
- Added workflow concurrency so superseded runs cancel automatically.
- The single workflow compiles the repo, imports the canonical product/engine, runs all pytest regressions, and smoke-checks ControlNet/style contracts.
- Removed redundant version-specific changelog files; this file is now canonical.

## v3.4 — Aggressive Styles by Default
- Removed AGGRO as a public control and made authored redraw the default style policy.
- Expanded the public library with 22 aggressive styles.
- Retuned existing public styles with family-specific redraw/ControlNet/temporal floors and caps.

## v3.3 — Tiny Creative Controls
- Introduced public ControlNet, AGGRO, and Steps controls.
- Kept deeper renderer controls engine-owned.

## v3.2 — Processing Presence
- Added visible render heartbeat, elapsed time, frame progress, and live styled-frame preview.

## v3.1 — Focused Interface
- Added responsive video preview, visible process browser, compact progress, and result card.

## v3.0 — Video In / Video Out
- Introduced the simple product boundary over the mature renderer.

## v2.x — Engine hardening and continuity
The v2 series built and audited the underlying engine: ControlNet structure locking, artistic style packs, optical-flow temporal transport, Shot Memory, Shot Director, Reference Lock, Project Workspace, Subject Library, Render Intelligence, AutoPilot, WebUI compatibility, project/media integrity, VFR timing, safe resume invalidation, and runtime stability.
