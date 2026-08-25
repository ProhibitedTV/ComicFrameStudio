# ComicFrame Studio v2.5 — Render Intelligence

v2.5 is an efficiency release for RTX 3060-class local rendering. The goal is not to make Easy Mode more complicated; the goal is to stop spending expensive work uniformly when shots have very different needs.

## Easy Mode

The Project Workspace adds one project-level control:

- **Fast** — favor 768 inference and lower diffusion-step targets.
- **Balanced** — default. Easy shots use 768; moderate/hard shots use 1024.
- **Quality** — favor 1024 and higher step targets.

`Retry OOM at 768` is enabled by default. If a 1024/native diffusion frame fails with a recognizable VRAM allocation error, ComicFrame retries that frame once at 768 with a reduced step target and low-VRAM ControlNet enabled. It does not restart the entire project.

## Adaptive render planner

Shot analysis produces cheap source metrics from a few representative frames:

- source motion/change
- edge/detail density
- requested artistic intensity
- subject-consistency pressure

Those values produce an `easy`, `moderate`, or `hard` tier. Original Footage is `bypass`.

Current policy:

| Mode | Easy | Moderate | Hard |
| --- | --- | --- | --- |
| Fast | 768 / 16 steps | 768 / 19 | 768 / 22 |
| Balanced | 768 / 18 | 1024 / 22 | 1024 / 26 |
| Quality | 1024 / 22 | 1024 / 26 | 1024 / 30 |

The step target is applied after the selected StylePack has produced its normal settings. Fast/Balanced cap unnecessary diffusion work. Quality may raise the step count for difficult shots.

The generated plan is written to:

```text
cache/render_intelligence/render_plan.json
```

Source-only shot features are cached separately at:

```text
cache/analysis/shot_features.json
```

## Optical-flow reuse

Before v2.5, normal continuity could solve essentially the same source motion twice for the same frame pair:

1. Shot Memory needed transport before diffusion.
2. Optical Flow temporal stabilization needed transport after diffusion.

Their confidence floors differ, but the expensive forward/backward Farneback solve does not need to differ.

v2.5 caches the raw backward flow plus pre-threshold confidence. Each caller then applies its own confidence floor. The first caller is a cache miss; the second caller reuses the same solve.

The cache is both in-memory and persistent:

```text
cache/flow/<content-hash>.npz
```

The key includes the actual grayscale source proxies and Fast/Quality solve mode, so a stale flow field cannot be silently reused for changed source pixels.

## OOM recovery

When an API error contains a recognized CUDA/VRAM allocation failure and the current directive is above 768:

1. remove any partial output for that frame;
2. switch that frame to 768 inference;
3. reduce its diffusion-step target by four, with a 14-step floor;
4. enable low-VRAM ControlNet for the retry;
5. retry exactly once.

Other errors still propagate normally. A failed retry does not loop.

## Cache / resume behavior

v2.4 rendered timelines do not contain Render Intelligence metadata. Those already-completed frames are preserved on upgrade rather than discarded merely because v2.5 exists.

Once a project has a v2.5 rendered timeline, changes to performance mode, adaptive resolution, or adaptive step decisions participate in per-frame invalidation. Only frames whose effective v2.5 directive changed need to be removed.

## Why no Canny-map cache yet?

ControlNet already accepts the untouched current source image and owns its preprocessing contract. Replacing that with precomputed detector maps is backend/preprocessor-version sensitive and can change semantics (especially with Pixel Perfect behavior). v2.5 therefore takes the safer high-ROI optimization first: source analysis and optical-flow reuse. A detector-map cache should only be added behind explicit ControlNet capability/version validation.

## Recommended RTX 3060 workflow

Use **Balanced** for normal project work. Use **Fast** when exploring several looks or transitions. Use **Quality** only after the creative direction is settled or for shots where 1024/extra steps visibly matter.

The Project Workspace still provides Quick Look, Preview Shot, Sequence Preview, Compare Looks, selected-shot rerender, and selective project resume; v2.5 simply makes the expensive path smarter when those actions actually invoke diffusion.
