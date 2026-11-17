# Dream Rotoscope, real preview, and temporal transport validation

## Scope and baseline

Base: `main@5341245`. Before editing: **82 passed, 3 skipped** in 3.25 s on Windows, Python 3.12. The three skips require symlink creation privileges. No compatible backend was listening at the configured `127.0.0.1:7860`; real diffusion comparison and GPU throughput remain unmeasured.

Final local regression: **117 passed, 3 skipped** in 5.72 s. Compilation, focused Ruff checks for new code and `git diff --check` passed. Real FFmpeg tests ran; only the three existing symlink tests were skipped. CI separately verifies the branch on Linux.

The five opportunities ranked after inspecting the architecture:

| Rank | Opportunity | User benefit | Risk | Effort |
| --- | --- | --- | --- | --- |
| 1 | Correct shared transport confidence and coordinate handling | Less stale paint at motion/occlusion boundaries | Moderate: changes rendered pixels | Moderate |
| 2 | Expose bounded real diffusion preview | Test a Look with one generation, without extracting the whole video | Moderate: project lifecycle | Moderate |
| 3 | Register Dream Rotoscope through existing finishing | Original paint/ink treatment with useful defaults | Moderate: artistic acceptance still needed | Moderate |
| 4 | Capture public choices before workers | Consistent Look, steps and ControlNet across a job | Low | Low |
| 5 | Profile broader decode and I/O work | Potential full-render throughput benefit | Moderate: correctness-sensitive | Unmeasured |

The first four form this implementation. Broad throughput rewrites were deferred; no new temporal engine, application subclass, model dependency, inference concurrency or checkpoint-switching mechanism was added.

## Existing pipeline and the changes

`app.py` installs resilience and FFmpeg compatibility before exposing the product shell. `comicframe_product` bridges public choices into `comicframe_simple`. The mature cooperative engine still owns extraction, Director, recurring subjects, reference backends, Shot Memory, adaptive inference, media verification and resume.

During each directed frame, Shot Memory may condition **img2img init only** using warped prior style and anchor palette statistics. The optional structural Canny unit retains the untouched current source. Diffusion is followed by deterministic finishing, then optical-flow stabilization, source-intensity blending and anchor capture. Render Intelligence shares raw flow between the conditioning and final stabilization stages.

Changes at those boundaries:

- One confidence implementation now serves both cached and uncached flow. It computes forward/backward agreement and photometric confidence, then caps feathered confidence by its original value. Smoothing cannot promote a rejected pixel.
- Upsampled confidence retains rejected support and checks full-resolution remap bounds. Prior styled images are resized into current output coordinates before remapping; this fixes adaptive-resolution Shot Memory alignment.
- Known Director shot starts bypass prior-shot conditioning and stabilization, even for similar histograms. Shot Memory records a new cut anchor.
- Raw flow keys include `2-occlusion-safe`. Loaded arrays must have valid shapes, finite values and bounded confidence. The render profile retains this pixel-affecting algorithm version; old rendered caches are preserved but cannot silently mix algorithms.
- Public source, project, Look, ControlNet and Steps live in a frozen `RenderRequest` for the job. Hidden defaults are applied on the main thread. Internal historical engine Tk state remains a documented limitation.

## Dream Rotoscope

The style library registers this High-stability Fine Art Look through existing `StyleSpec`/`StylePack` infrastructure. Internal defaults are denoise 0.58, CFG 5.5, structural weight 0.80 through 0.82 guidance, and temporal strength 0.26. Public Steps still wins; ControlNet off removes structural pressure.

Its prompt asks diffusion for expressive rotoscope painting, ochre/teal pigment harmony, stable anatomy and simplified detail. Finishing uses a small bilateral pass, continuous fixed Lab tonal bands, selective broad-edge ink and subtle image-derived pigment relief. It uses no random field, per-frame palette fitting, coordinate noise or animated texture phase. Print halftone, grain, misregistration and generic ink/posterization are disabled. When all common print operations are disabled, that stage skips a redundant PNG decode/encode.

This is deterministic finishing of a diffusion render. Finishing alone does not establish an authored artistic result, and no face/hand improvement is claimed without real footage review.

## First-frame preview

Select a video and Look, then **PREVIEW FRAME**. A lossless first source frame is extracted with a one-frame decode limit. The canonical engine renders it at its inference resolution, with the captured Steps/ControlNet choices and existing backend preflight/recovery. The app shows ORIGINAL and STYLIZED side by side and explicitly labels the result as a first-frame appearance preview.

Storage is an independently owned `<source>_comicframe/previews/first_frame/` subproject. It holds a full source fingerprint, separate source/test frames, profile and comparison PNG. Extraction checks ownership, PNG validity and source mutation; source identity is checked again before presenting the completed result. Preview never completes or invalidates full-render frames. Cancel/error restores the selected full project, and a cancelled full job cannot publish a stale earlier final video.

