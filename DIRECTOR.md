# ComicFrame Studio v2.2 — Easy Shot Director

v2.2 changes the normal ComicFrame workflow from a wall of rendering controls into a simple shot-oriented process.

## Normal workflow

```text
1. Choose video
2. Sync WebUI
3. Analyze Shots
4. Pick a Treatment
5. Preview Project
6. Render Video
```

Easy Mode is enabled by default. The detailed StylePack, ControlNet, optical-flow, Shot Memory and API-contract panels still exist, but they are hidden until **Easy Mode · hide advanced controls** is unchecked.

## Automatic shot analysis

`Analyze Shots` extracts frames when necessary and scans neighboring source frames at a small CPU-side proxy resolution. A cut is accepted only when both of these signals agree:

- meaningful mean pixel change
- meaningful grayscale-histogram disagreement

A minimum shot length suppresses clusters of false cuts around flashes or rapid motion.

The resulting plan is stored in:

```text
comicframe_timeline.json
```

Each shot records a frame range, style, starting intensity, ending intensity and interpolation curve.

## Treatments

### Clean Comic
Restrained `Clean Graphic Novel` throughout the video.

### Dark Video Essay
Mostly `Neo-Noir`, with occasional cleaner graphic-novel shots to keep long sequences readable.

### Clean → Chaos
Starts restrained, moves through strong comic treatment, escalates into `Dream Collapse` / `Signal Rupture`, then uses completely original footage for the final shot when the video has enough detected shots.

### Reality Break
Mostly clean illustrated footage with a surreal middle section and a return to original footage.

### Product Promo
Uses `Corporate Propaganda` as the base treatment with occasional high-impact `Graphic Shock` shots.

### Keep It Stable
Uses the source-faithful RTX-3060 profile at conservative intensity.

## Optional per-shot editing

The Easy Shot Director exposes only four decisions:

```text
Shot
Look
Intensity
Motion
```

### Look
Human-readable choices map to the full StylePack library:

```text
Original Footage
Clean Comic
Comic
Dark / Noir
Cyberpunk
Horror
Dream / Surreal
Glitch
Painted
Analog
Product Promo
```

`Original Footage` bypasses Stable Diffusion for that shot and writes a source-faithful PNG at the active inference dimensions.

### Intensity

```text
Low
Medium
High
Insane
```

Intensity is a meta-control. It drives the underlying systems together rather than forcing the user to coordinate them manually:

- diffusion denoise
- diffusion step budget / CFG
- deterministic graphic FX intensity
- ControlNet structural pressure
- ControlNet guidance duration
- temporal stabilization
- Shot Memory strength
- final source-vs-style presentation blend

The selected StylePack defines the artistic target; Intensity controls how hard ComicFrame moves toward it.

### Motion

```text
Stay
Build
Fade
```

`Build` eases from a lighter treatment into the selected intensity. `Fade` does the opposite. `Stay` holds intensity constant.

## Preview Project

Preview Project renders one representative middle frame from up to eight shots and builds:

```text
DIRECTOR_PREVIEW.jpg
```

The contact sheet labels each representative shot with its Easy Mode look and effective intensity. These preview frames deliberately do not create persistent Shot Memory anchors.

## Render behavior

For each frame ComicFrame resolves:

```text
frame number
  -> shot
  -> StylePack
  -> interpolated intensity
  -> effective diffusion / ControlNet / FX / temporal settings
```

The existing v2 stack then remains intact:

```text
Shot Director
  -> Shot Memory pre-diffusion conditioning
  -> hardened A1111 / Forge img2img contract
  -> ControlNet source lock
  -> deterministic StylePack finish
  -> optical-flow temporal stabilization
  -> Director source/style presentation blend
  -> persistent Shot Memory anchor
```

Shot Memory wraps the Director output, so anchors contain the final visible frame rather than an intermediate pre-director render.

## Shot-aware resume

The timeline that produced a full render is copied to:

```text
comicframe_timeline.rendered.json
```

The render profile also records the current timeline hash.

When the timeline changes, ComicFrame compares the effective old and new plan for every source frame. Only rendered frames whose effective style/intensity changed are deleted. Unchanged frames stay cached and the normal full render skips them.

Because Shot Memory anchors contain historical style information, changing any already-rendered directed frame clears the full-render Shot Memory anchor cache. It does **not** delete unaffected styled output frames.

Changes to non-timeline render infrastructure—checkpoint, inference mode, sampler, ControlNet model, and similar controls—still require a clean compatible render profile rather than silently mixing incompatible generations.

## Advanced Mode

Uncheck **Easy Mode · hide advanced controls** to reveal the existing technical panels. Nothing was removed. Advanced Mode remains available for experiments that need direct access to the full pipeline.