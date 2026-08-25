# ComicFrame Studio v2.4 — Project Workspace

v2.4 turns Easy Mode into the normal day-to-day editing surface. The rendering engine is still the v2.1-v2.3 stack underneath, but the user should not have to administer that stack just to make a video.

## Normal workflow

1. Choose a source video.
2. Sync WebUI or click **Check Setup**.
3. Click **Analyze Shots**.
4. Select shots visually from the thumbnail strip.
5. Adjust only the selected shot's **Look**, **Intensity**, **Motion**, and **Subject** consistency if needed.
6. Use **Quick Look**, **Preview Shot**, **Sequence Preview**, **Compare Looks**, or **Preview Project** before committing GPU time.
7. Click **RENDER VIDEO**.

Advanced Mode still exposes the full style, ControlNet, optical-flow, Shot Memory, Reference Lock, and API-contract controls.

## Shot strip

Each detected shot gets a cached 160×90 source thumbnail under:

```text
cache/shot_thumbnails/
```

The strip shows compact render state:

- `✓` — current shot plan is fully rendered and reusable.
- `↻` — rendered files exist but the shot plan changed and needs rerendering.
- `◐` — partially rendered.
- `○` — not rendered yet.
- `SRC` — Original Footage shot.
- `LOCK` — subject consistency is Locked.

Clicking a thumbnail selects that shot. Left/right arrow keys move between shots.

## Selected-shot inspector

Easy Mode exposes four creative controls:

- **Look**
- **Intensity**
- **Motion**
- **Subject** consistency

The inspector also exposes direct shot operations:

- **Preview Shot** — render one representative shot frame using the real pipeline.
- **Sequence Preview** — render a short contiguous clip around the shot transition and encode a small MP4.
- **Rerender Shot** — invalidate and rerender only the selected shot; final-video assembly is intentionally skipped.
- **Use Original** — make that shot source footage with no diffusion.
- **Compare Looks** — render four useful looks for the same representative frame.
- **Copy Look / Paste Look** — transfer style/intensity/motion/subject settings without copying a shot-local reference image.
- **Reset Shot** — restore the treatment-generated defaults for that shot.
- **Another Reference** — cycle through v2.3's shot-local stable reference candidates.

## Quick Look

**Quick Look** is CPU-cheap. It builds a contact sheet from cached styled representative frames where available, otherwise source thumbnails. It does not run Stable Diffusion.

Output:

```text
previews/QUICK_LOOK.jpg
```

## Sequence Preview

Sequence Preview chooses a contiguous range around the selected shot's transition into the next shot. It uses the existing test-render pipeline so ControlNet, Shot Memory, Reference Lock, style finishing, and API hardening remain in effect.

Output:

```text
previews/sequence/SHOT_XX_SEQUENCE.mp4
```

## Compare Looks

The selected shot can be rendered temporarily as:

- Clean Comic
- Dark / Noir
- Dream / Surreal
- Glitch

The comparison does not persist those temporary look changes into `comicframe_timeline.json`.

Output:

```text
previews/look_compare/shot_XXXX/COMPARE_LOOKS.jpg
```

## Work remaining

The workspace compares the current reference-aware per-frame plan against `comicframe_timeline.rendered.json` and the actual styled PNG cache. It reports:

```text
frames total · reusable · need work · shots changed
```

This is a workload count, not a fake time estimate.

## Autosave and history

Shot edits continue to autosave to `comicframe_timeline.json`. v2.4 keeps up to 30 prior timeline snapshots in memory for session **Undo / Redo**.

Keyboard shortcuts:

```text
← / →     previous / next shot
P         preview selected shot
R         rerender selected shot
O         use original footage
Ctrl+Z    undo
Ctrl+Y    redo
```

## Check Setup

Easy Mode's **Check Setup** summarizes whether the local production path is ready:

- ffmpeg / ffprobe
- Forge/A1111 API connection
- active checkpoint
- ControlNet availability
- best Reference Lock backend
- detected VRAM when available

The detailed v2.1 API contract diagnostics remain available in Advanced Mode.

## Friendly errors

The workspace translates common failures into actionable Easy Mode messages, including:

- CUDA / VRAM exhaustion → recommend 768 inference
- missing required ControlNet → Sync WebUI / compatible Canny model guidance
- WebUI connection failure → start Forge/A1111 API and retry
- NaN generation → lower inference or change sampler/checkpoint
- checkpoint verification failure → backend did not confirm model switch

Raw details are still written to the log.

## Project organization

v2.4 adds two user-readable project areas without moving older engine state and breaking compatibility:

```text
project/
  comicframe_timeline.json
  comicframe_timeline.rendered.json
  comicframe_profile.json
  source_info.json

  frames/
  styled_frames/

  previews/
    QUICK_LOOK.jpg
    look_compare/
    sequence/

  cache/
    shot_thumbnails/

  shot_memory/
  test_frames/

  FINAL_STYLED.mp4
```

Older v2 engine directories remain where they were so existing projects can resume safely.

## Resume compatibility

v2.4 UI-only workspace metadata does **not** invalidate otherwise-compatible v2.3 render caches. Actual shot reuse is still governed by reference-aware frame signatures covering style, intensity, Reference Lock level/frame/backend/model, plus the existing non-timeline render compatibility checks.