A first frame cannot assess continuity, later shots or sequence progression. Double-click the compact preview to open the comparison at full size; the PNG path is also shown under Result. A 2–5 second sequence preview is deliberately the next vertical slice.

## Repeatable synthetic evaluation

```powershell
python -m pip install -r requirements.txt pytest
python -m pytest -q -rs
python tools/evaluate_temporal.py --output docs/evidence/temporal-fast.json --clips
python tools/evaluate_temporal.py --quality --output docs/evidence/temporal-quality.json --clips
```

The harness generates its own source/illustration sequences with seed 734. It compares the baseline confidence algorithm frozen from `5341245` against the current algorithm using identical Farneback solves, strength 0.35 and floor 0.35. Cases cover static content, translation/pan, a moving occluder, lighting changes and a cut. Optional MP4s show **source | baseline | patched** at 12 fps. No third-party footage is needed. Metrics use uncompressed arrays, not the exported codec output.

Motion-compensated difference and edge difference use known fixture motion with visibility masks. Ghosting error measures deviation from fresh current stylization on occluder/exposed-border regions; it is a proxy, not perceptual truth. Gradient detail retention guards against winning by blurring or freezing the scene. The cut fixture applies the same known boundary to both runs; separate tests verify that the live engine honors Director boundaries.

Measured occlusion case (OpenCV 4.14, NumPy 2.3.5, single CPU flow thread):

| Metric | Fast baseline → patched | Quality baseline → patched |
| --- | --- | --- |
| Ghosting proxy, lower is better | 2.347 → 2.178 (**−7.2%**) | 1.999 → 1.862 (**−6.9%**) |
| Edge difference, lower is better | 1.784 → 1.691 (**−5.2%**) | 1.499 → 1.446 (**−3.5%**) |
| Gradient detail retention, near 1 | 0.979 → 0.986 | 0.994 → 0.997 |
| Motion-compensated pixel difference | 4.226 → 4.259 (**+0.8%**) | 4.194 → 4.216 (**+0.5%**) |

Rejecting more history sacrifices a small amount of pixel stabilization. The improvement is narrower: less ghosting with better gradient retention, not a universal flicker reduction. Static/lighting/cut edge differences are almost unchanged and slightly higher in some cases. Fast exposed-pan-border error fell from 0.069 to 0; Quality fell from 0.047 to 0.026. Flow-pair solve time was approximately 15–16 ms Fast and 28–30 ms Quality at 256×160, shared by both comparisons. These numbers do **not** measure a renderer speedup or GPU inference.

Raw results and generated comparison stills: [Fast](evidence/temporal-fast.json), [Quality](evidence/temporal-quality.json), [synthetic montage](evidence/temporal-fast.png). Synthetic differences are intentionally subtle; these are not example diffusion artworks.

## Integration and remaining acceptance

Automated coverage includes confidence masks, adaptive size changes, cache restart/floor reuse and corrupt arrays, explicit cuts, unchanged source ControlNet geometry, deterministic finishing, preview isolation, cancellation, source mutation, and backend errors. Real FFmpeg/ffprobe tests reconstruct generated CFR and VFR media, retain frame count/dimensions/audio/duration, and reject corrupt cached frames before replacing an existing final output.

The installed FFmpeg 9 rejected the engine's `-vsync` flag. The existing compatibility boundary now learns that rejection once per executable and retries the equivalent `-fps_mode passthrough` or `vfr` option. Old builds keep their original commands; unrelated failures are propagated. Real FFmpeg 9 media tests passed; older builds are covered by mocked compatibility regressions.

Optional native integration smoke (requires a working Tk display):

```powershell
python tools/smoke_desktop.py --output docs/evidence/native-smoke.json
python tools/smoke_desktop.py --controlnet --output docs/evidence/native-controlnet.json
```

Both tests use **mocked WebUI responses**, generated video/audio, the actual app class and actual FFmpeg. They completed one preview request followed by six full-render requests, preserving the selected 12 steps and ControlNet choice. ControlNet-on requests retained byte-identical source images in their structural units. Native widget geometry placed the main controls inside a 940×900 window; screenshot capture failed, so this is not a subjective layout review. Reports: [off](evidence/native-smoke.json), [on](evidence/native-controlnet.json).

Before accepting the signature look, render the same authorized 2–5 second clips on `5341245` and this branch with identical checkpoint hash, seed, steps, resolution and ControlNet model. Review faces, hands, occlusions, pans and shot cuts at normal speed and frame-by-frame; retain raw frames and record settings. The baseline has no Dream Rotoscope preset, so compare temporal changes using a shared existing Look first, then review Dream Rotoscope as a separate creative choice. No real-backend visual acceptance, RTX 3060 VRAM/throughput result, or long-shot identity guarantee is asserted here.

Next milestone: a bounded sequence preview through this same engine, followed by real-backend artistic review and complete immutable engine configuration.
