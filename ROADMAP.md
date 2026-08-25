# Roadmap

## Current baseline: v2.9.1 · Stability Seal

The v2.x product path is feature-complete enough for long-form local rendering:

- ControlNet-first structural fidelity
- pre- and post-diffusion temporal continuity
- Shot Director treatments
- shot-local reference locking
- recurring Subject Library
- adaptive Render Intelligence
- AutoPilot orchestration
- selective resume/invalidation
- original-vs-styled preview video
- measured ETA and bounded backend retry
- VFR-aware final assembly
- exact source identity / project ownership / path confinement
- crash-safe final media replacement

The next work should reduce architecture complexity rather than add another rendering subsystem.

## Next major target: v3.0 · RenderSession service boundary

Primary goal: keep the current behavior while making it cheaper to reason about and test.

- snapshot immutable render configuration before worker launch
- move renderer state out of Tk variables and widgets
- introduce explicit Project, RenderSession, Backend and MediaAssembler services
- replace cooperative MRO overrides with explicit composition where practical
- keep v2.9.1 project/timeline/profile compatibility through migration adapters
- preserve one small stable `app.py` launcher
- add headless service-level render tests independent of Tk

## Reliability follow-ups

- move remaining inline GitHub Actions smoke scripts into `tests/`
- add a real tiny ffmpeg integration fixture for CFR + VFR assembly duration checks
- add fault-injection tests around interrupted media writes and backend disconnects
- add a synthetic end-to-end project migration fixture spanning v2.2 → current
- add Windows CI for path, device-name and launcher behavior
- add optional periodic project-integrity scan for hand-edited/copied projects

## Optional quality features

These are deliberately lower priority than architecture simplification:

- semantic face/object-assisted recurring-subject suggestions, with manual Subject Library remaining authoritative
- optional AI super-resolution final pass
- render queue with named jobs/profiles
- true pause-after-current-frame in addition to STOP/resume
- import/export of named checkpoint + LoRA + ControlNet + style stacks
- optional multiple LoRAs with per-model weights
- user-selectable motion-on-twos / held-frame timing treatments

## Non-goals for the next cycle

- adding another temporal engine before the existing stack is decomposed
- replacing Canny source geometry with generated/reference geometry
- hiding backend compatibility errors behind silent fallbacks
- sacrificing deterministic resume behavior for speculative speedups

## Exit condition for v3.0

v3.0 should be considered successful if the same real projects render equivalently while the runtime can be understood without tracing a deep cooperative mixin chain. The current v2.9.1 behavior is the compatibility contract, not something to casually rewrite.
