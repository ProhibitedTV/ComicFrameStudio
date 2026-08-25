# ComicFrame Studio v2.9.1 — Stability Seal

v2.9.1 is the close-out of the second senior audit of the v2 renderer. It does not add another art subsystem; it tightens the boundaries around source identity, project ownership, resume, final media, backend failures and long-running in-process state.

## Source and project integrity

- New projects use full-file SHA-256 source identity.
- Legacy v2.8 projects are checked against decoded source frames before cached GPU work is preserved.
- Project ownership is recorded in `.comicframe_project.json` before ComicFrame performs destructive generated-state cleanup.
- Ambiguous generic folders are refused instead of assuming `frames/`, `cache/`, `subjects/`, etc. belong to ComicFrame.
- Source/project changes in one running application clear process-local timeline, subject, Shot Memory, flow and reference-cache state.
- Source mutation during extraction is detected; the source is reverified before final assembly.
- Generated directories, manifest paths and individual frame leaves reject symlink escapes.
- Persisted leaf names reject traversal, separators, drive syntax and Windows reserved device names.

## Media correctness

- `0/0` ffprobe rate metadata falls back to a valid rate.
- Display geometry comes from extracted pixels so autorotated phone footage uses the dimensions the renderer actually sees.
- Source per-frame timing is captured and cached.
- Variable-frame-rate projects are reassembled from per-frame durations rather than flattened to average FPS.
- Final silent/final MP4s are encoded to temporary files, probed for dimensions/duration/streams, then atomically replace prior outputs only after validation.
- Original audio is bounded to the styled video timeline without `-shortest` truncating valid video.

## Resume and backend resilience

- Corrupt cached PNGs are rejected and rerendered.
- Resume profile normalization preserves equivalent v2.8/v2.9 frames when only audit/lifecycle metadata changed.
- Timeline/reference/subject/render-plan signatures continue to own selective pixel invalidation.
- Transient WebUI 429/5xx/network failures get bounded retries.
- OOM/NaN remain on their specialized recovery paths rather than being hidden by generic retry.
- ControlNet unit capacity is probed; a one-unit configuration preserves Canny and falls back to Shot Memory for reference continuity.
- Repeated frame/reference base64 encoding uses a bounded process-local LRU cache.

## Operations and previews

- Render progress reports measured seconds per frame and a rough EMA ETA once real samples exist.
- STOP attempts the WebUI interrupt endpoint and preserves resumable completed frames.
- Window close while rendering requests a safe stop and waits for the worker to exit.
- Compare Looks restores the persisted timeline after temporary comparison renders.
- Sequence Preview also emits an original-vs-styled comparison MP4.

## Repository cleanup

- `app.py` is a small stable launcher again.
- The exact v2.8 runtime is preserved in `comicframe_runtime_v28.py`.
- v2.9 media hardening lives in `comicframe_runtime_v29.py`.
- v2.9.1 lifecycle/source-finalization guarantees live in `comicframe_stability.py`.
- README, roadmap and known-limitations documentation were rewritten to match the current product instead of v1/v2.0-era state.

## Regression coverage

Second Audit CI covers the older hardening suite plus dedicated tests for:

- full-vs-sampled source fingerprint changes
- VFR timestamp normalization
- invalid `0/0` FPS metadata
- seven-digit frame numbering
- corrupt and symlinked PNG rejection
- project ownership and safe reset
- Shot Memory/manifest path confinement
- Windows reserved manifest leaves
- ControlNet unit capacity
- transient retry classification
- ETA formatting
- stable launcher routing
- in-process project/source context reset
- exact-source finalization checks
- resume-profile migration
- bounded reference encoding cache

The historical subsystem CI suites remain in place and must all pass on the same final head before merge.
