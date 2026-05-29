# Engineering-manager — standing standards

My accrued engineering bar, applied to EVERY sprint I scope. The `engineering-manager`
skill injects this into my prompt and promotes generalizable lessons here (lean,
Tim-confirmed). Skill-managed.

## The two axes (guard this hardest)

- **Quality now spans visual AND audio; the runtime invariant is unchanged.** The axes are
  fundamentally **quality vs runtime**. Visual was the only quality sub-axis only because it
  was the only thing on the menu; E7 (2026-05-26) adds the **audio** sub-axis (SFX/ambient
  layering, mix legibility). SFX/ambient over a 4-min scene adds zero seconds, exactly as
  richer rendering does not — do NOT let an audio sprint claim runtime either.
- Richer rendering — charts, animation, overlays — **or richer audio** — fixes **production
  quality / slideshow risk**. It does **NOT** add **runtime**. A 4–5 min story rendered
  beautifully (or scored beautifully) is still 4–5 min. Runtime is bought with MORE distinct
  beats (more story / more sources).
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
6. **Real-scene demonstration.** Pick a canonical scene from a *recent real project* (not
   a synthetic fixture) and render the new capability against it end-to-end, sampling
   rendered mp4 frames to confirm it reads right in production — goldens prove determinism,
   the demo proves it works on real content. This is existing practice (Sprint 1 baby-walker
   stat scenes; Sprint 2/5 s21 decline-curve verified end-to-end), now codified. (Idea A,
   2026-05-26: Tim wants new arsenal skills demonstrably verified against a real scene, not
   only against fixtures.)
7. Eventually: a Style Manifest element (E4) and a dashboard surface (E6).
   Sprints 1–N may defer 7, but must name it as deferred, not forget it.
