# Book Scene Motion Design

## Purpose

Book-style videos need a renderable motion contract, not just a prompt phrase.
The `Narrative History` look requires two linked surfaces:

- A persistent open-book frame for normal scenes.
- A page-turn transition that shares the same page geometry, inset, material,
  color, and shadow language.

The immediate production target is a higher-quality generated book-page turn
for archival/history explainers. The longer-term target is a reusable animation
foundation for magazine flips, photo albums, document reveals, map unfolds, and
other editorial transitions.

## Styles

- `page-turn`: legacy alias for an FFmpeg slide-style transition.
- `book-page-turn`: basic generated book transition using FFmpeg filter layers.
- `book-page-turn-v2`: generated higher-fidelity page turn using real frame
  imagery, warped page geometry, shadows, highlights, and shared book geometry.
- `stock-book-page-turn`: licensed-asset path for purchased stock footage.

## Shared Geometry

`BookSceneSpec` is the source of truth for:

- output size
- outer page rectangle
- content inset
- paper colors
- page edge color
- background color
- gutter/shadow color

Static scene framing and generated page-turn transitions must read from this
same model so a scene and its transition look like the same physical book.

## V2 Acceptance Criteria

The v2 transition is acceptable when:

- The turning page uses actual scene imagery, not only flat color boxes.
- The page visibly changes width and perspective over time.
- The page has a shaded back/front surface, moving highlight, and edge shadow.
- The destination page receives a contact shadow.
- Multiple pages can be flipped sequentially through `page_count`, allowing
  fast blank-page flips for rewind/comeback effects.
- The output is encoded as a normal MP4 transition clip and works with the
  existing compose cache and concat pipeline.

## Motion Review

AI review should inspect sampled motion, not only a still frame. Transition
preview generation also emits a `transitions_motion/*.jpg` sheet that tiles up
to the first 60 frames of the transition. Agents should inspect that sheet when
judging timing, easing, frame-to-frame continuity, and whether the animation
actually reads as motion.

## Future Backends

The current v2 path is dependency-light and implemented with Pillow plus FFmpeg.
A future `webgl_mesh` backend can reuse the same `BookSceneSpec` contract and
replace only the frame generation step. The transition style should stay stable;
renderer backend selection can become a separate field once there is a second
production-ready generated backend.
