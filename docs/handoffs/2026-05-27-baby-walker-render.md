# Handoff: baby-walker explainer — render phase (after storyboard-critic PASS)

**Date:** 2026-05-27
**Branch:** feat/niche-visual-style-split
**Last commit:** f01d579 fix(storyboard-review): reconcile transitions[] on cut/merge
**Status:** active

## Related parts

- `docs/handoffs/2026-05-26-storyboard-critic-gate.md` — **predecessor (history).** Built the
  storyboard-critic editor gate + ran loop 1. This render-phase handoff supersedes it.

## Goal

Produce the baby-walker explainer video (`output/projects/20260504-115232-baby-walker-story`,
locale zh-TW). The explainer was producer-GREENLIT (~8 min, both story + visual axes closed);
the storyboard-critic gate then ran to **PASS** (loops 1–3), the gate skill was hardened, and the
storyboard was re-rendered. Remaining work is QA on the rendered output and committing the
render-prep edits — then it's publishable.

## Progress so far

- **Storyboard-critic gate PASSED** on the baby-walker storyboard. Loops committed:
  - `5f5ec67` gate infra (skill + critic agent + produce Phase 3.5 + handoff doc)
  - `7b917fa` loop 1 (46%→30% text-heavy) + critic memory + `.gitignore` whitelist
  - `3ee9b8f` loops 2–3 (30%→26%, PASS). Loop verdicts in
    `.agent-memory/storyboard-critic/reviews/20260504-115232-baby-walker-story.md`.
- **video-producer path fix** (know-fountains): commit `0eccff2`.
- **Gate skill hardened** (`f01d579`): `reconcile_transitions()` added to storyboard-review's
  auto-apply so `cut`/`merge` no longer leave dangling `transitions[]` refs. Verified against
  single-cut / merge-removal / consecutive-chain / no-op scenarios (function extracted from the
  committed SKILL.md and re-run).
- **Render-prep edits (UNCOMMITTED — see WIP):**
  - s25 + s26 → reuse s24's fitted map (`edits/s24_outpaint_postcrop_00dbf5.png`); identical source
    + target box, so sharing the refit is correct (not the "don't carry refit_path" gotcha).
  - s37 + s44 → `animate.enabled=false`. They are `chart_type=comparison`, which has **no animated
    variant** (only line/bar/stat_big_number animate). Loop 1 wrongly enabled animation; compose
    validation rejected it. Now `validate_storyboard` is clean (0 errors; 1 non-blocking s40 warn).
- **Re-rendered** the 9 stale loop-changed scenes via `compose rescene` (s6, s13, s25, s26, s29,
  s35, s37, s44, s45); rest cached. Output: `compose/final_zh-TW_no_overlay.mp4` (02:07, 122 MB,
  **9:49 / 589.8s**). Only the `no_overlay` variant was produced this pass.

## Next step

**A QUALITY-ENHANCEMENT pass is required before publish** (user feedback 2026-05-27, after watching
the no_overlay render). Four defects + the fix-prompt are below. The reviewer *principle* has already
been enhanced this session (commit `1a29a18`: storyboard-critic now does a variant-aware review +
reuse/substrate/locale/transition checks); the actual scene FIXES are to be done in a NEW session
using the prompt in "## Quality-enhancement fix-prompt" below. Publish only after that pass.

(Prior milestone, still true: visual-review done; deliverable variant DECIDED = `no_overlay`, clean
images + audio. The render-prep storyboard edits are committed.)

## Quality-enhancement fix-prompt (paste into a NEW session)

