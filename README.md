# ComicFrame Studio

ComicFrame Studio is a local desktop app that turns ordinary video into aggressively stylized animation through an AUTOMATIC1111/Forge-compatible Stable Diffusion WebUI API.

**Current product runtime: v3.5 · Simple Product Consolidation**

The public workflow is intentionally small:

```text
choose video
→ choose look
→ optional ControlNet structure rail
→ choose steps
→ PROCESS VIDEO
→ open result
```

Everything else—shot detection, reference locking, subject continuity, temporal transport, adaptive rendering, cache safety, VFR reconstruction, audio restoration, and backend compatibility—is engine-owned.

## What v3.5 changes

v3.5 consolidates the product around one canonical shell instead of stacking a new UI class for every release.

Production now enters through:

```text
app.py
  → comicframe_product.py
      → comicframe_simple.py
          → mature engine stack
```

`comicframe_product.py` owns only the public experience and render-policy bridge. `comicframe_style_library.py` owns public style registration. Engine modules stay independent.

The old `interface → presence → aggro → style_overhaul` application inheritance ladder is retired.

## Public controls

Normal use exposes only:

- **Look** — searchable style/process library
- **ControlNet** — on/off structural rail
- **Steps** — 12–36, default 24
- **Process Video**

Aggressive redraw is the baseline policy. There is no AGGRO toggle.

The app remembers the last selected Look, ControlNet choice, and Steps between launches.

## Functional behavior

The simple product shell includes:

- source/result preview
- searchable style browser
- automatic shot-aware sequence treatments
- live rendered-frame preview during processing
- elapsed-time processing heartbeat
- compact cancel action
- result actions for open, show in folder, save copy, and copy path
- primary action gating until a real source file exists
- non-destructive output naming beside the source video

The source video is never overwritten.

## Production pipeline

```text
source video
    ↓
source fingerprint + project ownership validation
    ↓
ffmpeg frame extraction + source timing capture
    ↓
shot analysis / treatment
    ↓
source frame
    + Shot Memory
    + reference / subject conditioning
    ↓
Stable Diffusion img2img
    + optional source Canny ControlNet
    ↓
deterministic style finishing
    ↓
optical-flow temporal stabilization
    ↓
validated styled PNG cache
    ↓
VFR-aware video reconstruction
    ↓
source audio restoration
    ↓
validated final MP4
```

ControlNet always uses the current source frame for geometry. Turning ControlNet off removes that structural unit; continuity systems remain engine-owned.

## Quick start

### 1. Start Stable Diffusion WebUI

Use Forge or AUTOMATIC1111 with API access enabled.

For ControlNet mode, install `sd-webui-controlnet` and a compatible Canny model. ComicFrame capability-detects the local backend rather than assuming one fixed model name.

### 2. Launch ComicFrame

Windows:

```bat
run_comicframe_studio.bat
```

Or:

```bash
python app.py
```

Python dependencies are listed in `requirements.txt`. `ffmpeg` and `ffprobe` must be available on PATH.

### 3. Process

1. **CHOOSE VIDEO**
2. choose a Look
3. leave **ControlNet** on for a loose structural rail, or turn it off for freer redraw
4. choose Steps
5. **PROCESS VIDEO**
6. open the result

Project/cache storage is derived from the source automatically.

## Style library

The public library combines shot-aware sequences with aggressive single-style passes. Current examples include:

- Graphic Shock
- Cyberpunk Print
- Toxic Xerox
- Photocopier Riot
- Newsprint Panic
- Bootleg Anime Print
- Street Poster Melt
- Chrome Nightmare
- Dead Channel
- Acid Cathedral
- Synthetic Fever
- Neon Ruin
- Memory Burn
- Paranoid Broadcast
- Heavy Gouache
- Ink Brutalism
- Pastel Nightmare
- Pulp Oil
- Storybook Ruin
- Charred Sketch
- Neo-Noir
- Manga Motion
- Risograph Zine
- VHS Horror
- Signal Rupture
- Watercolor Wash
- Clean Graphic Novel

The browser is searchable because the library is intentionally large.

## Project layout

A typical generated project contains:

```text
<source>_comicframe/
  .comicframe_project.json
  source_info.json
  comicframe_timeline.json
  comicframe_profile.json
  frames/
  styled_frames/
  subjects/
  shot_memory/
  previews/
  cache/
  styled_silent.mp4
  FINAL_STYLED.mp4
```

Generated state is contained inside the owned project directory.

## Architecture

### Product

- `app.py` — stable launcher
- `comicframe_product.py` — single public UI + public render-policy bridge
- `comicframe_style_library.py` — curated style registration and aggressive redraw baseline
- `comicframe_simple.py` — one-button video processing boundary over the engine

### Engine

- `comicframe_director.py` — shot detection and treatments
- `comicframe_reference_lock.py` — shot-local reference conditioning
- `comicframe_subjects.py` — recurring subjects across cuts
- `comicframe_shot_memory.py` — pre-diffusion temporal/style memory
- `comicframe_optical_flow.py` — post-diffusion temporal transport
- `comicframe_efficiency.py` — adaptive render intelligence
- `comicframe_autopilot.py` — automatic orchestration
- `comicframe_webui_contract.py` — Forge/A1111 capability contract
- `comicframe_media.py` — project/media integrity
- `comicframe_manifest_safety.py` — persisted-path confinement
- `comicframe_runtime_v28.py`, `comicframe_runtime_v29.py`, `comicframe_stability.py`, `comicframe_usability.py` — hardened engine compatibility/audit boundaries

The versioned engine compatibility modules are intentionally retained because they carry audited media/resume behavior. Product-shell version layers are not.

## CI

The repository uses one GitHub Actions workflow.

It:

- compiles the repository
- imports the canonical product and major engine modules
- runs the full pytest regression suite
- smoke-checks ControlNet payload compatibility
- verifies the public style registry

Workflow concurrency cancels superseded runs so a multi-file change does not create another queue storm.

## Safety / resume guarantees

ComicFrame retains the hardened engine behavior from the v2.8–v2.9 audit series:

- full-file source fingerprints
- strict generated-project ownership
- corrupt cached PNG rejection
- symlink/path-confinement checks
- bounded transient WebUI retries
- adaptive OOM handling
- atomic validated final-media replacement
- source mutation checks
- VFR timing preservation
- selective compatible-frame reuse

See `KNOWN_ISSUES.md` for current non-blocking debt.

## Engine documentation

- `PROJECT_WORKSPACE.md`
- `AUTOPILOT.md`
- `DIRECTOR.md`
- `REFERENCE_LOCK.md`
- `SUBJECT_LIBRARY.md`
- `SHOT_MEMORY.md`
- `OPTICAL_FLOW.md`
- `EFFICIENCY.md`
- `CONTROLNET.md`
- `WEBUI_CONTRACT.md`
- `TROUBLESHOOTING.md`
- `AUDIT.md`
- `ROADMAP.md`
- `CHANGELOG.md`
