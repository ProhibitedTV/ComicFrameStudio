# ComicFrame Studio v3.1 — Interface Pass

v3.1 keeps the v3.0 video-in/process/video-out engine contract and aggressively improves only the operator interface.

## Interface changes

- Replaces the stacked form layout with a two-column workspace.
- Adds a large responsive source/result preview canvas.
- Fixes the v3.0 preview-height bug that could collapse the image into a thin strip.
- Replaces the process combobox with a visible scrollable process browser.
- Shortens noisy internal process labels while preserving canonical engine names underneath.
- Shows category/continuity metadata in human-facing language only.
- Keeps one dominant `PROCESS VIDEO` action.
- Shows Cancel only while processing.
- Uses compact status + percentage progress presentation.
- Hides the Result card until a finished video actually exists.
- Promotes `OPEN VIDEO` as the primary post-render action.
- Keeps project paths, ControlNet, checkpoints, samplers, Reference Lock, Shot Memory, Render Intelligence and other engine details completely hidden.

## Compatibility

No render semantics are changed. The v3.1 interface metadata is stripped by the existing simple-shell resume compatibility normalization, so compatible v3.0 caches remain reusable.
