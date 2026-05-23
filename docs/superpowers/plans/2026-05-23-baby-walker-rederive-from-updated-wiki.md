# Baby-Walker Re-Derive from Updated Wiki — Implementation Plan

> **SESSION CHECKPOINT (2026-05-23, mid-execution):** Tasks 0, 1, 2 executed. Task 3 (storyboard re-derive) pending at the designed gate. **Read `tmp/baby-walker-rederive-handoff.md` first** — it carries the full Task-3 design (47-scene block-by-block, chart specs with confirmed `data` field names, advisor fix for the chart-clustering risk, verbatim-line placement, hand-fix preservation map, and the Task 4–7 Python entry points verified against the modules). Continue from Task 3 there.

> **For agentic workers:** This is a content/video re-production plan, not a code feature. "Tasks" are pipeline stages and storyboard-authoring steps. Steps use checkbox (`- [ ]`) syntax for tracking. The explainer `analyze` + `storyboard` stages are **authored by Claude directly** following the `produce` skill (Phase 2 / Phase 3) — they are not automated LLM calls.

**Goal:** Bring `output/projects/20260504-115232-baby-walker-story` up to the GREENLIT loop-7 wiki cut — add the four new source-backed story acts, route stat scenes through the now-shipped chart renderer, wire in the newly-acquired assets — while preserving the corrections already hand-committed to the storyboard.

**Architecture:** Re-acquire the updated wiki into the project, re-derive `knowledge.json` + `storyboard.json` from it (authored by Claude, charts auto-selected for stat beats), diff against the current board to confirm the hand-fixes survived (re-apply any that regressed), then re-run script → TTS → compose via direct Python drivers. The current render is preserved as an A/B baseline before anything overwrites it.

**Tech stack:** Python pipeline (`src/pipeline/`), Fish Audio TTS (`tim-zhtw-fish`), `chart.py` + `chart_anim.py` (shipped to master), Pillow compositing, ffmpeg concat. Source of truth: `know-fountains/wiki/parenting/explainers/baby-walker-story.md` (updated 2026-05-23).

---

## Background — why this work exists

The project currently renders a **40-scene, ~6.2 min** cut, built from a **2026-05-12** snapshot of the wiki (`source/explainer.md`). The wiki was rewritten **2026-05-23** and is now **GREENLIT at ~8 min (loop-7)**, a decision the producer review explicitly says supersedes the older cut. Three gaps:

1. **Four new story acts are absent** from the storyboard (each backed by a real ingested source):
   - **Act A — mechanism** (speed + burns/drowning/poisoning). Only the speed/stairs fragment exists today.
   - **Act B — the undercount** ("230,676 is the floor": NEISS low sensitivity + 40+ product names). Absent.
   - **Act C — the ban that wasn't** (Canada banned, US didn't, and *why*: CPSC legal bar + lobbying; Shin quote). Only a one-line Canada mention (s20) exists.
   - **Act D — developmental delay** (BMJ 2002, n=190). Absent.
2. **Data-motion mandate not applied.** Board is **17 slides + 10 text_cards, 1 chart**. The chart renderer (all 6 types + animated reveals) is now on master. The wiki authored chart specs for Acts B and D that have nowhere to render yet.
3. **Acquired assets unused.** All verified on disk: `kettle_boiling_gas_stove.jpg`, `bathtub_bathroom.jpg`, `drain_cleaner_naoh.jpg`, `north_america_blank_map.png`, `Baby_in_a_walker_in_San_Salvador_1972.jpg` (1972 boom photo — never wired in), the two motion clips, and `*_alignsm` fit variants.

---

## Settings to preserve (read from CURRENT context.json — the SESSION_HANDOFF is stale on MLA)

```
voice_id:          tim-zhtw-fish        # Fish Audio primary
source_locale:     en
locale:            zh-TW
niche:             parenting
burn_subtitles:    False
skip_overlays:     True
preferred_variant: no_overlay           # NOT subtitles_no_overlay, NOT mla
mla:               False                 # project was simplified off MLA since the handoff
theme.frame_style: open_book_page        # storyboard-level; keep
```

