# ComicFrame Studio v2.0 — Shot Memory

Shot Memory closes the temporal loop in ComicFrame Studio.

v1.9 optical flow stabilizes a frame **after** Stable Diffusion has rendered it. v2.0 also carries trusted style information **into the next img2img request before diffusion starts**.

## Why this exists

Frame-by-frame diffusion can make locally plausible decisions that drift over time:

- ink shapes change from frame to frame
- painterly textures re-form in different places
- faces keep the same geometry but change rendering language
- product highlights and color treatment wander
- environmental texture shimmers even when motion is coherent

Fixed seeds and ControlNet help, but neither tells the next diffusion request how the previous frame was actually drawn.

Shot Memory does.

## v2.0 frame pipeline

```text
current source frame
       │
       ├──────────────→ untouched Canny ControlNet image
       │
       └→ current source geometry
              +
          optical-flow-warped previous stylized frame
              +
          low-strength palette statistics from current shot anchor
              │
              ↓
       memory-conditioned img2img init
              │
              ↓
        Stable Diffusion / LoRA
              │
              ↓
     deterministic style finishing
              │
              ↓
      v1.9 optical-flow temporal lock
              │
              ↓
       final stabilized frame
              │
              └→ periodic shot reference anchor
```

The crucial safety split is that **ControlNet never receives the memory composite**. It continues to receive the untouched current source frame, so style memory cannot silently become structural guidance.

## Default controls

```text
Shot Memory:       ON
Memory strength:   0.22
Palette strength:  0.10
Anchor refresh:    24 frames
Confidence floor:  0.45
```

These defaults are intentionally conservative. Memory is confidence-masked and capped; it is not a raw crossfade from the prior render.

## What the controls mean

### Memory strength

Controls the maximum contribution of the optical-flow-warped previous stylized frame to the next img2img initialization.

- `0.10–0.20`: light continuity assistance
- `0.20–0.30`: normal production range
- `0.30–0.45`: aggressive style persistence
- above `0.45`: useful experimentally, but can resist legitimate appearance changes

### Palette strength

Applies a low-strength LAB color-statistics transfer from the latest shot anchor to the current source before transported style is blended in.

This is geometry-free. It helps a shot remember overall color language without copying anchor shapes.

### Anchor refresh

The final stabilized output is periodically copied into:

```text
shot_memory/full/references/
```

Anchors are also created immediately after a scene cut. The default refresh interval is 24 frames.

### Confidence floor

Shot Memory reuses only regions where optical flow is trustworthy. Confidence combines:

- forward/backward flow agreement
- current-vs-warped-source photometric agreement
- valid in-frame coordinates

Higher values are more conservative. Lower values carry style through harder motion but accept more risk.

## Scene cuts

A hard cut resets transported memory before diffusion. The first rendered frame of the new shot becomes a new anchor.

Cut detection uses both gross pixel change and histogram disagreement, matching the v1.9 anti-pan logic.

## Test renders

Test renders use their own memory scope:

```text
shot_memory/test/
```

That directory is rebuilt for each test render, so an old experiment cannot quietly contaminate a new A/B test.

The first frame of a selected test range renders without prior memory. Subsequent frames build memory normally.

## Full-render resume

Full-shot anchors persist under:

```text
shot_memory/full/
```

The normal ComicFrame render profile records all Shot Memory settings. Changing memory strength, palette strength, anchor interval, or confidence floor blocks an incompatible full-render resume instead of mixing generations.

## Recommended first comparison

Use the same 30–60 frame clip with visible motion.

First render:

```text
Shot Memory: OFF
Temporal engine: Optical Flow · Fast
```

Second render:

```text
Shot Memory: ON
Memory strength: 0.22
Palette strength: 0.10
Temporal engine: Optical Flow · Fast
```

Look specifically at:

- face rendering during head turns
- hands and carried objects
- clothing texture
- repeated ink/paint marks
- background surface treatment during camera movement
- product shape and highlight consistency

## When to turn it down

Reduce Memory strength when:

- lighting changes rapidly inside one continuous shot
- the intended effect is deliberate visual collapse
- a subject transforms dramatically
- the style should mutate rather than remain coherent

For **Dream Collapse**, **Signal Rupture**, and similarly unstable presets, a lower Shot Memory strength can preserve the intended chaos while optical-flow post stabilization still protects readable motion.
