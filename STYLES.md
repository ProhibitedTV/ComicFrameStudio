# ComicFrame Studio style packs

ComicFrame Studio v1.7 treats a style as a render-pipeline configuration, not just a prompt preset.

Applying a style can change:

- positive and negative prompting
- img2img denoise, steps and CFG
- ControlNet weight and guidance end
- temporal-lock strength and thresholds
- Graphic Print Finish intensity and enabled components
- deterministic style-specific grading after the common print stack
- inference-resolution preference and fixed-seed behavior

ControlNet remains enabled/required for these production styles. You can still override any visible control after applying a preset.

## Included styles

| Style | Intended look | Structural pressure | Temporal behavior |
| --- | --- | --- | --- |
| **Video Fidelity · RTX 3060** | Source-faithful illustrated footage | High | Balanced stabilization |
| **Graphic Shock · maximum print** | Chaotic mixed-media print / CMYK impact | Medium-high | Looser to retain energy |
| **Comic Punch · strong** | Strong general comic treatment | High | Moderate stabilization |
| **Clean Graphic Novel** | Restrained ink, clean color, minimal glitch | Very high | Strong stabilization |
| **Neo-Noir** | Near-monochrome hard blacks and rim light | High | Strong stabilization |
| **Cyberpunk Print** | Neon cyan/magenta print grime | High | Moderate stabilization |
| **Pulp Horror** | Distressed vintage horror-comic stock | Medium-high | Moderate/loose |
| **Retro 70s Print** | Warm faded four-color offset print | High | Moderate stabilization |
| **Manga Motion** | Monochrome ink and screentone | Very high | Strong stabilization |
| **Dream Collapse** | Subject anchored while environment fractures | Deliberately lower | Loose by design |
| **Corporate Propaganda** | Heroic clean product-ad illustration | Very high | Strong stabilization |
| **Analog Broadcast** | Comic + CRT/public-access signal grime | High | Looser to preserve signal character |
| **Structure First · ControlNet test** | Continuity diagnostic | Maximum | Strong stabilization |
| **Diffusion Only · diagnostic** | Raw diffusion comparison | High ControlNet, no post FX | Temporal finish disabled |

## Deterministic style finishes

Several styles add a final deterministic grading step after diffusion and the shared Graphic Print Finish stack:

- **Neo-Noir** converts the final image to high-contrast monochrome.
- **Manga Motion** uses stronger monochrome contrast and tonal posterization.
- **Retro 70s Print** reduces saturation and adds a warm aged-paper cast.
- **Pulp Horror** darkens/desaturates and applies a restrained brown-red pulp cast.
- **Cyberpunk Print** increases color separation and contrast.
- **Corporate Propaganda** sharpens and cleans the heroic advertising treatment.
- **Analog Broadcast** adds deterministic horizontal scanlines and a small frame-cycling signal ghost.
- **Dream Collapse** adds a restrained deterministic displaced-edge echo.

These finishers are deliberately deterministic so they do not introduce random frame-to-frame shimmer.

## Starting points

For ordinary footage, begin with **Video Fidelity · RTX 3060** or **Clean Graphic Novel**.

For product/promotional comedy, **Corporate Propaganda** is designed to keep the product silhouette readable while exaggerating the visual rhetoric around it.

For the most aggressive interdimensional/glitch-comic result, use **Dream Collapse** or **Graphic Shock · maximum print**. Dream Collapse intentionally reduces ControlNet pressure compared with the fidelity presets so the environment has room to fracture while the subject remains anchored.

For each new shot, render a short test range before committing to the entire video. Style settings are written into the render profile so ComicFrame will not silently resume a sequence with a different style pack.
