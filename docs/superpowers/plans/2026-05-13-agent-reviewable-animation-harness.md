# Agent-Reviewable Animation Harness

Date: 2026-05-13

## Goal

Make animation quality legible to an agent before investing in more renderer
complexity. The harness should let an agent inspect a transition and say where
it fails: frozen frames, black frames, jumps, jitter, blank intervals, weak
motion readability, bad easing, or visual glitches.

Renderer sophistication is secondary. A 2.5D or 3D backend is only useful if the
agent can evaluate the output without waiting for the user to manually review
every artifact.

## Research Notes

Useful inspection layers:

- FFmpeg has production-grade filters for detecting black intervals, frozen
  intervals, VMAF motion scores, video signatures, and SI/TI spatial-temporal
  information. These are good low-level gates and should run before visual
  agent review.
- OpenCV dense optical flow can estimate motion vectors across the whole frame.
  That is a stronger future layer for page-path smoothness, curl direction, and
  "motion went the wrong way" checks.
- SSIM and VMAF-style metrics are useful for regression and reference
  comparison, but they do not by themselves answer whether an animation looks
  like a believable page turn.
- Agent-facing image artifacts are required: sampled-frame contact sheets,
  consecutive-frame diff sheets, motion curves, accumulated motion heatmaps, and
  short clips. Numeric metrics alone are not legible enough.

## Outputs The Agent Can Check

### Tier 1: Cheap Structural Checks

Machine-readable:

- duration, frame count, FPS, resolution
- audio track presence
- black-frame intervals
- freeze/static intervals
- duplicate-frame ratio
- mean luminance range
- per-frame visual delta curve
- per-frame edge delta curve
- SI/TI or VMAF motion summary when available

Agent-readable:

- one sampled-frame contact sheet per transition
- one consecutive-frame diff sheet per transition
- one motion curve image
- one accumulated motion heatmap

This tier catches broken renders, static clips, black frames, sudden jumps, and
motion pulses that are likely to look bad.

### Tier 2: Animation-Semantic Checks

For book/page transitions:

- page edge trajectory should move monotonically according to the intended
  direction
- gutter anchor should remain stable
- page silhouette should change smoothly
- page flip should not become a flat sliding rectangle
- blank-page interval should not dominate the transition unless explicitly
  requested
- reveal of the next scene should be intentional, not a late pop
- repeated multi-page flips should have regular rhythm

This tier needs image-processing heuristics and agent review of visual artifacts.

### Tier 3: Reference-Based Checks

Inputs:

- current generated transition
- prior known-good transition
- licensed/reference transition clip
- candidate renderer output

Checks:

- side-by-side contact sheets
- side-by-side motion curves
- rough SSIM/LPIPS-style regression checks where dependencies are available
- human/agent rubric score against reference qualities

This tier decides whether a new backend is actually better.

## Harness Shape

Add a command:

```bash
uv run pipeline transition review --project-id <ID> --first 4
uv run pipeline transition review --project-id <ID> --transition s1:s2
uv run pipeline transition review --clip path/to/transition.mp4
```

Output under:

```text
output/projects/<ID>/compose/reviews/animation/
  summary.json
  summary.md
  <transition-id>/
    metrics.json
    frames_contact.jpg
    diff_contact.jpg
    motion_curve.jpg
    motion_heatmap.jpg
    optional_short_clip.mp4
    optional_optical_flow.jpg
```

The command should reuse existing preview resolution and transition cache lookup
logic rather than re-rendering clips unless explicitly requested.

## Scoring Contract

Each transition gets:

- `technical_status`: pass, warn, fail
- `motion_status`: pass, warn, fail
- `agent_review_status`: pass, warn, fail
- `confidence`: low, medium, high
- `findings`: concrete timestamp/frame-index issues

Example issue:

```json
{
  "severity": "warn",
  "frame": 31,
  "time_sec": 1.03,
  "type": "motion_spike",
  "message": "Large visual-delta spike during blank-page flip; likely reads as page popping rather than smooth curl."
}
```