8. **Locale-portable by default** (cross-cutting authoring bar, Tim 2026-05-29). A scene's
   visual content should stay language-neutral so ONE render serves future multi-language
   audio tracks without re-rendering visuals (we already ship MLA — `--mla
   --secondary-locale`; this is the visual-side complement). Bias order: (1) numerics /
   charts / data graphics, (2) image-only, (3) iconography / emoji. When baked-in on-screen
   text is genuinely unavoidable, default it to **English (en-US first)**, never the locale
   narration language. **Scope split vs the existing niche `universal_rules` "no text in
   images" (shipped, parenting/true-crime):** that rule governs **AI-generated image
   backgrounds** (Flux renders baked-in text garbled, so suppress it entirely); this bar's
   "en-US first" governs **deliberate** on-screen text we author — chart labels, overlays,
   callouts — where the text is intentional and legible. Not contradictory: no-text for AI
   backgrounds, en-US-first for deliberate text. This is **orthogonal to both axes** — it is portability/i18n, NOT a
   slideshow-quality lift and NOT runtime; do not mis-file it as a quality sprint. The
   director-prompt-bias half of this rides along with the next `stages/direct.py`-touching
   sprint (don't spin it into its own epic); the lint-enforcement half is an E5 🔵 item
   (locale-portability lint, below current priorities). *(Note: animated emoji/iconography
   is NOT a current visual type — flag as possible future E2/E3 demand if a beat names it,
   per arsenal-is-a-variable; do not build pre-emptively.)*

**Lessons from Sprint 2 (animation):**
- **Frame generators are PURE.** Contract: `(progress, visual, base_bg, w, h, palette,
  top) → PIL.Image` — no disk, no network, no random. The orchestrator owns all I/O.
  This is what makes sampled-frame goldens viable; without purity you fall back to mp4
  binary comparison, which is flaky across ffmpeg builds. Enforced by a determinism
  test that calls each generator twice and asserts byte-identical PIL output BEFORE any
  golden-comparison test runs.
- **Two-axes guardrails belong in code.** A reveal-duration policy stated only in docs
  erodes; one enforced by the validator (`reveal_duration_sec ≤ scene_duration − 0.5s`
  raises with a fix hint) survives pressure. New animation-adjacent sprints must check
  whether their own quality-vs-runtime tradeoff has a code-level fence.
- **ffmpeg invocation is duplicated, not abstracted, until a 3rd caller appears.**
  `_camera_motion_to_video` and `render_animated_chart` both call `run_ffmpeg` with the
  same JPEG-sequence arg list; a shared helper waits for the 3rd caller (premature
  abstraction is the bigger risk here).
- **Hold-tail caching is mandatory for animated chart reveals.** The orchestrator
  renders the p=1.0 final frame ONCE and reuses it for every frame after the reveal.
  Saves ~30% wall-time on a typical 6s scene with 4s reveal; verified by a test that
  asserts the generator is called ≤ `reveal_frames` times, not `total_frames`.

**Lessons from Sprint 1 (chart):**
- **Renderers do NOT self-wrap the project frame.** `open_book_page` is applied at
  compose level (`compose.py` → `composer/frame.py`) post-render, so a new visual type
  inherits it automatically. Don't re-implement frame logic in the renderer (the chart
  handoff's "wrap with book_scene" wording was wrong).
- **Golden-PNG test mechanics:** fixtures live in `tests/unit/` (+ `tests/fixtures/.../golden/`),
  rendered with a deterministic flat background (`ai_background: false`) so NO provider
  call fires in CI; mock `image_to_video`; add a determinism smoke test (render twice,
  `ImageChops.difference(...).getbbox() is None`) BEFORE committing fixtures; gate
  regeneration behind `UPDATE_GOLDENS=1`. Always eyeball each golden — a deterministic
  test passes a baked-in layout bug silently.
- **A new type owns a warm/editorial palette** rather than consuming the cool slate
  `Theme` color defaults (`secondary_bg` = slate-700); consume `theme.image_style` for the
  AI-bg prompt (art-direction continuity) and defer full Theme-color integration to E4.

## Anatomy of a new audio capability (E7)

*Accreted from the first E7 sprint — the music/audio-axis feature (master `12bfce3`, EM REVIEW
2026-05-29).* An audio capability mirrors the visual-type anatomy but the analogues differ:

1. **Schema additive + back-compat.** A new audio control is an optional `Scene`/`Theme` field
   with a no-op default (music: `Scene.music_mood = ""` inherit, `Theme.music_default_mood =
   "none"`). It must never change output for storyboards that don't set it.
2. **Pure DSP core, orchestrator owns I/O — same as frame generators.** Cue planning and any
   timeline math (`plan_cues`, mood resolution) are pure functions over data
   (storyboard + `scenes.json`); ffmpeg filter-graph builders (`build_bed`/`duck_bed`/`mux`)
   are thin, deterministic command emitters. `compose/scenes.json` is the timing source of
   truth (accurate per-scene start/duration) — align audio cues to it, never re-derive timing.
3. **The two-axes fence is the LENGTH CLAMP.** Audio is the quality (audio) sub-axis with ZERO
   runtime. The in-code fence: build the bed to the *exact* existing video duration
   (`apad whole_dur=total, atrim 0:total`), stream-copy the video (`-c:v copy`), and mix with
   `duration=first` keyed to narration — so audio physically cannot extend the video. Prove it
   with a length-assertion test (bed length == total ±tol), the audio analogue of the
   `reveal_duration_sec ≤ scene − 0.5s` validator. This belongs in code, not docs.
4. **Mix legibility is MEASURABLE, not eyeballed.** A duck/mix is verified by `volumedetect`
   dB deltas on synthetic tones (bed sits N dB below speech; recovers in pauses), and
   re-application is idempotent (source the narration bus from the pristine `raw.mp4`, never
   the already-mixed final → no doubling). These are the audio analogue of golden PNGs.
5. **Loud failure on a missing asset.** A used-but-unstocked mood/SFX must `Exit` loudly with
   a `suggested_fix`; library entries with a blank `file` are skipped on load so they error at
   use, not silently render nothing.
6. **Real-scene demo is STILL gating (step 6 of the visual anatomy applies).** Goldens/dB-tests
   prove determinism + the mix math on synthetic audio; they do NOT prove it sounds right on
   real content. A new audio capability is not 🟢 until it is demonstrated against a canonical
   real-scene arc with real (license-clear) assets and the artifact saved — for music, the
   s19→s23 baby-walker intelligibility check. **Lesson learned the hard way:** the music
   feature's engineering passed every test but the library was empty, so the demo could not run
   → EM returned ADVISE, not PASS, and E7 stayed 🔵. Synthetic-only ≠ proven.
7. **Asset library = a license-tracking manifest from day one.** `library.json` carries
   per-asset `source`/`source_url`/`license`/loudness — this is the same shape E7 item 1 (SFX
   asset registry) wants, so a music/SFX library should converge on one registry pattern, not
   fork two.

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

## Production-project greenlight gate (governance — 2026-05-26, Tim)

A second class of work now lives in my queue: **production video projects** (candidate
videos), tracked in `.agent-memory/engineering-manager/production-projects.md`. They are a
distinct entity from capability work and obey a standing three-part rule. **I track and
surface the gate; I do NOT clear it (Tim, as video-producer, does) and I do NOT produce the
video.**

1. **Greenlight gate.** A parked production project must carry an explicit **video-producer
   greenlight** flag before it can become a sprint nominee. Until greenlit it stays
   **blocked**. The greenlight is a content/quality decision (Tim wearing the video-producer
   hat), separate from my engineering role.
2. **Backlog-review notification — every dispatch, every mode (INTAKE/SPRINT/REVIEW).** I
   scan `production-projects.md` and emit a fixed `## Production-project gate status` block in
   my reply: one `Blocked — awaiting greenlight: <title>` line per un-greenlit project, or an
   explicit all-clear line if none are blocked (and an "(none tracked)" line if the file is
   empty). **The block always prints** so its absence never reads as "the EM forgot." This is
   not optional and is independent of mode. (Use a `notify-result` call too if that channel is
   available; the in-reply block is the floor.)
3. **Nomination rule.** Once a project receives video-producer greenlight it becomes a
   nominee for the **next sprint slot** *unless* a very-high-impact capability sprint is
   currently ongoing.

**Capability sprint ≠ production-project sprint slot — keep them distinct.** A *capability
sprint* I scope and propose end-to-end (my normal SPRINT output, gated by my REVIEW). A
*production-project slot* I only **nominate** — the actual video production happens elsewhere
(content work), not in a capability build session. Never silently start scoping a production
video as if it were a capability sprint.

**Pinned definitions (so future-me doesn't relitigate):**
- *"Very-high-impact capability sprint ongoing"* — a capability sprint that has multiple
  converging demand pointers AND/OR is fixing actively-degraded output today (the exact bar
  Sprint 6 / E4 Slice 3 clears). If such a sprint is ongoing, it pre-empts a greenlit
  production project for the slot; otherwise the greenlit production project takes it.
- *"Currently ongoing"* — greenlit-and-in-flight. A sprint that is merely proposed-but-not-
  yet-greenlit does NOT count as ongoing for pre-emption purposes.

## Definition of done (the REVIEW gate)

- **A greenlit arsenal sprint is not "done" until I pass it in REVIEW mode.** This is the
  adversarial acceptance gate — the role exists *because* the builder and the reviewer must
  be different eyes. The build session summons me before `finishing-a-development-branch`
  / merge.
- **I verify, I do not perform.** REVIEW = "does this satisfy the sprint's acceptance
  criteria + the `test-plan.md` rows it touched?" I **run** the targeted tests via Bash
  (`uv run pytest <paths> -q`, `ruff`, `mypy`) and read exit codes / golden diffs myself —
  a gate that only inspects assertions has no teeth. Code-quality/correctness review is a
  *separate* job (throwaway reviewer); I **require it has happened**, I don't redo it.
- **Verdict is one of three:** `REWORK` (specific must-fix gaps; status does NOT advance),
  `ADVISE` (acceptance met, with recommendations), `PASS` (acceptance met). I check the
  two-axes claim held (no runtime smuggled in via an arsenal item) before any PASS.
- **Real-scene demo is part of the gate** for any new visual/audio *capability* (not for a
  pure-refactor/infra sprint): before PASS I require evidence the build was demonstrated
  against a canonical scene on a recent real project (rendered-frame check), not only against
  golden fixtures. Goldens prove determinism; the demo proves it works on real content.
  (Idea A, 2026-05-26.)
- **Only PASS advances state:** move ROADMAP 🔵→🟢, refresh `arsenal-state.md`, flip the
  `test-plan.md` rows to ✅. Always append the verdict to `sprint-log.md`.

## Test-plan upkeep

- `test-plan.md` is the regression contract. In SPRINT mode I append the new capability's
  acceptance rows as `🔲 planned` (naming the test path the build must create). In REVIEW
  mode I run them and flip ✅/❌. Never PASS a sprint with a `🔲`/`❌` row it introduced.

## Memory hygiene (keep dispatch cheap)

- The managing skill no longer pre-reads my memory into the dispatch prompt — I spawn with
  my persona and **read my own memory + `docs/ROADMAP.md` first thing**, inside my isolated
  context. So I must keep these files lean.
- **Sprint-log compaction:** `sprint-log.md` holds only the last ~2 sprints; older closed
  sprints roll to `sprint-log-archive.md` (which I read only when explicitly asked for deep
  history — `arsenal-state.md` already carries the shipped inventory). When the active log
  grows past ~3 sprints, archive the oldest.
