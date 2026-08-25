# ComicFrame Studio

ComicFrame Studio is a local desktop application for turning ordinary video into source-faithful AI-stylized animation through an AUTOMATIC1111/Forge-compatible Stable Diffusion WebUI API.

**Current stable runtime: v2.9.1 · Stability Seal**

The source video is never overwritten. ComicFrame extracts frames into a project directory, renders resumable styled PNGs, and creates a separate `FINAL_STYLED.mp4`.

## What the current runtime does

ComicFrame is no longer a simple frame-by-frame img2img batcher. The current stack coordinates:

- automatic shot detection and per-shot art direction
- Canny ControlNet structural locking
- shot-local reference locking with IP-Adapter/reference-only capability detection and Shot Memory fallback
- cross-shot recurring Subject Library references
- pre-diffusion Shot Memory
- optical-flow temporal transport after diffusion
- adaptive per-shot inference resolution and diffusion steps
- one-click AutoPilot planning/probing/rendering
- cached project thumbnails, previews and selective rerendering
- exact source-content identity and safe resume invalidation
- variable-frame-rate timing preservation
- measured render telemetry and rough ETA
- bounded transient WebUI retry and OOM downgrade behavior
- crash-safe final media replacement

## Production pipeline

```text
source video
    ↓
exact source fingerprint + project ownership check
    ↓
ffmpeg frame extraction + original frame timing capture
    ↓
shot analysis / treatment / recurring-subject plan
    ↓
current source frame
    + transported Shot Memory
    + shot/project reference conditioning
    ↓
Stable Diffusion img2img
    + untouched-source Canny ControlNet
    ↓
deterministic graphic/style finishing
    ↓
optical-flow temporal stabilization
    ↓
validated resumable styled PNG
    ↓
VFR-aware video reassembly
    ↓
original audio restoration
    ↓
validated atomic FINAL_STYLED.mp4
```

The structural source sent to Canny remains the current untouched source frame. Style memory and reference conditioning do not replace source geometry.

## Quick start

### 1. Start Stable Diffusion WebUI

Use Forge or AUTOMATIC1111 with its API enabled. For the normal production path, install `sd-webui-controlnet` plus a Canny model compatible with the selected checkpoint family.

ComicFrame capability-detects the WebUI rather than assuming one fixed ControlNet/IP-Adapter installation.

### 2. Launch ComicFrame

On Windows:

```bat
run_comicframe_studio.bat
```

Or with Python:

```bash
python app.py
```

Python dependencies are listed in `requirements.txt`. `ffmpeg` and `ffprobe` must be available on PATH.

### 3. Choose a source and project directory

Use a dedicated ComicFrame project directory. v2.9+ writes a `.comicframe_project.json` ownership marker and refuses to destructively manage an ambiguous folder containing unrelated `frames/`, `cache/`, `subjects/`, or similarly named generated paths.

### 4. Analyze and render

Easy Mode is the intended default surface:

1. choose the source video
2. choose treatment / performance mode
3. **Analyze Shots** or use **AutoPilot**
4. inspect Quick Look / shot previews if desired
5. **RENDER VIDEO**

Completed compatible frames are reused. Timeline/reference/subject/render-plan changes invalidate only the affected work when possible.

## Stability and resume guarantees

The v2.8 → v2.9.1 audit series tightened the project boundary substantially:

- new projects use a full-file SHA-256 source fingerprint
- legacy v2.8 caches are decoded-frame checked before migration
- changing source/project inside one running app clears process-local timeline, subject, flow and memory state
- source files are checked for mutation during extraction and reverified before final assembly
- corrupt cached PNGs are rejected instead of silently skipped as complete
- generated directory and frame symlinks are refused
- manifest filenames are path-confined, including Windows reserved device names
- ControlNet one-unit configurations keep Canny and fall back to Shot Memory rather than overflowing unit capacity
- transient WebUI 429/5xx/connection failures retry a bounded number of times
- OOM remains handled by the adaptive low-resolution retry path rather than generic retries
- final video files are encoded to temporary files, probed, then atomically replace the previous output only after validation
- configuration controls are locked while a worker job is active

## Timing and rotated video

ComicFrame stores the decoded source-frame timing under the project cache. Variable-frame-rate clips are assembled from per-frame durations instead of being flattened to one average FPS.

