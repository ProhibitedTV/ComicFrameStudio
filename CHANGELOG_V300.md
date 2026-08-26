# ComicFrame Studio v3.0 — Video In / Video Out

v3.0 is an operator-surface reset, not a renderer rewrite.

## Product contract

The default UI is now:

**Video → Process → Process Video → Result**

Everything else is hidden.

## Kept under the hood

The existing ControlNet, Reference Lock, Shot Memory, optical-flow continuity, Render Intelligence, AutoPilot, source/media integrity, resume/cache and Forge/A1111 compatibility layers remain in the runtime.

## Removed from normal UI

Project selection, backend configuration, ControlNet controls, sampler/checkpoint controls, reference controls, shot editor, subject library, performance controls, advanced toggles and the technical log console are no longer part of the operator surface.

## Output behavior

Working state is derived automatically from the selected source. Completed MP4s are copied beside the source with a process-specific, non-destructive filename.

## Compatibility

The simple-shell metadata is explicitly excluded from frame-cache compatibility checks. v3.0 does not change the meaning of existing render signatures merely because the UI became smaller.
