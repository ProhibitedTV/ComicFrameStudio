# Senior Engineering Shakedown — v2.8 Runtime Hardening

This audit treats `app.py` as the canonical product boundary and reviews the accumulated v1.x/v2.x cooperative-mixin stack for correctness, resume safety, I/O cost, cache growth, persisted-input safety, and failure recovery.

## Fixed in v2.8

### 1. Source-frame reuse could silently use the wrong video

Previous behavior skipped extraction whenever `frames/` contained anything. That made two cases unsafe:

- an interrupted extraction left a partial frame sequence that was accepted as complete;
- reusing a project directory with another source video could keep stale extracted/styled frames.

v2.8 records a bounded content fingerprint and actual extracted frame count in `source_info.json`, verifies an exact contiguous `frame_000001.png ... frame_N.png` sequence, rebuilds incomplete source frames, and clears ComicFrame-derived project state when source content changes.

Pre-v2.8 projects are migrated without throwing away work when their stored dimensions/FPS/duration and extracted sequence are internally consistent.

### 2. Workspace cache accounting used a v2.3-only dependency signature

The v2.4 workspace still used `reference_plan_signature`, so later Render Intelligence, Subject Library, and AutoPilot changes could be shown as "reusable" even when the renderer correctly considered them dirty.

The canonical runtime now routes workspace cache checks through the newest dependency signature supported by the timeline.

### 3. Selective invalidation had become five nested whole-video passes

Director, Reference Lock, Render Intelligence, Subject Library, and AutoPilot each added another frame-by-frame invalidation layer. For a current v2.7 timeline, the AutoPilot dependency signature already contains all lower dependencies.

v2.8 performs one canonical pass for v2.7+ timelines and falls back to the historical compatibility chain only for older projects.

### 4. Any timeline edit destroyed all persistent Shot Memory anchors

Older invalidation layers safely removed the entire `shot_memory/full` tree whenever any affected frame changed. Correct, but increasingly wasteful as per-shot editing became common.

v2.8 expands changed frames to affected Director shot ranges and prunes only anchors inside those ranges. If the memory manifest is missing/corrupt, it still falls back to deleting the full memory scope rather than risking stale state.

Selected-shot rerender also prunes that shot's stale anchors before rendering.

### 5. Persistent optical-flow cache was unbounded

`cache/flow/*.npz` could grow for the lifetime of a project. v2.8 treats it as an LRU-like persistent cache, touching used entries and periodically trimming oldest files to a 2 GiB / 1600-file ceiling (with an 85% post-GC target).

### 6. Adaptive-resolution final output depended on the first PNG when source upscale was disabled

v2.5 intentionally allows different inference sizes by shot. ffmpeg can decode a variable-size PNG sequence, but without an explicit scale filter the encoder adopts the first frame's dimensions. A first 768-class shot could therefore make an otherwise 1024 project encode at 768.

v2.8 always selects an explicit final output size:

- source dimensions when `Upscale final video back to source resolution` is enabled;
- the user's global inference target otherwise.

The final dimensions are normalized to even values for `yuv420p`/H.264 and AutoPilot verification now treats a dimension mismatch as a failed render.

### 7. Shot analysis was recomputed on every AutoPilot run

AutoPilot called shot analysis every time, and shot analysis itself called extraction again. v2.8 records a shot-analysis signature containing source identity, frame count, detector algorithm version, and cut setting. Matching plans are reused. Clicking **Analyze Shots** explicitly still forces a fresh analysis.

The extraction layer also keeps a short-lived in-process source/sequence memo so nested calls in the same job do not repeat source hashing/probing work.

### 8. Performance / AutoPilot modes were not restored from the loaded timeline

A reopened project defaulted its UI variables to `Balanced`, which could silently rebuild a plan different from the one saved in the project. v2.8 restores persisted Render Intelligence and AutoPilot modes when the timeline is loaded.

### 9. Automatic subjects could accumulate as orphan project data

Changing automatic clustering thresholds/groups created new deterministic `auto_*` subjects while old groups remained in `subjects/` indefinitely. v2.8 garbage-collects unreferenced automatic subjects and their reference directories after a new AutoPilot plan is created. Manual subjects are never collected.

### 10. Assembly only checked counts, not exact frame identity

A stale extra frame and a missing expected frame could pass a simple `len(styled) >= len(source)` check. v2.8 requires the styled frame-number sequence to exactly match the source frame-number sequence and encodes exactly that many frames.

### 11. Persisted manifest paths were trusted too far

Subject IDs/reference filenames and Shot Memory anchor filenames originate in ComicFrame-generated JSON, but project folders can be copied, shared, or hand-edited. Raw path joining meant a crafted `../` value or escaping symlink could point outside the project.

v2.8 treats those values as untrusted leaf components. Subject/reference/anchor access is confined to the expected project directory, malformed subject IDs are dropped/quarantined, and selective Shot Memory cleanup will never follow a manifest filename outside `shot_memory/full/references`.

### 12. Render configuration could be changed while a worker was running

The worker guard prevented starting a second job, but the normal UI controls stayed live. A treatment, performance mode, subject, or other setting could therefore be changed while later frames of the same render were still being produced.

v2.8 disables interactive configuration controls for the lifetime of a worker and restores each control's original state afterward. **STOP remains enabled.** This keeps a single render job internally consistent without removing emergency cancellation.

## Architectural debt deliberately not papered over

### Cooperative mixin depth

The runtime has a deep cooperative MRO. It is tested and currently functional, but the cost of reasoning about `super()` ownership is rising. v2.8 deliberately places cross-generation safety at the canonical `ComicFrameStudioApp` boundary rather than adding another feature mixin.

A future package refactor should converge toward explicit services such as:

- `ProjectStore`
- `RenderPlanner`
- `FrameRenderer`
- `ContinuityEngine`
- `ReferenceProvider`
- `Assembler`

and leave Tk widgets as a thin controller/view layer.

### Tk state is still used as runtime configuration

v2.8 prevents user-driven mid-job changes, but several rendering layers still read/temporarily set Tk variables from worker-driven code. Tk variables are the wrong long-term configuration boundary. A future refactor should snapshot an immutable render configuration before starting a job and pass it through the pipeline instead of using widgets as the mutable configuration store.

### CI is broad but fragmented

The repository has strong smoke coverage across separate workflows, but much of it is inline Python embedded in YAML. v2.8 starts a normal `tests/` tree with pytest; migrating the historical suites there would reduce duplication and make local regression runs substantially easier.

### Automatic subject clustering is conservative, not semantic recognition

AutoPilot's current subject grouping uses deterministic full-frame visual similarity. High thresholds limit damage, but it is not object/face recognition. Low-confidence cases intentionally remain shot-local. If semantic recurring-subject detection becomes important, add a local embedding/detection layer rather than lowering these thresholds.

## Audit principle going forward

The primary product contract remains:

> source video → treatment/performance → one-click render → verified stylized video

New features should be rejected or hidden behind Advanced Mode unless they improve that path, improve output correctness, or measurably reduce work required to produce it.
