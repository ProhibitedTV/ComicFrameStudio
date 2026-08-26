# ComicFrame Studio v3.3 — Aggro Controls

v3.3 keeps the video-in / style / video-out product shape and adds only three understandable creative controls.

## Public controls

- `CONTROLNET` — on/off structural lock. On is the default.
- `AGGRO` — stronger redraw mode. On is the default.
- `STEPS` — 12–36 sampling steps, default 24. Lower values trade refinement for materially faster renders.

## Aggro behavior

Aggro is a pipeline mode, not a cosmetic post-effect. It:

- raises diffusion denoise / redraw authority
- weakens ControlNet weight even when ControlNet remains enabled
- ends structural guidance earlier
- gives Experimental styles more freedom than stable styles
- strengthens deterministic style finishing
- reduces temporal smoothing enough to preserve authored variation
- reduces source-frame blending so outputs read as redraws instead of filtered footage
- appends a transformation-oriented prompt clause while retaining subject/action/composition constraints

With `CONTROLNET` off, the structural ControlNet unit is disabled and the ControlNet preflight requirement is removed. Reference/Shot Memory continuity remains available to the deeper engine.

## Cache correctness

`controlnet`, `aggro`, and `steps` live in top-level `creative_controls` render-profile metadata. Changing any of them invalidates incompatible styled-frame cache instead of silently reusing old pixels.

## Unchanged

No new sampler, CFG, denoise, guidance, temporal, Reference Lock, Shot Memory, checkpoint, project or backend controls are exposed in the normal UI.
