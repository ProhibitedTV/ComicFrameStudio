# ComicFrame Studio v3.0 — Video In / Video Out

The operator workflow is intentionally tiny:

1. **Choose Video**
2. Choose a **Process**
3. Click **Process Video**
4. Open the result or save a copy

That is the product.

## What disappeared from the UI

ComicFrame no longer asks the operator to manage:

- project directories
- checkpoints
- samplers or schedulers
- ControlNet modules/models/weights
- reference backends
- subject-lock internals
- temporal/optical-flow settings
- Shot Memory
- Render Intelligence
- AutoPilot configuration
- cache management
- render profiles
- technical logs

Those systems remain in the engine and are selected/configured automatically by the process pipeline.

## Internal working data

Choosing `clip.mp4` silently uses:

```text
clip_comicframe/
```

for extracted frames, caches, timelines and renderer state. This directory is an implementation detail and is not exposed in the v3.0 UI.

## Results

Finished videos are copied beside the source using a non-destructive name such as:

```text
clip_comicframe_signal-rupture.mp4
clip_comicframe_signal-rupture_2.mp4
```

The original source file is never overwritten.

## Processes

The process selector contains two kinds of operations:

- **Single-style passes** such as Signal Rupture, Graphic Shock, VHS Horror, Risograph Zine, Oil Impasto, Cyberpunk Print and Dream Collapse.
- **Shot-aware sequences** such as Clean → Chaos and Reality Break.

A process owns the technical decisions needed to execute it. The operator chooses the visual result, not the renderer implementation.
