# Changelog

## v3.6.2 — Long-Render Resilience

### Unattended render survival
- Raised the img2img client read timeout from the legacy one-hour ceiling to six hours by default so legitimately slow SDXL + ControlNet frames are not killed by ComicFrame itself.
- Added a 24-hour transient backend recovery window with short backoff followed by once-per-minute polling.
- Wait for Forge/A1111 to become healthy and idle before resubmitting a frame after a disconnect, preventing duplicate generations from competing for VRAM.
- Refresh WebUI capabilities, checkpoint state, and the public ControlNet choice after a backend restart before resuming the interrupted frame.
- Expanded transient transport classification while continuing to fail fast on CUDA OOM and NaN failures.
- Kept completed PNG frames as durable checkpoints throughout recovery; backend failures now cost time instead of discarding a multi-day render.
- Added environment overrides for the long frame timeout and backend recovery window.
- Added regression coverage for entrypoint wiring, multi-hour transport timeouts, recovery scheduling, transport scoping, and transient-error classification.

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
