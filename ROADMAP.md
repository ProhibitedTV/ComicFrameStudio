# Roadmap

## Next: v1.6 — temporal animation language

Primary goal: make neighboring styled frames feel like one authored animation rather than independent paintings.

- test optical-flow-assisted previous-frame guidance
- evaluate keyframe + propagation workflows
- add shot-change detection so temporal state resets at cuts
- add optional motion-on-twos / held-frame timing without changing clip duration
- add controlled smear-frame / impact-frame treatment for high-motion moments
- add A/B test-video generation from a selected frame range
- add frame-to-frame consistency metrics / contact sheets

## v1.7 — style model workflow

- checkpoint-family compatibility hints
- LoRA metadata / trigger-word display when available
- saved named style stacks combining checkpoint + LoRA + ControlNet + Graphic Print Finish
- optional multiple LoRAs with per-model weights
- style-stack import/export
- curated guidance for illustration/comic versus photoreal checkpoints

## v1.8 — render operations

- ETA / frames-per-hour telemetry
- pause/resume controls
- per-frame retry policy and failure quarantine
- render queue with named profiles
- optional automatic fallback 1280 → 1024 → 768 inference after recoverable GPU errors

## v1.9 — finishing / output

- optional AI upscale pass
- color-script presets
- test-contact-sheet export
- side-by-side original/styled comparison video
- optional texture plate overlays beyond generated print grain

## Technical debt

- move presets to data/config files
- add unit tests for pure media/profile helpers
- add API mock tests for A1111 checkpoint/sampler/LoRA/ControlNet discovery and error handling
- split the stable core into a package when the v1.x surface stops moving rapidly
- choose a license before broader distribution
