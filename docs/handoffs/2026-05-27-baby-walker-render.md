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

**The video is DONE for this pass — only publish remains (optional).** Visual-review (2026-05-27) is
complete and the user DECIDED the deliverable variant: **`no_overlay` (clean images + audio, no
burned text) — accepted as-is.** No re-render. The render-prep storyboard edits were committed
(see WIP). The single remaining action is to publish if/when the user wants:
```bash
# invoke the publish skill on 20260504-115232-baby-walker-story (final_zh-TW_no_overlay.mp4)
```

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