## Implementation Plan

### Slice 1: Review Artifacts Without New Dependencies

- Create `pipeline.composer.animation_review`.
- Use FFmpeg/ffprobe plus Pillow/numpy.
- Resolve intro and storyboard transition clips from the current project.
- Generate contact sheet, diff sheet, motion curve, heatmap, JSON, and markdown.
- Add tests around metric summarization and clip resolution.

Exit criterion: the agent can inspect the first few baby-walker transitions and
produce timestamped findings without user review.

### Slice 2: FFmpeg Filter Gates

- Add blackdetect, freezedetect, vmafmotion, and SI/TI summaries when the local
  FFmpeg build supports them.
- Store raw logs and parsed events in `metrics.json`.
- Treat missing filters as skipped checks, not hard failures.

Exit criterion: broken/static/black clips are flagged automatically.

### Slice 3: Book-Specific Heuristics

- Detect page area and vertical page-edge candidates from high-delta/edge maps.
- Track page-edge x position over time.
- Flag non-monotonic jumps, long blank intervals, late reveal pops, and unstable
  gutter movement.

Exit criterion: the harness can distinguish "technically moving" from "reads as
a believable book/page turn."

### Slice 4: Optical Flow Upgrade

- Add optional OpenCV optical-flow support if `cv2` is installed.
- Generate flow magnitude/direction sheets.
- Track motion direction consistency and high-motion outlier regions.

Exit criterion: agent review gets a motion-vector artifact, not only frame
differences.

### Slice 5: Reference Comparison

- Let the user attach or register target reference clips.
- Produce side-by-side reference/candidate sheets and metrics.
- Add a rubric review prompt that compares candidate to reference.

Exit criterion: renderer changes can be judged against a stable target, not only
against subjective memory.

## Baby-Walker First Probe

A temporary prototype was run against the first four transition clips in
`output/projects/20260504-115232-baby-walker-story`:

- intro
- `s1_s2`
- `s2_s3`
- `s3_s4`

Artifacts:

```text
tmp/animation-review-baby-walker-first/
```

Observed:

- All four clips are 1.5s, 30 FPS, 45 frames.
- No black frames were detected by the prototype.
- No frozen/static frame pairs were detected by the prototype.
- All four clips were flagged for repeated large visual-delta spikes.
- Visual sheets show the same pattern: the multi-page flip is readable, but the
  5-page effect creates repeated blank-book intervals and late reveal pulses.

Initial agent judgment:

- Technically valid: yes.
- Smooth enough: borderline.
- Agent-legible failure: repeated motion spikes and blank-page dominance.
- Likely user-visible concern: the transition can read as several fast pops
  through blank pages rather than one physically continuous book animation.

The same prototype was also run against the first three rendered scene clips:

- `s1_scene`
- `s2_scene`
- `s3_scene`

Artifacts:

```text
tmp/animation-review-baby-walker-scenes-first/
```

Observed:

- `s1_scene` has continuous low-to-moderate motion and no freeze/static flag.
- `s2_scene` and `s3_scene` were flagged as mostly static.
- The static flags are not necessarily technical failures, because archival
  still-image scenes can intentionally hold. They are reviewability warnings:
  if the creative requirement is ongoing motion, these scenes need pan/zoom,
  parallax, page-surface motion, or other controlled movement.

Initial agent judgment:

- `s1_scene`: pass for smooth in-scene motion.
- `s2_scene`: warn for static hold.
- `s3_scene`: warn for static hold.
- Likely user-visible concern: after a dynamic opening, the next two history
  scenes may feel visually inert even though the book frame is present.

## Sources

- FFmpeg filters: https://www.ffmpeg.org/ffmpeg-filters.html
- OpenCV optical flow tutorial: https://docs.opencv.org/4.x/d4/dee/tutorial_optical_flow.html
- Netflix VMAF: https://github.com/Netflix/vmaf
- SSIM paper: https://www.live.ece.utexas.edu/publications/2004/zwang_ssim_ieeeip2004.pdf
