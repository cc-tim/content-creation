# 3D Book Page Renderer Evaluation

Date: 2026-05-13

## Context

`book-page-turn-v2` now gives the baby-walker project a stronger book/page
contract using Pillow plus FFmpeg: real frame imagery, perspective warping,
shading, contact shadow, and multi-page flips up to 8 pages.

That is still a 2.5D renderer. The missing qualities in the target
"Shutterstock quality" reference are true 3D page geometry, curled mesh
deformation, visible page thickness, physical lighting, cast shadows, camera
depth, and motion blur.

Current local facts:

- `blender` is not installed on this machine right now.
- `node` and `npm` are installed, but this repo has no Node/Remotion project.
- The existing Python pipeline already has the stable integration point:
  `TransitionConfig` -> `BookPageTurnV2Renderer` -> transition MP4 clip.
- The existing `BookSceneSpec` geometry contract should be reused by any 3D
  backend so static book scenes and transition clips keep matching.

## Recommendation

Build a new Blender-backed generated renderer first, not a browser/WebGL
renderer.

The production shape should be:

```text
book-page-turn-v2
  renderer_mode = generated
  generation_backend = pillow | blender
```

The transition style should stay stable. Backend selection should be a separate
generated-renderer field so existing storyboards do not need another style name
for the same creative intent.

Blender is the best next step because it gives us the hard visual features that
the current renderer cannot produce:

- Real mesh geometry for a page.
- Thickness and page edges through mesh/solidify geometry.
- Physical lights, contact shadows, ambient occlusion, camera perspective, and
  depth of field.
- Engine-level motion blur in final renders.
- Headless command-line rendering for pipeline integration.

Three.js/Remotion is a valid later preview or lightweight renderer, but it would
still require custom page-curl shaders, custom shadow/postprocess work, and a
new browser render stack. It fits interactive previews better than the first
attempt at near-stock transition quality.

## Evaluated Options

### Option A: Keep Improving Pillow/FFmpeg

Complexity: low to medium.

Upside:

- No new runtime dependency.
- Already integrated and tested.
- Fast enough for production iteration.

Limit:

- Perspective transforms are still flat quads, not a curled surface.
- Shadows and highlights are painted approximations.
- There is no physical camera, lens, mesh thickness, deformation blur, or real
  page self-shadowing.

Confidence:

- 85% to make it incrementally better.
- 20% to reach near-stock page-turn quality.

Use this as fallback, not the final answer.

### Option B: Blender Headless Renderer

Complexity: medium-high.

Upside:

- Directly addresses the missing quality dimensions.
- Can be driven headlessly from the pipeline.
- Deterministic analytic mesh animation is possible without relying on cloth
  simulation.
- Can render either fast EEVEE previews or higher-quality Cycles references.

Limit:

- Adds an external binary dependency.
- Needs a standalone render script because Blender's Python environment is not
  the same as the repo's `uv` environment.
- Render time must be measured on this machine after Blender is installed.
- Asset/material tuning matters. A technically correct mesh can still look
  cheap without paper texture, bevels, lighting, and camera polish.

Confidence, assuming Blender can be installed and we have 1-3 target reference
clips:

- 80% to produce a visibly superior 3D book turn within one focused slice.
- 65% to get close to stock-template quality after a second polish slice.
- 45% to match a specific Shutterstock sample closely without buying or
  recreating comparable materials/assets.

This is the recommended path.

### Option C: Three.js or Remotion Three

Complexity: high for production-quality output, medium for a preview-quality
prototype.

Upside:

- Node and npm are already present.
- Three.js has the right primitives for custom geometry, textures, shadow maps,
  tone mapping, and WebGL rendering.
- Remotion can render real MP4 output from React compositions and has a Three.js
  integration.

Limit:

- This repo has no Node project yet.
- Server-side Three.js rendering needs Chromium/WebGL setup and Remotion
  recommends the ANGLE renderer for Three.js server-side output.
