# ComicFrame Studio v1.8 — Artistic Expansion

v1.8 expands ComicFrame from a comic/video stylizer into a broader artistic rendering platform while preserving the v1.6/v1.7 ControlNet-first continuity model.

## Library size

The built-in library now contains **44+ pipeline-aware styles**, including **30 new v1.8 packs**.

Each pack owns its own diffusion strength, steps, CFG, ControlNet pressure, guidance end, temporal lock settings, shared Graphic Print Finish toggles, deterministic final grade, negative prompt, and inference preference.

## Families

### Fine Art
- Watercolor Wash
- Gouache Storybook
- Oil Impasto
- Charcoal Study
- Pastel Dream
- Ink Wash

These reduce or disable comic-print effects and use deterministic pigment, paper, relief, charcoal, pastel, or wash finishing instead.

### Cinema & Genre
- Arthouse Melancholy
- Grindhouse Damage
- VHS Horror
- Dystopian Sci-Fi
- Dream-Pop Haze
- Surveillance State

These emphasize cinematic tone, signal character, and genre atmosphere while keeping the source shot anchored.

### Print & Poster
- Risograph Zine
- Screenprint Poster
- Pulp Cover
- Album Art
- Propaganda Poster
- Underground Flyer

These prioritize limited palettes, posterized shapes, physical-print character, and strong graphic hierarchy. Generated lettering is explicitly discouraged in the prompts.

### Experimental
- Glitch Collapse
- Analog Decay
- Liminal Haze
- Relic Iconography
- Brutalist Dreamstate
- Signal Rupture

These intentionally loosen structural/temporal pressure compared with commercial or fidelity presets. They are the place to push media breakdown, displacement, atmosphere, and abstraction.

### Commercial
- Luxury Ad
- Minimal Catalog
- Hype Drop
- Infomercial Fever Dream
- Hero Tech Promo
- Clean Ecommerce

These are product-shape-first presets. ControlNet and temporal pressure are deliberately higher, especially for Minimal Catalog, Hero Tech Promo, Luxury Ad, and Clean Ecommerce.

## Artistic library browser

The desktop UI adds a **3B · Artistic library · v1.8** panel below the normal Look card.

Choose a family, inspect the style description and continuity rating, then click **Apply style**. The ordinary preset controls remain available after applying, so every pack is still a starting point rather than a locked mode.

Continuity labels are intentionally simple:

- **High** — product/dialogue/structure-first work.
- **Medium** — stylized but still conservative enough for ordinary video.
- **Experimental** — intentionally permits more frame-to-frame and environmental transformation.

## Deterministic finishing

The new finishers avoid uncontrolled per-frame randomness. VHS scanlines, film scratches, band displacement, RGB splitting, posterization, pigment softening, monochrome grading, and signal tearing are functions of the source image and frame number.

For the same rendered frame and frame number, ComicFrame should produce the same deterministic finish. CI includes a regression test for this behavior.

## Recommended starting points

For painterly work:

```text
Watercolor Wash
Gouache Storybook
Oil Impasto
Charcoal Study
```

For music/video art:

```text
Album Art
Dream-Pop Haze
Risograph Zine
Signal Rupture
Glitch Collapse
```

For horror/genre work:

```text
VHS Horror
Grindhouse Damage
Pulp Cover
Surveillance State
```

For product promos:

```text
Luxury Ad
Hero Tech Promo
Hype Drop
Corporate Propaganda
Infomercial Fever Dream
Clean Ecommerce
```

For source-faithful baseline comparisons, continue using **Video Fidelity · RTX 3060**.
