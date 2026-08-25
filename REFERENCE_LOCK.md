# ComicFrame Studio v2.3 — Reference Lock

v2.3 adds shot-local subject consistency without turning Easy Mode into an AI control panel.

## Easy Mode

Each shot gets one human control:

- **Normal** — maximum stylistic freedom; no explicit reference conditioning.
- **Strong** — recommended for people, products, props and recurring hero objects.
- **Locked** — prioritize recognizable identity and shape even when the environment/style becomes aggressive.

The selected shot also shows its automatically chosen source reference frame. **Try another reference** cycles through several stable candidates from that same shot.

## Capability ladder

ComicFrame probes the running local ControlNet installation and chooses the strongest safe backend it actually exposes:

1. **IP-Adapter** — only when `ip-adapter-auto` and a checkpoint-family-compatible generic IP-Adapter model are both installed.
2. **ControlNet reference-only** — when a reference-only preprocessor is exposed.
3. **Shot Memory** — always available as the built-in fallback.

No optional reference extension is required for the project to render.

### Why `ip-adapter-auto`

Current `sd-webui-controlnet` exposes an `ip-adapter-auto` preprocessor whose implementation selects the correct concrete preprocessor from the chosen IP-Adapter model. ComicFrame therefore does not hard-code a CLIP-H/CLIP-G preprocessor when Auto is available.

ComicFrame also avoids automatically selecting FaceID/PuLID variants because those can require auxiliary LoRAs or InsightFace dependencies. Generic CLIP IP-Adapter models are preferred for a zero-surprise automatic path.

## SDXL / SD1.x compatibility

Reference Lock compares the active checkpoint family with discovered IP-Adapter model names. SDXL projects only auto-select SDXL IP-Adapter models; SD1.x projects avoid SDXL models.

A model change is resolved into the shot timeline before rendering so a changed reference backend/model participates in selective resume invalidation.

## Architecture

Each conditioning system has one job:

```text
current source frame
  ├─ img2img / current action
  ├─ Canny ControlNet / current geometry
  ├─ shot reference / identity + appearance
  └─ Shot Memory / temporal style continuity
```

The geometry ControlNet unit continues to receive the untouched current source frame. Reference Lock appends a separate ControlNet unit for IP-Adapter/reference-only rather than replacing or mutating Canny.

When neither optional reference backend exists, Strong/Locked temporarily increase Shot Memory transport/palette anchoring for that frame. The UI values are restored immediately after payload construction.

## Reference selection

After shot analysis, ComicFrame considers several frames inside each shot while deliberately avoiding the cut boundaries. Candidate scoring favors:

- useful image detail,
- distance from shot boundaries,
- lower difference from neighboring frames.

The highest-scoring candidate becomes `reference_frame`. Candidate frames are always constrained to that shot's `[start, end]` range, so references cannot leak across scene cuts.

The timeline stores:

```json
{
  "subject_lock": "Strong",
  "reference_frame": 352,
  "reference_candidates": [352, 344, 361],
  "reference_backend_resolved": "IP-Adapter",
  "reference_module": "ip-adapter-auto",
  "reference_model": "ip-adapter-plus_sdxl_vit-h [hash]"
}
```

## Reference strengths

Reference weights are intentionally conservative:

| Mode | IP-Adapter | reference-only |
|---|---:|---:|
| Strong | 0.62 | 0.52 |
| Locked | 0.82 | 0.72 |

Normal does not add a reference unit.

These are separate from Shot Director's visual Intensity. A shot can therefore be:

```text
Look: Dream / Surreal
Intensity: Insane
Subject consistency: Locked
```

which means the environment is allowed to collapse while the subject receives stronger identity/shape anchoring.

## Preview

`Preview Project` becomes a three-column diagnostic contact sheet:

```text
SOURCE | REFERENCE | RESULT
```

This makes it possible to judge both the artistic result and whether the chosen reference is helping before committing to the full render.

## Resume / invalidation

v2.3 extends v2.2's per-frame timeline signature with:

- `subject_lock`,
- `reference_frame`,
- resolved reference backend,
- resolved reference model.

Changing the reference for Shot 7 therefore invalidates Shot 7's affected rendered frames without deleting unrelated completed shots. Shot Memory anchors are rebuilt whenever directed history changes because those anchors encode prior visual history.

## Advanced mode

The advanced Reference Lock panel exposes only one additional policy control:

- Auto
- IP-Adapter
- Reference only
- Shot Memory

If a forced backend is unavailable, ComicFrame logs the condition and falls back safely rather than failing a render.