- Motion blur is not the same as Blender's render-engine motion blur; it would
  likely be a compositing/postprocess approximation.
- We would still need custom page-curl geometry/shaders and frame export.

Confidence:

- 70% to build a useful web preview and review tool.
- 55% to beat the current v2 renderer.
- 35% to reach near-stock quality without substantial shader/postprocess work.

Use this if interactive editing/preview becomes more important than final-render
quality.

### Option D: Licensed Stock Clip or Overlay

Complexity: low to medium.

Upside:

- Fastest way to real stock quality.
- The code already has a licensed-clip and overlay-oriented path.

Limit:

- The clip may not match exact book geometry, scene texture placement, camera
  angle, or page count.
- Licensing and source tracking must be correct.
- It is less flexible for custom multi-page "rewind/comeback" effects.

Confidence:

- 90% to improve immediate production quality if a matching asset is found.
- 40% to satisfy bespoke story-specific transitions.

Use as production fallback or reference target, not as the generated 3D system.

## Proposed Blender Architecture

Add a generated backend under the current transition system:

```text
src/pipeline/composer/transitions.py
  BookPageTurnV2Renderer chooses generated backend:
    pillow -> current render_book_page_turn_v2()
    blender -> render_book_page_turn_blender()

src/pipeline/composer/book_scene.py
  keeps BookSceneSpec as the shared geometry contract

src/pipeline/composer/book_scene_blender.py
  prepares frames, manifest, temp dirs, and ffmpeg encode
  detects blender binary
  invokes Blender in background mode

tools/blender/render_book_page_turn.py
  standalone Blender Python script
  reads JSON manifest
  creates scene, page meshes, camera, lights, materials
  renders PNG sequence
```

The manifest should contain only primitive JSON:

```json
{
  "width": 1920,
  "height": 1080,
  "fps": 30,
  "duration_sec": 1.5,
  "page_count": 5,
  "frame_a": "/abs/path/a.png",
  "frame_b": "/abs/path/b.png",
  "output_frames": "/abs/path/frames/frame_#####.png",
  "book_geometry": {
    "page_x": 124,
    "page_y": 81,
    "page_w": 1672,
    "page_h": 918,
    "inset_x": 249,
    "inset_y": 177,
    "inset_w": 1422,
    "inset_h": 726
  }
}
```

Implementation details:

- Use an analytic page-curl mesh, not cloth physics, for the first version.
- Use a dense subdivided page grid with UVs mapped to the outgoing frame.
- Animate page vertices from right-to-left across the gutter with a curl radius,
  hinge anchor, and slight vertical lift.
- Add a thin page body or solidified edge material so page thickness is visible.
- Use the destination frame as the page/book surface underneath.
- Instantiate blank intermediate pages for multi-page flips.
- Render the frame sequence with Blender, then encode with the existing FFmpeg
  settings so concat compatibility stays unchanged.
- Keep Pillow v2 as fallback and as a cheap test renderer.

## Benchmark and Measurement Plan

We need two measurement layers: automated gates for regressions, and visual
judgment against reference footage.

### Reference Set

Create a small fixed benchmark set:

- `current_v2`: current baby-walker transition output.
- `stock_ref_1`: a licensed/sample book-page-turn clip at 1080p.
- `stock_ref_2`: a second clip if available, ideally with visible page curl and
  camera depth.
- `blender_candidate`: candidate generated output.

Normalize each clip to the same resolution, FPS, duration, and page-count
intent before comparison.

### Automated Gates

These should run on the transition clip or on the existing motion review sheet:

- Frame count, duration, dimensions, FPS, and audio-track presence match the
  concat contract.
- No black/blank frames except intentional blank book pages.
- Gutter anchor drift stays below 2% of page width.
- Page silhouette area changes smoothly; no large second-derivative spikes.
- Page edge blur width is visible during fastest motion, not a razor-sharp
  sliding polygon.
