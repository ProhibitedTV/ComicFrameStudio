# ComicFrame Studio v2.9.2 — Project / Source Usability

This hotfix addresses two source-loading failures exposed by normal Windows usage after the v2.9.1 stability audit.

## Fixed

- Source preview generation no longer writes `_source_preview.jpg` into an unclaimed project directory. UI previews now live under the operating-system temp directory.
- Auto-created `<video>_comicframe` folders left in the preview-only v2.9.1 failure state are recovered automatically and safely.
- Recovery remains strict: custom folders or folders containing any additional reserved/generated ComicFrame paths are not auto-claimed.
- Video probing now retries progressively more portable ffprobe queries when a build rejects the rich `stream_side_data` show-entries expression.
- ffprobe failures now surface the real stderr diagnostic and selected source path instead of only `returned non-zero exit status 1`.
- Source-preview failures are non-fatal and explicitly report that rendering can continue.

## Render compatibility

v2.9.2 does not alter diffusion, ControlNet, reference, subject, timing, or frame-render signatures. Existing compatible v2.9.1 render caches remain reusable.
