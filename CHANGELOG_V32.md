# ComicFrame Studio v3.2 — Processing Presence

v3.2 keeps the v3.1 interface and v3.0 render engine unchanged, while making long renders visibly and continuously alive.

## Processing feedback

- Adds a dedicated processing activity card only while a job is running.
- Pulses the main `PROCESSING` action state every 500 ms, independent of render progress.
- Adds an elapsed-time heartbeat that continues moving during long single-frame SDXL inference.
- Converts the renderer's existing `index/total: frame_N.png` state into a clear `FRAME X / Y` readout.
- Translates extraction, shot analysis, assembly, audio restore and upscale phases into concise operator-facing activity text.
- Updates the large preview with a newly completed styled frame every five rendered frames.
- Marks the preview `LIVE · X/Y` only after that output frame actually exists on disk.
- Switches the preview badge to `FINALIZING` during assembly/audio/output finishing.
- Shrinks the full-width red cancel bar into a compact secondary `CANCEL` action.
- Visually suppresses the process browser while rendering so the active job owns the hierarchy.

## Engine behavior

No diffusion, ControlNet, Reference Lock, Shot Memory, optical-flow, Render Intelligence, cache invalidation, frame signature, assembly or media-integrity behavior is changed.

## Cache compatibility

Presence metadata lives inside `simple_shell`, which is already removed by resume-profile normalization. Compatible v3.1/v3.0 render caches remain reusable.