- The page casts or implies a moving shadow on the destination page in at least
  the middle third of the transition.
- The candidate's transition preview sheet includes at least 8 visually distinct
  motion states for a 1.5s flip.

### Perceptual Metrics

Use metrics cautiously:

- SSIM is useful for regression tests against our own golden renders, but it is
  not enough to decide "stock quality."
- LPIPS can help compare candidate render variants, especially when the same
  source textures are used.
- FVD is designed for video-generation distribution quality, but it is overkill
  and unstable for a tiny set of short transition clips.

The practical approach is: metrics catch regressions and obvious defects;
review sheets decide whether the motion reads as professional.

### Human or Agent Review Rubric

Score each candidate 1-5 on:

- Page curl and geometry.
- Page thickness and material believability.
- Shadow, lighting, and contact with the page below.
- Motion continuity, blur, and absence of popping.
- Match to the intended `Narrative History` book-frame look.

Acceptance gate:

- Average score at least 4.0.
- No individual criterion below 3.
- Candidate beats current v2 in side-by-side review.
- Candidate is within one point of the selected stock reference average.

## Suggested Work Slices

### Slice 1: Dependency and Benchmark Harness

- Add a small transition-evaluation command or script.
- Generate side-by-side review sheets for current v2, candidate, and reference.
- Add machine-readable checks for frame count, duration, dimensions, and blank
  frame detection.
- Document how to install or locate Blender on this machine.

Exit criterion: we can compare current v2 to a reference clip before writing the
new renderer.

### Slice 2: Minimal Blender Backend

- Create standalone Blender script and Python wrapper.
- Render one-page curl using outgoing and incoming frame textures.
- Encode MP4 through existing FFmpeg path.
- Add an integration test skipped when `blender` is unavailable.

Exit criterion: `book-page-turn-v2` can render with `generation_backend=blender`
and produce a valid transition clip.

### Slice 3: Quality Pass

- Add page thickness, paper texture, bevel/edge material, area lights, shadows,
  camera framing, depth, and motion blur.
- Add multi-page sequential flips matching current `page_count` behavior.
- Tune against the baby-walker 5-page/1.5s transition.

Exit criterion: review rubric average is at least 4.0 and clearly beats v2.

### Slice 4: Production Controls

- Expose backend choice in storyboard/API/dashboard only where needed.
- Cache Blender renders using the backend name, render version, and material
  parameters.
- Keep Pillow v2 fallback available for fast drafts.

Exit criterion: production users can choose quality vs speed intentionally.

## Primary Sources Consulted

- Blender command-line rendering: https://docs.blender.org/manual/en/latest/advanced/command_line/render.html
- Blender command-line arguments: https://docs.blender.org/manual/en/4.0/advanced/command_line/arguments.html
- Blender Cycles motion blur: https://docs.blender.org/manual/en/latest/render/cycles/render_settings/motion_blur.html
- Blender Simple Deform modifier: https://docs.blender.org/manual/en/latest/modeling/modifiers/deform/simple_deform.html
- Three.js WebGLRenderer: https://threejs.org/docs/pages/WebGLRenderer.html
- Three.js BufferGeometry: https://threejs.org/docs/pages/BufferGeometry.html
- Three.js CanvasTexture: https://threejs.org/docs/pages/CanvasTexture.html
- Remotion renderMedia: https://www.remotion.dev/docs/renderer/render-media
- Remotion @remotion/three: https://www.remotion.dev/docs/three
- Remotion ThreeCanvas: https://www.remotion.dev/docs/three-canvas
- Remotion motion blur package: https://www.remotion.dev/docs/motion-blur
- SSIM paper: https://live.ece.utexas.edu/publications/2004/zwang_ssim_ieeeip2004.pdf
- LPIPS paper: https://arxiv.org/abs/1801.03924
- FVD paper: https://arxiv.org/abs/1812.01717