Do **not** re-introduce MLA / EN secondary track — the project moved off it deliberately (latest render is `compose/final_zh-TW_no_overlay.mp4`).

---

## Hand-fix re-apply checklist (verify each survives the re-derive; re-apply if regressed)

| # | Fix | What it corrected | How to verify in new board |
|---|-----|-------------------|----------------------------|
| 1 | s1 posture 坐→站 | Cleves baby is **standing** in the frame, not sitting | Opening narration says 站 (stand), not 坐 |
| 2 | s3 claim | dropped false "同一個座椅" + AI-tell "六百年沒換過" | No "同一個座椅"; hook phrasing neutral |
| 3 | s11/s25 → `generated_image` | stat/villain scenes use generated_image not slide | mechanism + villain scenes are generated_image |
| 4 | s33 activity center | wheeled image replaced with **no-wheels** activity center | activity-center scene has no wheeled-walker image |
| 5 | **s21 decline-curve** (crown jewel) | animated line, 1990→2014, **6 milestone markers** | chart scene present with all 6 markers (1982/1995/1997/2001/2004/2010) |
| 6 | theme.frame_style | `open_book_page` book frame on every scene | `theme.frame_style == "open_book_page"` |
| 7 | context preferred_variant | `no_overlay` | `context.json.preferred_variant == "no_overlay"` |

Because Claude authors the new storyboard with this checklist in hand, items 1–4 are corrected at authoring time rather than re-applied after. Items 5–7 are structural and must be carried forward verbatim.

---

## Target structure (new `required_sequence`, act by act)

New runtime target: **top-of-band ~480s / ~46–48 scenes** (loop-7 accepted top-of-band). Ordering constraints from the wiki: mechanism + undercount come **before** the merged decline-curve (anchor 230,676 first); after the curve it is **ban-politics → developmental-cost → "so why a $1.1B market?"**.

| Block | Scenes (approx) | Source section | Visual treatment |
|-------|-----------------|----------------|------------------|
| 1. History 1440→boom | ~8 | intro + "A long gap before it took off" | article_images; **add 1972 San Salvador photo + `baby_walker_boom_era.mp4`** (period texture only — never assert "this is a walker" over the clip). 1905 photo doubles as the 1901 Sloan stand-in **with an on-screen date-disambiguation label**, held through the 1960s–70s transition. page-turn transitions. |
| 2. Injury stats | ~4 | "The numbers that changed things" | **Route to charts**: 1990 ~20,650 → `stat_big_number`; 74% stairs / 91% head-neck → `bar` or `proportion_blocks`; 38% skull fx of admitted → `stat_big_number`; 230,676/25yr → `stat_big_number`. |
| 3. **Act A — mechanism** (INSERT) | ~3 | "What actually happens in the seat" | speed beat over `baby_walker_danger_rolling.mp4`; hazard montage of 3 stills — burns `kettle_boiling_gas_stove.jpg`, drowning `bathtub_bathroom.jpg`, poisoning `drain_cleaner_naoh.jpg` (brief beat, 600×450 — do not dwell); deaths 34 (1973–98) + 8 (2004–08) as stat. Narrate hazard endpoints, **not** "the walker is shown." |
| 4. **Act B — undercount** (INSERT) | ~1–2 | "And 230,676 is the floor" | `chart_type="bar"`, animated grow, **iceberg reveal**: "Recorded (NEISS)" 230,676 vs taller "Estimated true ?" cap. Title "230,676 is the floor". Subtitle "NEISS sensitivity gaps + 40+ product names". Source "Weiss, Pediatrics, 1996". `style_mood: "medical chart"`. |
| 5. Merged decline-curve | 1 (**keep s21**) | "The controversy timeline" + "Did it work?" (both tables MERGE here) | **Keep existing s21 line chart** (1990→2014, 6 markers). The current separate regulation slides (old s16–s18: 1982 study / 1995–97 standards / 1999 −57%) **collapse into the curve's markers** — they are deleted as standalone scenes. Narration delivers the 90% verdict as the line draws. |
| 6. **Act C — ban politics** (INSERT/EXPAND) | ~2–3 | "The ban that wasn't" | **Use `north_america_blank_map.png` + overlay** "BANNED 2004" (Canada) / "STILL SOLD" (US) — chosen over a comparison chart **to break the chart run** (greenlight term 1). Shin quote ("virtually impossible for the CPSC to ban a consumer product…") as animated text overlay on the map, NOT a bare text_card. Add the lobbying half + "still legal/sold 2024, AAP+CR renew call." |
| 7. **Act D — developmental delay** (INSERT) | ~2 | "Medicine's other objection" | `chart_type="comparison"` — Walker users vs Non-users, 3 rows (crawl +4wk, stand +3wk, walk +3wk). Title "Walkers delay the milestones they replace". Source "Garrett BMJ 2002, n=190". Then `chart_type="line"` — x=hours of use 0–24h, y=delay days 0–3+, annotation at x=24 "~3 extra days' delay per 24h". Title "The delay scales with use". Tone: "doesn't do what the box implies," not parent-shaming. |
| 8. Market + 3 products + rule | ~14 (**keep s22–s40**) | "$1.1B market" → "three products" → "the rule" | Keep. Villain = `Baby_by_Vignesh.jpg` (wheeled sit-in); push-toy = `Baby_Walker.jpg` (or `_alignsm`); stationary activity center = generated_image/text_card (no dedicated still — acceptable per greenlight term 3). Straight cuts (no page-turn) for this block. |

