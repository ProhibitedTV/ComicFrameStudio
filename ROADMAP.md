# Roadmap

## Next: v1.5 — temporal consistency

Primary goal: make neighboring styled frames feel like one animation rather than independent paintings.

- test optical-flow-assisted previous-frame guidance
- evaluate keyframe + propagation workflows
- add shot-change detection so temporal state resets at cuts
- add A/B test-video generation from a selected frame range
- add frame-to-frame consistency metrics / contact sheets

## v1.6 — render operations

- ETA / frames-per-hour telemetry
- pause/resume controls
- per-frame retry policy and failure quarantine
- render queue with named profiles
- optional automatic fallback from native → 1280 → 1024 inference after recoverable GPU errors

## v1.7 — quality / finishing

- optional AI upscale pass
- post-process halftone/CMYK/ink effects as deterministic compositing layers
- optional motion-on-twos / held-frame timing pass
- impact-frame and smear-frame tools
- color-script presets

## Technical debt

- collapse legacy versioned implementation layers into a small package once the v1.x feature shape settles
- move presets to data/config files
- add unit tests for pure media/profile helpers
- add API mock tests for A1111 model/sampler discovery and error handling
- choose a license before broader distribution
