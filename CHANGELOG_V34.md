# ComicFrame Studio v3.4 — Aggressive Styles by Default

v3.4 removes aggression as an operator decision. Choosing a style now means choosing a materially transformative visual process.

## Public UI

The creative surface is reduced to:

- Style
- ControlNet on/off
- Steps (12–36, default 24)

The v3.3 `AGGRO` checkbox is removed from layout. Its stronger-redraw behavior is permanently enabled as part of the style policy.

## Global style retune

Every public style pack receives an aggressive baseline appropriate to its family:

- higher minimum img2img denoise / redraw authority
- lower ControlNet weight when structural guidance is enabled
- earlier ControlNet guidance cutoff
- higher deterministic FX floor
- lower temporal smoothing ceiling
- an authored-reinterpretation prompt clause that preserves identity/action/broad composition without demanding literal edge copying

Experimental styles receive the weakest structural pressure and strongest redraw floor. Stable/commercial styles remain more controlled but are still visibly illustrated rather than lightly filtered.

## New styles

Adds 22 new processes:

- Toxic Xerox
- Punk Flyer
- Newsprint Panic
- Bootleg Anime Print
- Photocopier Riot
- Tabloid Apocalypse
- Stencil Riot
- Street Poster Melt
- Chrome Nightmare
- Blackout Gospel
- Acid Cathedral
- Synthetic Fever
- Neon Ruin
- Dead Channel
- Memory Burn
- Paranoid Broadcast
- Heavy Gouache
- Ink Brutalism
- Pastel Nightmare
- Pulp Oil
- Storybook Ruin
- Charred Sketch

## Engine continuity

ControlNet remains the only public structural switch. Turning it off still removes the ControlNet render requirement and structural unit. Shot Memory, Reference Lock, optical flow and the rest of the continuity engine remain internal.

## Cache correctness

The v3.4 `aggressive-by-default` style policy is render-profile significant. Existing v3.3 frames are not silently reused under the new visual contract.