> Project `20260504-115232-baby-walker-story` (content-creation, branch `feat/niche-visual-style-split`).
> The video was rendered as `preferred_variant: no_overlay` (clean images + audio — NO burned
> overlays/subtitles; this is the user's accepted deliverable, keep it). It's a PORTED video
> (`source_locale: en` → `locale: zh-TW`). Fix these four quality defects, then re-gate and re-render.
> The storyboard-critic standards were just upgraded (`.agent-memory/storyboard-critic/standards.md`,
> commit `1a29a18`) to catch exactly these — read them first.
>
> **1. Image reuse reads as repetition (no_overlay strips the differentiators).**
>    - `north_america_blank_map.png` on s24/s25/s26 (×3), `Baby_Walker.jpg` on s36/s38/s45/s47 (×4),
>      `Baby_by_Vignesh.jpg` on s29/s33/s35 (×3), `Learning_to_walk.png` on s3/s6 (×2). With overlays
>      off and no camera_motion, these are the identical frame repeated.
>    - Fix: give each reuse a differentiator that SURVIVES into the no_overlay frame (distinct
>      camera_motion/crop), OR a distinct real/generated image, OR merge redundant beats. Run a full
>      `visual.path` reuse count and resolve every 3+.
>
> **2. The map is a blank substrate — meaningless without the (stripped) overlay.**
>    - s24/s25/s26 use a blank grey map; its whole meaning (Canada BANNED 2004 vs US STILL SOLD) was
>      in the `text_emphasis` overlay that no_overlay drops. Fix: bake the meaning INTO the image —
>      generate annotated map(s) (Canada highlighted/banned vs US still-sold, color-coded + minimal
>      labels) so the bare frame communicates. Differentiate the three (or merge).
>
> **3. Locale-locked text slides → depicting generated_images.**
>    - s4 and s7 (and any other `slide`/`text_card` burning zh-TW text) are porting liabilities and
>      missed visuals. Convert depictable concepts to `generated_image` via the `generate-image`
>      skill (draft tier first per global CLAUDE.md): e.g. s7 "女性回到職場" → woman working in an
>      office, "塑膠射出成型" → injection-molding machinery, "郊區開放格局" → suburban open-plan home.
>      Keep text only for genuinely non-depictable beats.
>
> **4. Page-turn transitions are uniform (gimmicky).**
>    - `book-page-turn-v2` is on ALL of s1→s30. Intended design = history scenes only. Sections:
>      hook s1-3, context s4-9 (= history); rising s10-21, climax s22-29 (= analytical). Fix: keep
>      page-turn within history (s1→s9) + the s9→s10 "close the history book" boundary; set s10→s30
>      seams to `style:none`. Edit the `transitions[]` array directly.
>
> **Then:** re-run the `storyboard-review` gate (now variant-aware — it should verify these are
> fixed), then re-render with `compose rescene --project-id 20260504-115232-baby-walker-story
> --scene <changed ids>` (run `fit-image` first for any new generated images). Re-run `visual-review`.
>
> **Gotchas:** `produce` can't re-render an existing project (use `compose rescene`); `comparison`
> charts need `animate.enabled=false`; don't rely on overlays (no_overlay); a `tail`-piped background
> command masks its exit code — read the task output file.

### Visual-review outcome (all clear under the no_overlay decision)
- **Image fitting RESOLVED:** compose fills+crops article_images, so the photos (s6/s29/s35/s36/
  s38/s45/s47) render edge-to-edge with subjects intact — NO outpaint needed. The earlier
  "letterbox" worry was a misread of frame.py. s13 chart + s24/s25/s26 map images all render
  correctly.
- **Overlays intentionally absent:** with `no_overlay` chosen, the gate's namecards/text_emphasis
  (s24 BANNED/STILL SOLD, s25 Shin, s26 lobbying, s6/s29/s35/s45 verbatim) do NOT appear — accepted.
  The critic's loop-1/2 work remains valuable structurally (it drove text_card→article_image), even
  though the overlays aren't burned. Knock-on accepted: s36/s45/s47 show the same push-toy image.
- Runtime 9:49 (~2 min over the 6–8 band) — accepted as top-of-band per project history.

## Open questions / pending decisions

All resolved 2026-05-27:
- Photo fitting — RESOLVED: compose fills+crops; no outpaint needed.
- Variant — RESOLVED: user chose `no_overlay` (clean, no burned text); render stands.
- Runtime 9:49 (~2 min over band) — accepted as top-of-band.
- Only optional decision left: publish now or later (user's call).

## Files touched + WIP state

- `output/projects/20260504-115232-baby-walker-story/storyboard.json` — **uncommitted.** s25/s26
  refit_path reuse + s37/s44 `animate.enabled=false`. Validated clean. Ready to commit.
- `compose/final_zh-TW_no_overlay.mp4` — freshly rendered output (gitignored).
- `.agent-memory/active-handoff-*` + `.agent-memory/storyboard-critic/...` — local (gitignored
  except the storyboard-critic whitelist already committed).

## Gotchas / learnings

- **`pipeline produce` is the wrong tool to re-render an existing project** — `--url` is REQUIRED and
  `--project-id` is an INTEGER. For an existing slug-named project use `pipeline compose rescene
  --project-id <slug> --scene sN ...` (re-renders only named scenes + rebuilds transitions/final) or
  `compose reburn`. The handoff's old `produce --start-from tts` command was wrong.
- **`comparison` charts have no animated variant.** `animate.enabled` must be false for
  chart_type ∈ {comparison, proportion_blocks, timeline}; only line/bar/stat_big_number animate.
- **Unfitted images letterbox, they don't break.** `frame.py` scales-to-fit into the book inset and
  pads with `#18120b`. fit-image's `refit_path` is the override to fill the box (crop/outpaint).
- **`text_emphasis` overlay is single-line** (one ffmpeg drawtext); never put `\n` in its text.
- **Piping a backgrounded CLI through `tail` masks its exit code** — exit 0 from the pipe ≠ success.
  Read the task output file; the first "render" silently failed an arg-validation error this way.

## How to resume

```bash
cd /home/tim-huang/content-creation
git rev-parse --abbrev-ref HEAD          # feat/niche-visual-style-split
git log --oneline -5                     # confirm f01d579 at/near HEAD
git status --short | grep storyboard.json  # the uncommitted render-prep edit

# 1) QA the render (in-session skill):
#    invoke the visual-review skill on project 20260504-115232-baby-walker-story
ls -lh output/projects/20260504-115232-baby-walker-story/compose/final_zh-TW_no_overlay.mp4

# 2) If a photo needs filling: fit-image skill --apply on that scene, then:
#    uv run pipeline compose rescene --project-id 20260504-115232-baby-walker-story --scene sN

# 3) Commit the render-prep edits:
git add output/projects/20260504-115232-baby-walker-story/storyboard.json
git commit -m "fix(baby-walker): render-prep — map refit reuse (s25/s26) + disable animate on comparison charts (s37/s44)"
```
