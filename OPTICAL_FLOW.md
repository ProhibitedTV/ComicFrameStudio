# ComicFrame Studio v1.9 — Optical Flow Temporal Transport

v1.9 upgrades ComicFrame's temporal continuity from static-pixel reuse to motion-aware style transport.

## Why this exists

The v1.6 Basic temporal lock compares consecutive source frames and blends the previous stylized frame only where source pixels stay visually similar. That works well for static backgrounds but naturally weakens during camera movement, head turns, walking, hand motion, and moving product shots.

Optical-flow transport estimates where visible content moved, warps the previous stylized frame into the new coordinates, and only then blends trusted regions into the current render.

```text
previous source ─┐
                 ├─ optical flow ─ current→previous map
current source  ─┘                 + confidence
                                      ↓
previous styled frame ─────────── warp into current coordinates
                                      ↓
current diffusion render ───── confidence-gated temporal blend
                                      ↓
                                stabilized frame
```

## Engines

### Off
No temporal stabilization.

### Basic
The v1.6 source-difference lock. This remains useful as a dependency-free fallback and a debugging baseline.

### Optical Flow · Fast
The new default. Computes dense Farnebäck flow near a **512-pixel long edge**. This is intended for normal RTX 3060-class ComicFrame work because Stable Diffusion remains the dominant render cost.

### Optical Flow · Quality
Runs a larger **768-pixel long-edge** flow proxy with more pyramid levels, a larger solve window, additional iterations, and Gaussian Farnebäck refinement. Use it for difficult motion or important final shots when the Fast transport still slips.

## Confidence system

ComicFrame does not blindly copy the warped previous render. A transported pixel must survive multiple checks:

1. **Forward/backward consistency** — previous→current flow and current→previous flow should agree after remapping.
2. **Photometric agreement** — the previous source, warped into the current frame, should still resemble the current source.
3. **Bounds validity** — flow landing outside the previous frame is rejected.
4. **Confidence floor** — the UI threshold removes weak matches before temporal blending.

This is especially important around hands, newly revealed background areas, occlusion edges, fast motion, and objects entering/exiting frame.

## Scene cuts

Basic temporal locking primarily used whole-frame source difference. v1.9 optical modes require both:

- sufficiently large mean source-frame change, and
- low grayscale histogram correlation.

That makes a normal camera pan less likely to be mistaken for a hard cut while still preventing style memory from crossing actual edits.

## Blend strength

The existing **Temporal strength** control remains the maximum transported-style contribution. A value of `0.35` means a fully trusted optical-flow region can receive up to roughly 35% warped previous style and 65% current render. Low-confidence regions automatically receive less or none.

Style packs continue to set their own temporal strengths. Experimental styles therefore remain freer than product/dialogue presets even when both use optical flow.

## Dependency and fallback

v1.9 adds:

```text
numpy
opencv-python-headless
```

If OpenCV cannot import on a particular machine, ComicFrame still launches. Selecting either optical mode logs the problem and falls back to **Basic** rather than aborting a render.

## Recommended first comparison

Use a short 30–60 frame source containing visible motion and compare:

```text
Engine: Basic
vs.
Engine: Optical Flow · Fast
```

Keep every other render setting identical. Good test footage includes a head turn, arm/hand movement, a camera pan, or a product moving across frame.

Look specifically for whether facial inks, clothing texture, halftone patterns, paint character, and product edges travel with the object instead of being regenerated in unrelated positions.

## Next architecture step

Optical flow gives ComicFrame short-term visual memory between adjacent frames. The natural v2.0 direction is **shot memory / keyframe reference conditioning**: retain a chosen artistic reference for the shot while optical flow handles local motion between neighboring frames.