### Chart-spec → scene wiring (for Phase 3 authoring)

| Scene role | chart_type | key data | title / source |
|------------|-----------|----------|----------------|
| 1990 peak | stat_big_number | ~20,650 | "US ER visits, 1990" |
| injury pattern | bar / proportion_blocks | 74% stairs, 91% head/neck | "Where walker injuries land" |
| severity | stat_big_number | 38% skull fx (of admitted) | "Of those admitted" |
| cumulative toll | stat_big_number | 230,676 / 25 yr | "1990–2014" |
| Act B undercount | bar (iceberg) | Recorded 230,676 vs Estimated "?" | "230,676 is the floor" / Weiss 1996 |
| **decline-curve (keep s21)** | line + 6 markers | 1990→2014 (20,650→2,001) | "US ER visits per year" / AAP 1990–2014 |
| Act D milestones | comparison | crawl +4wk, stand +3wk, walk +3wk | "Walkers delay the milestones they replace" / Garrett BMJ 2002 n=190 |
| Act D dose-response | line | x=0–24h use, y=0–3+ days delay | "The delay scales with use" / Garrett BMJ 2002 |

**Chart-clustering guard (greenlight term 1):** beats 4–7 risk 4–5 chart-type scenes in a row (stats → bar → decline-line → ban-comparison → delay-comparison+line). Using the **map+overlay** for Act C (not a comparison chart) breaks the run and satisfies the downstream no-3-consecutive-same-type rule. Verify the final board has no 3 consecutive `chart` scenes.

---

## Task 0 — Pre-flight (safety + traceability)

**Files:** `output/projects/20260504-115232-baby-walker-story/`

- [ ] **Step 1: Back up the current render as the A/B baseline**

```bash
cd /home/tim-huang/content-creation
P=output/projects/20260504-115232-baby-walker-story
cp "$P/compose/final_zh-TW_no_overlay.mp4" "$P/compose/final_zh-TW_no_overlay.PRE-REDERIVE.mp4"
ls -lh "$P/compose/final_zh-TW_no_overlay.PRE-REDERIVE.mp4"
```
Expected: a ~78 MB copy exists, untouched by later steps.

- [ ] **Step 2: Checkpoint the current storyboard/knowledge/context before overwriting**