Display dimensions come from the extracted pixels, so phone footage with rotation metadata uses the geometry the renderer actually sees rather than blindly trusting coded stream dimensions.

## Project layout

A typical project contains:

```text
project/
  .comicframe_project.json
  source_info.json
  comicframe_timeline.json
  comicframe_timeline.rendered.json
  comicframe_profile.json
  frames/
  styled_frames/
  test_frames/
  subjects/
  shot_memory/
  previews/
  cache/
    analysis/
    flow/
    timing/
    render_intelligence/
    autopilot/
  styled_silent.mp4
  FINAL_STYLED.mp4
```

Generated state is deliberately contained inside the project directory.

## Major subsystems

- `comicframe_director.py` — shot detection, treatments and per-frame art direction
- `comicframe_reference_lock.py` — shot-local reference conditioning
- `comicframe_subjects.py` — recurring cross-shot subjects
- `comicframe_shot_memory.py` — pre-diffusion temporal/style memory
- `comicframe_optical_flow.py` — post-diffusion temporal transport
- `comicframe_efficiency.py` — adaptive render intelligence and flow caching
- `comicframe_autopilot.py` — one-click orchestration and verification
- `comicframe_runtime_v28.py` — preserved v2.8 hardening compatibility boundary
- `comicframe_runtime_v29.py` — media integrity, VFR assembly, retry and ETA audit layer
- `comicframe_stability.py` — v2.9.1 process lifecycle/source-finalization seal
- `comicframe_media.py` — pure media/project integrity helpers
- `comicframe_manifest_safety.py` — persisted-path confinement helpers
- `app.py` — intentionally small stable launcher

## Preview tools

The workspace includes:

- Quick Look contact sheet
- per-shot preview
- contiguous Sequence Preview
- original-vs-styled sequence comparison video
- Compare Looks contact sheet
- selected-shot rerender
- use-original bypass
- copy/paste/reset look controls

## Reference and subject behavior

For shot-local consistency, Auto mode prefers:

```text
compatible IP-Adapter
→ ControlNet reference-only
→ built-in Shot Memory fallback
```

If the WebUI exposes only one ControlNet unit, ComicFrame reserves it for Canny structural guidance and uses Shot Memory for identity/style continuity.

Recurring Subject Library assignments intentionally survive cuts; temporal Shot Memory does not.

## Performance

Render Intelligence supports Fast, Balanced and Quality project modes. It analyzes source motion/detail and requested artistic pressure to choose per-shot inference work instead of spending the same GPU budget on every frame.

Raw optical-flow results are cached and reused. Persistent flow cache size is bounded. Repeated reference-image base64 encoding is also bounded and cached in-process in v2.9.1.

## Tests

The repository has dedicated CI for the core renderer, WebUI contract, Shot Memory, Shot Director, Reference Lock, Project Workspace, Render Intelligence, Subject Library, AutoPilot, runtime hardening and the second stability audit.

The second-audit suite covers source fingerprinting, VFR timing, `0/0` FPS metadata, 7-digit frame numbering, corrupt/symlinked PNG rejection, project ownership, manifest confinement, ControlNet unit capacity, retry classification, ETA formatting, stable entrypoint routing, project-context reset, source-finalization checks and resume-profile migration.

## Limitations and maintenance debt

See [KNOWN_ISSUES.md](KNOWN_ISSUES.md). These are current non-blocking limitations/architecture debt rather than known silent-corruption paths.

## More documentation

- [PROJECT_WORKSPACE.md](PROJECT_WORKSPACE.md)
- [AUTOPILOT.md](AUTOPILOT.md)
- [DIRECTOR.md](DIRECTOR.md)
- [REFERENCE_LOCK.md](REFERENCE_LOCK.md)
- [SUBJECT_LIBRARY.md](SUBJECT_LIBRARY.md)
- [SHOT_MEMORY.md](SHOT_MEMORY.md)
- [OPTICAL_FLOW.md](OPTICAL_FLOW.md)
- [EFFICIENCY.md](EFFICIENCY.md)
- [CONTROLNET.md](CONTROLNET.md)
- [WEBUI_CONTRACT.md](WEBUI_CONTRACT.md)
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- [AUDIT.md](AUDIT.md)
- [ROADMAP.md](ROADMAP.md)
- [CHANGELOG_V291.md](CHANGELOG_V291.md)
