# ComicFrame Studio v2.7 — AutoPilot

v2.7 makes the normal product contract explicit:

> choose a video → choose a treatment/performance → **ANALYZE + RENDER** → get `FINAL_STYLED.mp4`

All earlier systems remain available as optional overrides, but the user should not have to manually manage shots, recurring subjects, reference backends, temporal continuity, inference size, or resume behavior for a normal render.

## Easy Mode workflow

1. Choose the source video.
2. Choose a Treatment.
3. Choose Performance: Fast / Balanced / Quality.
4. Leave Creative on Balanced unless a more conservative or more aggressive plan is wanted.
5. Click **ANALYZE + RENDER**.

`Probe first` is enabled by default. It renders a few representative frames before the full job and rejects obviously broken/blank output before hundreds of frames are attempted.

## What AutoPilot plans

AutoPilot runs the existing shot detector and treatment planner, then applies cheap source-aware guardrails:

- high-motion shots can receive slightly less artistic intensity in Safe/Balanced creative modes;
- Wild preserves the treatment's requested intensity;
- v2.5 Render Intelligence still owns adaptive 768/1024 inference and diffusion-step targets;
- Original Footage shots still bypass Stable Diffusion completely.

AutoPilot metadata is stored under `cache/autopilot/autopilot_plan.json`.

## Automatic recurring-subject hints

The v2.6 Subject Library remains fully usable manually, but it is not required for AutoPilot.

AutoPilot compares representative source frames between shots using a cheap deterministic visual metric. Only high-confidence groups are promoted automatically. The thresholds are deliberately conservative:

- Safe: 0.95
- Balanced: 0.92
- Wild: 0.88

Low-confidence/singleton shots remain shot-local. Manual Subject Library assignments always win.

Auto-generated subjects use deterministic IDs derived from the source fingerprint and shot group. They intentionally use one stable project reference across the group so the feature actually provides cross-shot continuity rather than choosing every shot as its own reference.

## Architecture

```text
AutoPilot
   ↓ orchestration only
Subject Library
   ↓ recurring identity
Render Intelligence
   ↓ GPU effort / flow cache / OOM recovery
Project Workspace
   ↓ editorial UI
Reference Lock
   ↓ IP-Adapter / reference-only / Shot Memory fallback
Shot Memory
   ↓ cut-local temporal continuity
Shot Director
   ↓ look / intensity / treatment
Optical Flow
   ↓ motion transport
ControlNet
   ↓ current-source geometry
```

AutoPilot does not carry Shot Memory across cuts and never replaces the current-source Canny geometry image with a project reference.

## Quality probe

When enabled, AutoPilot renders up to four representative frames:

- first shot;
- hardest Render Intelligence shot;
- highest-intensity shot;
- one recurring-subject shot when available.

It rejects missing/tiny images, nearly solid black/white output, and pathologically flat output. The source/result sheet is written to:

`previews/AUTOPILOT_PROBE.jpg`

Probe details are written to:

`cache/autopilot/quality_probe.json`

## Failure recovery

v2.5 already retries a VRAM allocation failure once at 768 with lower steps and low-VRAM ControlNet.

v2.7 adds a second narrow fallback: if an optional IP-Adapter/reference-only backend fails, the current action is retried through the built-in Shot Memory reference backend. Core Canny/geometry failures are not silently hidden.

Existing rendered frames remain reusable during a retry.

## Final verification

After assembly AutoPilot checks:

- `FINAL_STYLED.mp4` exists and is non-trivial;
- output duration is close to source duration;
- if the source has audio, the final output also has audio;
- final video dimensions are reported.

The report is stored at:

`cache/autopilot/final_verification.json`

AutoPilot does not report `RENDER COMPLETE ✓` until these checks pass.

## Manual override philosophy

Every AutoPilot decision remains editable after analysis. If one shot is wrong, use the Project Workspace to change that shot and rerender it. AutoPilot is the default path, not a lockout from the rest of ComicFrame Studio.
