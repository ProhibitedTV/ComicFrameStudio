# ComicFrame Studio v2.6 — Subject Library

v2.6 adds explicit project-level recurring subjects on top of v2.3 Reference Lock and v2.5 Render Intelligence.

## Easy workflow

1. Analyze the video and select a shot containing the recurring person/product/prop.
2. Choose `Person`, `Product`, `Prop`, or `Other` and click **Create from Shot**.
3. Give the subject a human name.
4. Assign it to other shots with the Subject picker or **Assign Through…**.
5. Add alternate angles with **Add Reference** when useful.
6. Use **Check Subject** to render one representative frame from every assigned shot before a full render.

The normal shot controls remain Look / Intensity / Motion / Subject consistency. Backend-specific reference controls stay in Advanced Mode.

## Storage

Subjects are project-local:

```text
project/
  subjects/
    subjects.json
    <stable-subject-id>/
      ref_<stable-reference-id>.png
```

The registry uses stable IDs internally. Display-name changes do not alter render dependencies, so renaming a subject does not invalidate completed frames.

## Multiple references

A subject can hold several references from different shots/angles. When the subject is first assigned to a shot, ComicFrame scores the references against that shot's representative source frame using deterministic CPU-side image features (framing/aspect, luminance, contrast, edge/detail structure and coarse left/right/top/bottom balance).

The chosen reference is then **pinned into the shot timeline**. Adding another reference later does not silently change existing assignments or invalidate frames. Use **Another Reference** to explicitly cycle the selected project reference for a shot.

## Architecture

```text
Project Subject
      |
      +--> pinned best project reference
                    |
                    v
             Reference Lock
          IP-Adapter / reference-only
             / Shot Memory fallback

Current source -------> Canny geometry
Previous styled frame -> Shot Memory (cut-local only)
Render Intelligence --> adaptive GPU effort
```

A recurring subject intentionally survives scene cuts. Temporal Shot Memory does not; scene-cut reset behavior remains unchanged.

## Selective invalidation

Timeline render dependencies include stable subject ID, selected reference ID/content hash, resolved subject type and the existing v2.5 efficiency/reference signature.

- Rename a subject: no rerender.
- Add an unused reference: no rerender.
- Assign a subject to Shot 5: Shot 5 becomes dirty.
- Change Shot 5 to another subject/reference: Shot 5 becomes dirty.
- Change an unrelated subject: unrelated shots remain reusable.

Reference files are content-hashed when the project registry is loaded, so an externally modified selected reference is detected before rendering.

## Subject types

Easy Mode supports:

- **Person** — recognizable identity across cuts.
- **Product** — prioritize stable shape/product appearance.
- **Prop** — prioritize recurring object silhouette/details.
- **Other** — generic recurring visual identity.

v2.6 does not automatically introduce FaceID/PuLID or auxiliary InsightFace/LoRA dependencies. It continues using the capability ladder already proven by Reference Lock.

## Render Intelligence

Assigned recurring subjects add a small difficulty pressure to the v2.5 planner because cross-shot reference conditioning costs GPU work and increases consistency requirements. Product/Prop subjects receive slightly more pressure than Person/Other subjects. Fast/Balanced/Quality remain the only user-facing performance choices.

## Cross-shot check

**Check Subject** renders one representative frame per assigned shot through the real pipeline and creates:

```text
previews/subjects/<subject-id>/SUBJECT_CHECK.jpg
```

Each row shows:

```text
SOURCE | SUBJECT REF | RESULT
```

This is intended to expose identity/product drift before committing the GPU to a full project render.
