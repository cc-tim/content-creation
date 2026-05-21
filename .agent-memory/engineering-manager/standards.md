# Engineering-manager — standing standards

My accrued engineering bar, applied to EVERY sprint I scope. The `engineering-manager`
skill injects this into my prompt and promotes generalizable lessons here (lean,
Tim-confirmed). Skill-managed.

## The two axes (guard this hardest)

- Richer rendering — charts, animation, overlays — fixes **visual quality / slideshow
  risk**. It does **NOT** add **runtime**. A 4–5 min story rendered beautifully is still
  4–5 min. Runtime is bought with MORE distinct beats (more story / more sources).
- Every sprint names which axis it serves. Never let a sprint claim it "extends the video"
  by dressing up beats already on hand. (Source: producer loop 4, baby-walker — material
  greenlit for ~4–5 min did not reach a 6–8 min ask; charts/animation would not have closed
  that gap.) When Tim sets a longer target, ask which axis the gap is on before scoping.

## Anatomy of a new visual type

Copy a proven precedent — `composer/rich_slide.py` is the reference two-pass shape (Flux
draft background cached by `md5(prompt)` under `work_dir/image_cache/` + Pillow composite +
themed-flat fallback on provider failure + `image_to_video` to mp4). A new type is not done
until it has ALL of:

1. Dispatch branch in `composer/base.py`.
2. Taxonomy entry **with a worked example** in `stages/direct.py` (the model learns the
   data schema by demonstration, not by description).
3. Validation — minimal inline at first (presence/shape), promoted to the E5 storyboard
   validator when that lands.
4. Golden-PNG tests (one per sub-variant).
5. `overlay_rules.py` wiring (does it carry its own text / suppress the narration subtitle?).
6. Eventually: a Style Manifest element (E4) and a dashboard surface (E6).
   Sprints 1–N may defer 6, but must name it as deferred, not forget it.

## Budget discipline ($50/mo cap)

- Flux **draft** tier first ($0.003); promote only approved content.
- Cache by prompt hash — identical prompts hit cache, no API call; re-renders are free.
- Every sprint quantifies its per-project $ cost. Arsenal items are cheap by design
  (Pillow composites over cached backgrounds); if a sprint isn't cheap, say why.

## Sequencing principles

- **Leverage × readiness.** Pick the slice with the highest content value whose
  dependencies already exist. Don't front-load infrastructure the first content win
  doesn't need (chart v1 ships consuming `theme` directly; Style-Manifest integration
  comes later).
- **Foundational-before-dependent.** Animation (E2) needs charts (E1) for animated reveals;
  overlays (E3) want the Style Manifest (E4) so they're traceable, not new silent globals.
- **One sprint is "next."** Sketch the following ones; commit to one.
- **Slice for independent shippability.** Each sprint lands value on its own; no sprint is
  dead weight until a later one arrives.

## Reliability posture

- Prefer **loud failures over silent fallbacks** once the E5 validator exists. Today's
  silent `text_card` fallback for a missing/HTML `article_image` "looks intentional" and
  hid real bugs (baby-walker). New types should fail loudly with a `suggested_fix`.
- Surface silent globals; don't add new ones. `frame_style`, niche `visual_style`, the
  unused `anchor_image`, seed, and rich_slide bg defaults are all currently invisible — the
  arsenal must not deepen that hole (that's why E4 gates E3).

## Scope hygiene

- Don't over-build. A scaffold/precedent beats a framework. Defer explicitly; never
  silently expand a sprint mid-flight.
- Don't fork a parallel backlog from `docs/future-tasks.md`; absorb rendering items into
  the epics and cross-link.