```bash
cd /home/tim-huang/content-creation
git add -A output/projects/20260504-115232-baby-walker-story/storyboard.json \
             output/projects/20260504-115232-baby-walker-story/knowledge.json \
             output/projects/20260504-115232-baby-walker-story/context.json
git commit -m "chore(baby-walker): checkpoint pre-rederive storyboard/knowledge/context

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```
Expected: clean commit; `git log -1` shows the checkpoint. (Confirmed: these three files are git-tracked, so the commit is the right checkpoint mechanism. On `master`, commit confirmation is required per repo hygiene rules — get Tim's go-ahead for this one commit.)

- [ ] **Step 3: Snapshot the hand-fix evidence for the diff in Task 3**

```bash
cd /home/tim-huang/content-creation
python3 -c "
import json
sb=json.load(open('output/projects/20260504-115232-baby-walker-story/storyboard.json'))
for s in sb['scenes']:
    print(s['id'], s['visual'].get('type'), '|', s['narration'][:50])
" > /home/tim-huang/content-creation/tmp/baby-walker-board-OLD.txt
wc -l /home/tim-huang/content-creation/tmp/baby-walker-board-OLD.txt
```
Expected: 40-line snapshot saved for later diffing.

---

## Task 1 — Re-acquire (copy updated wiki into the project)

**Files:** Modify `output/projects/20260504-115232-baby-walker-story/source/explainer.md`

- [ ] **Step 1: Confirm the wiki is the GREENLIT loop-7 version**

```bash
grep -n "loop-7\|GREENLIT\|updated:" /home/tim-huang/know-fountains/wiki/parenting/explainers/baby-walker-story.md | head
```
Expected: `updated: 2026-05-23`, `decision: GREENLIT`, "LOOP 7".

- [ ] **Step 2: Copy the updated wiki over the stale project source**

```bash
cp /home/tim-huang/know-fountains/wiki/parenting/explainers/baby-walker-story.md \
   /home/tim-huang/content-creation/output/projects/20260504-115232-baby-walker-story/source/explainer.md
grep -c "What actually happens in the seat\|230,676 is the floor\|The ban that wasn't\|Medicine's other objection" \
   /home/tim-huang/content-creation/output/projects/20260504-115232-baby-walker-story/source/explainer.md
```
Expected: `4` — all four new act headers now present in project source.

- [ ] **Step 3: Verify required assets resolve through the `raw` symlink**

```bash
cd /home/tim-huang/content-creation
for f in kettle_boiling_gas_stove.jpg bathtub_bathroom.jpg drain_cleaner_naoh.jpg \
         north_america_blank_map.png Baby_in_a_walker_in_San_Salvador_1972.jpg \
         baby_walker_boom_era.mp4 baby_walker_danger_rolling.mp4; do
  test -f "raw/parenting/baby-walker/assets/$f" && echo "OK $f" || echo "MISS $f"
done
```
Expected: all `OK` (the `raw` → `../know-fountains/raw` symlink resolves manifest-relative paths).

---

## Task 2 — Re-derive `knowledge.json` (produce skill, Phase 2: Analyze)

**Files:** Modify `output/projects/20260504-115232-baby-walker-story/knowledge.json`

This is authored by Claude per the `produce` skill Phase 2. Re-read the updated `source/explainer.md` and rebuild the knowledge base.

- [ ] **Step 1: Invoke the `produce` skill and follow its Phase 2 (Analyze) instructions** to regenerate facts / entities / timeline / context_bridges from the new wiki body, including the four new acts' facts (mechanism speed + burns/drowning/poisoning + deaths; NEISS undercount + 40+ names; CPSC legal bar + lobbying + Shin quote; BMJ 2002 milestones + dose-response).

- [ ] **Step 2: Set production_notes for the top-of-band cut**

In `knowledge.json` → `production_notes`:
```json
{
  "target_duration_sec": "420–480 (≈8 min, top of band)",
  "target_scenes": "46–48",
  "scene_duration_sec": "6–10",
  "visual_style": "<keep current>",
  "transitions": "page-turn between history scenes (hook → regulation block); straight cuts for final block (three product variants → the rule)"
}
```

- [ ] **Step 3: Verify the four acts' facts landed**

```bash
cd /home/tim-huang/content-creation
python3 -c "
import json
k=json.load(open('output/projects/20260504-115232-baby-walker-story/knowledge.json'))
blob=json.dumps(k,ensure_ascii=False)
for needle in ['NEISS','Garrett','Shin','virtually impossible','drowning','poisoning','190']:
    print(('OK ' if needle in blob else 'MISS '), needle)
"
```
Expected: all `OK`.

---

## Task 3 — Re-derive `storyboard.json` (produce skill, Phase 3: Storyboard)

**Files:** Modify `output/projects/20260504-115232-baby-walker-story/storyboard.json`

Author the new ~46–48 scene board per the **Target structure** table above, with the **Chart-spec wiring** table and the **Hand-fix checklist** in hand. Follow the `produce` skill Phase 3.

- [ ] **Step 1: Author the board** in the new `required_sequence` order (Blocks 1–8). Carry forward verbatim: `theme.frame_style: "open_book_page"`; the existing **s21 line chart with all 6 markers** (renumber as needed but keep its `data` block intact); page-turn transitions through the regulation block, straight cuts after.

- [ ] **Step 2: Apply hand-fixes 1–4 at authoring time** — standing posture in the opener; no "同一個座椅"/"六百年沒換過"; mechanism + villain scenes as `generated_image`; activity-center scene with no wheeled image.

- [ ] **Step 3: Wire the new assets** — 1972 San Salvador photo + `baby_walker_boom_era.mp4` (boom block), `baby_walker_danger_rolling.mp4` + 3 hazard stills (Act A), `north_america_blank_map.png` (Act C), `Baby_by_Vignesh.jpg` (villain). Use `*_alignsm` variants where a fit was already prepared.

- [ ] **Step 4: Verify structure, charts, ordering, and runtime**

```bash
cd /home/tim-huang/content-creation
python3 -c "
import json
sb=json.load(open('output/projects/20260504-115232-baby-walker-story/storyboard.json'))
sc=sb['scenes']; tot=sum(s.get('narration_est_sec',0) for s in sc)
types=[s['visual'].get('type') for s in sc]
print(f'scenes={len(sc)}  est={tot:.0f}s ({tot/60:.1f}min)')
import collections; print('types:', dict(collections.Counter(types)))
# no 3 consecutive same visual type
run=1; bad=[]
for i in range(1,len(types)):
    run = run+1 if types[i]==types[i-1] else 1
    if run>=3: bad.append((sc[i]['id'],types[i]))
print('3+ consecutive same-type:', bad or 'none')
print('frame_style:', sb.get('theme',{}).get('frame_style'))
# decline curve markers preserved
charts=[s for s in sc if s['visual'].get('type')=='chart' and s['visual'].get('chart_type')=='line' and s['visual'].get('data',{}).get('markers')]
print('decline-curve markers:', len(charts[0]['visual']['data']['markers']) if charts else 'MISSING')
"
```
Expected: `scenes` 46–48; `est` 420–480s; `frame_style: open_book_page`; `3+ consecutive same-type: none`; decline-curve markers `6`.

- [ ] **Step 5: Diff against the old board and confirm the four acts are present**

```bash
cd /home/tim-huang/content-creation
python3 -c "
import json
sb=json.load(open('output/projects/20260504-115232-baby-walker-story/storyboard.json'))
blob=json.dumps(sb,ensure_ascii=False)
for label,needle in [('A-burns','燙'),('A-drown','溺'),('B-undercount','NEISS'),('C-Shin','禁'),('D-BMJ','發展')]:
    print(('OK ' if needle in blob else 'CHECK '), label, needle)
"
```
Expected: act content present (adjust needles to the actual zh-TW wording authored).

---

## Task 4 — Re-derive the narration script

**Files:** Modify `output/projects/20260504-115232-baby-walker-story/script/script_zh-TW.md`

- [ ] **Step 1: Regenerate the script from the new storyboard** (per memory `feedback_storyboard_script_sync`: after manual storyboard edits, regenerate the script via `derive_script()` before TTS).

```bash
cd /home/tim-huang/content-creation
uv run python -c "
import asyncio, json
from pathlib import Path
from pipeline.storyboard import Storyboard, derive_script  # confirm symbol name in src/pipeline/storyboard.py
P=Path('output/projects/20260504-115232-baby-walker-story')
sb=Storyboard.model_validate_json((P/'storyboard.json').read_text())
script=derive_script(sb)
(P/'script'/'script_zh-TW.md').write_text(script)
print('script chars:', len(script))
"
```
Expected: script regenerated; char count roughly proportional to ~8 min of zh-TW narration. (If `derive_script` has a different signature, read `src/pipeline/storyboard.py` and adapt — do not guess.)

---

## Task 5 — TTS (clear caches first, then synth)

**Files:** Modify `output/projects/20260504-115232-baby-walker-story/audio/*`

- [ ] **Step 1: Clear stale audio + per-scene mp4 caches** (per `feedback_storyboard_script_sync`: clear all scene `.mp4` caches before compose so renumbered/changed scenes don't reuse stale audio/video).

```bash
cd /home/tim-huang/content-creation
P=output/projects/20260504-115232-baby-walker-story
rm -f "$P"/audio/segment_*.mp3 "$P"/audio/narration_zh-TW.mp3 "$P"/audio/subtitles_zh-TW.srt
rm -f "$P"/compose/scene_*.mp4 "$P"/compose/raw_no_overlay.mp4 "$P"/compose/concat_list*.txt
ls "$P"/audio/ "$P"/compose/ 2>/dev/null
```
Expected: segment/narration/subtitle and scene caches gone; the `*.PRE-REDERIVE.mp4` baseline remains.

- [ ] **Step 2: Run the TTS stage via direct Python** (helper CLIs take `project_id: int`; this project ID is a string, so drive the stage directly — same pattern the prior session used for compose).

```bash
cd /home/tim-huang/content-creation
uv run python -c "
import asyncio, json
from pipeline.context import PipelineContext   # confirm import path
from pipeline.stages.tts import TTSStage
P='output/projects/20260504-115232-baby-walker-story'
ctx=PipelineContext.model_validate_json(open(P+'/context.json').read())
asyncio.run(TTSStage().run(ctx))
open(P+'/context.json','w').write(ctx.model_dump_json(indent=2))
print('narration:', ctx.narration_path)
"
```
Expected: `narration_zh-TW.mp3` regenerated (~440–480s, voice `tim-zhtw-fish`); `segment_timings` repopulated for the new scene count. (Confirm `PipelineContext` import path / TTS entry against `src/pipeline/stages/tts.py` before running — adapt, don't guess.)

- [ ] **Step 3: Verify narration duration matches the ~8 min target**

```bash
cd /home/tim-huang/content-creation
ffprobe -v quiet -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 \
  output/projects/20260504-115232-baby-walker-story/audio/narration_zh-TW.mp3
```
Expected: ~420–490 s.

---

## Task 6 — Compose (direct Python driver, per documented workaround)

**Files:** Create `output/projects/20260504-115232-baby-walker-story/compose/final_zh-TW_no_overlay.mp4`

- [ ] **Step 1: Run ComposeStage directly** (not `pipeline compose` — that CLI requires `--project-id: int`).

```bash
cd /home/tim-huang/content-creation
uv run python -c "
import asyncio
from pipeline.context import PipelineContext
from pipeline.stages.compose import ComposeStage
P='output/projects/20260504-115232-baby-walker-story'
ctx=PipelineContext.model_validate_json(open(P+'/context.json').read())
asyncio.run(ComposeStage().run(ctx))
open(P+'/context.json','w').write(ctx.model_dump_json(indent=2))
print('final:', ctx.final_video_path)
"
```
Expected: `compose/final_zh-TW_no_overlay.mp4` (re)written; charts rendered via `chart.py`/`chart_anim.py` for the stat/Act-B/Act-D scenes; page-turn transitions in the history/regulation blocks, straight cuts after.

- [ ] **Step 2: Confirm the new render and compare to baseline**

```bash
cd /home/tim-huang/content-creation
P=output/projects/20260504-115232-baby-walker-story
for f in "$P/compose/final_zh-TW_no_overlay.mp4" "$P/compose/final_zh-TW_no_overlay.PRE-REDERIVE.mp4"; do
  echo "$f"; ffprobe -v quiet -show_entries format=duration,size -of default=noprint_wrappers=1 "$f"
done
```
Expected: new render ~8 min and meaningfully longer than the ~6.2 min baseline; both files present.

---

## Task 7 — Visual review + final verification (evidence before "done")

- [ ] **Step 1: Run the `visual-review` skill** on the rendered scenes — check chart legibility, hazard-still montage reads correctly, map overlay (BANNED/STILL SOLD) is legible, no subtitle/overlay overlap, image↔narration match on the new acts, no style drift, boom clip never captioned "this is a walker."

- [ ] **Step 2: Spot-check the four new acts** by extracting frames at the act timestamps and viewing them (mechanism montage, Act B iceberg bar, Act C map, Act D charts).

- [ ] **Step 3: Confirm publish attributions are queued** (greenlight term 4): CC-BY / CC-BY-SA / CC0 credits per `CREDITS.md` for 1972, 2022, kettle, bathtub, map; both `.mp4` clips flagged AI-generated. (Do not publish in this plan — surface to Tim.)

- [ ] **Step 4: Report results to Tim with the A/B pair** — old baseline vs new cut, runtime delta, which hand-fixes were re-applied vs survived, any director choices worth a second look.

---

## Risks & mitigations

- **Director non-determinism** — the new board may not reproduce every hand-fix. *Mitigation:* Task 0 Step 3 snapshot + Task 3 Step 5 diff + the checklist; fixes 1–4 are applied at authoring time, not left to chance.
- **CLI string-ID breakage** — `produce`/`compose`/TTS helper CLIs take `project_id: int`. *Mitigation:* drive TTS + compose via direct Python (Tasks 5–6), as the prior session did. Confirm import paths against the actual modules before running.
- **Chart-clustering** — 4–5 chart scenes risk tripping the no-3-consecutive rule and feeling like a dashboard run. *Mitigation:* Act C uses map+overlay (not a chart); Task 3 Step 4 asserts no 3 consecutive same-type.
- **Cache reuse on renumbered scenes** — stale `scene_*.mp4`/segment audio could bind to wrong scenes. *Mitigation:* Task 5 Step 1 clears all caches before TTS/compose.
- **Baseline loss** — *Mitigation:* Task 0 Step 1 copies the current render to `*.PRE-REDERIVE.mp4` before anything overwrites it.
- **`drain_cleaner_naoh.jpg` is 600×450** — don't hold on it (greenlight term 2); kettle + bathtub (multi-thousand-px) carry the longer dwells in the montage.

---

## Self-review (run before declaring the plan ready)

- **Spec coverage:** four acts (A/B/C/D) → Blocks 3/4/6/7 + Task 3; data-motion mandate → chart wiring table + Block 2 routing + decline-curve keep; new assets → Task 1 Step 3 + Task 3 Step 3; ordering constraints → Target structure note; greenlight terms 1–5 → chart-clustering guard, term 2 risk note, term 3 (stationary center text_card ok), term 4 attributions (Task 7 Step 3), term 5 (1905 stand-in + date label, Block 1). Covered.
- **Settings preserved:** read from current context (no_overlay, mla False) not the stale handoff. Covered.
- **No placeholders:** commands are concrete; the two genuinely skill-driven stages (analyze, storyboard) explicitly defer to the `produce` skill rather than fabricating LLM output; Python import paths flagged "confirm before running" rather than asserted blindly.
