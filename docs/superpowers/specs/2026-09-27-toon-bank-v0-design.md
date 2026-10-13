# Toon engine + resource bank v0 — design

**Status:** approved by Tim (2026-09-27) · roadmap: epic **E9**, **Sprint 9** (`docs/ROADMAP.md`) ·
**Addendum §11** (2026-10-13): Sprint 11, finishing own-show step 3 (E9 item 2), Tim-greenlit
**Guideline:** [`docs/own-show.md`](../../own-show.md) (top guideline for Tim's own videos) ·
scene library: [`docs/own-show-scenes.md`](../../own-show-scenes.md)
**Designed with Tim:** approach (part 1), bank (part 2) and scene file (part 3) approved in
conversation on 2026-09-26/27. Part 4 (testing and scope) is first presented here.

## 1. Goal and non-goals

**Goal.** Turn the throwaway 2.5D tryout rig (`output/projects/20260724-hybrid-ai-agent-controller/style-tryouts/r4/`)
into a real, tested engine. Add a **resource bank** of things Tim has picked, plus a
**scene file** format that references bank items by name and always renders the same frames.
Then Tim's own videos can use animated scenes as an ordinary pipeline visual type.

**Non-goals (v0):**
- **Not** composing EP1 scenes or its story. The EP1 outline and plot come from Tim later
  (order of work, step 4). The only scene used here is library scene **001** (the lioness
  tryout), and only as the worked example and acceptance test.
- No new bank items beyond what Tim has already picked. The campfire was not picked, so it
  stays a library idea.
- No syncing to individual words. Timing is by seconds, or approximately by sentence (§5).
- No Remotion, no AI video (the Seedance test is a separate step), no Shorts or vertical
  framing, no lip-sync.

## 2. Decisions this builds on (from own-show.md)

- **Look:** frozen character Tim (likeness 2, short crop A, navy hoodie), line A (marker),
  2.5D. Joints, props and camera are 3D, but every line is drawn flat and the linework boils.
  Drawings are held at 12/s (about 2.5 frames each); the camera moves on ones at 30 fps, matching
  compose's concat rate so the clip doesn't judder when concatenated (24 fps juddered; Tim
  picked 30/12 over 30/15 on 2026-09-28). By default the boil
  is *soft*: the drawing holds and the lines shimmer faintly. `full` (the tryout's look) and
  `still` can be chosen per scene. Tim made this pick on 2026-09-28, at the scene-001
  checkpoint.
- **Grammar:** the Hana Explores structure in Tim's doodle look. Sets are ghosted; focus
  characters and props are in colour; graphics pop in; comic emphasis; limited motion.
- **Wordless:** no words are drawn in the animation. Screens show icons, bubbles hold
  pictograms, and cards hold icons. Words live only in narration and subtitles, per locale.
- **Randomness belongs at design time:** options → Tim picks → frozen in the bank.
  Rendering is deterministic.
- **Assembly:** through the pipeline. A storyboard scene of visual type `toon` renders from
  the bank; Tim's A-roll stays an ordinary `clip`.

## 3. Architecture (part 1)

```
storyboard scene  visual.type = "toon"  ─┐
                                         ▼
src/pipeline/composer/toon.py   adapter: render_scene(type "toon") → toon.render_clip(...)
        │
src/toon/scene.py    ToonScene (Pydantic): cast, shots[{at, set, camera, place, props, beats}]
        │  load + validate against the bank; resolve beat times
        ▼
src/toon/render.py   frame(scene, bank, t) → RGBA  (pure) · render_clip → mp4 (ffmpeg, parallel)
        │ uses
        ├─ src/toon/engine/   pen (line A, ghost pen), camera + projection, rig + IK,
        │                     head/face/hair (sphere-projected), 2.5D draw order, paper composite
        ├─ src/toon/kit/      drawing kinds: props (laptop, phone, mug, plate, idea_bulb …),
        │                     graphics (pictogram bubble, ✗ card, ✓ pill, anger mark, speed lines,
        │                     focus glow, sweat, shock lines, smoke wisp), icon registry, sets
        └─ src/toon/bank.py   loads assets/toon/bank/**.yaml → typed Bank
src/toon/cli.py      `pipeline toon validate|render|sheet` (registered on the pipeline CLI)
```

- **One job per unit.** `engine` knows nothing about the bank. `kit` knows nothing about scenes.
  `scene` knows nothing about cairo. `render` is the only unit that ties them together.
- **Cairo binding: `cairocffi`**, which needs no build headers. The hub has the
  `libcairo.so.2` runtime; the Mac has Homebrew cairo. It was checked to be byte-identical to
  pycairo on one frame of the tryout (2026-09-27). On macOS a small loader shim points
  cairocffi at `/opt/homebrew/lib`. `pipeline doctor` gains a toon check (cairo loads, a
  one-frame smoke render works).
- **The engine is ported from the r4 rig, not rewritten.** Code is cleaned up, typed, and
  global state is removed: the rig's global `FACE/HAIR/BODY/HIP` become per-character
  arguments. The tryout code stays in `output/` as history.

## 4. The bank (part 2)

Two kinds of item:

| Kind | What | Where |
|---|---|---|
| **Data** — anything Tim picked | YAML, one file per item, with a `picked:` provenance note (date, which option, which sheet or scene) | `assets/toon/bank/` (in git) |
| **Drawing kinds** — how a *type* of thing is drawn | Python; colours and sizes come from data | `src/toon/kit/` |

**v0 contents** (only items already frozen or picked):

| Path | Items |
|---|---|
| `characters/` | `tim` (face, hair, body, line; model sheet), `lioness` (option A: mane, ears, muzzle, apron) |
| `expressions.yaml` | neutral, talking, happy, focused, worried, shocked, angry, deflated (shared) |
| `poses.yaml` | sit_typing, sit_shock, stand_rest, stand_point, stand_wash (relative to the hip, facing +z, so any character can use them) |
| `sets/` | `office` (ghosted wall with door, window, shelf; desk, chair, rug, lamp; spots `desk_seat`, `doorway`, `doorway_out`) · `kitchen` (counter, sink, faucet, window, cabinets; spot `sink`) |
| `props/` | laptop (icon screen), phone, mug, plate, plate_stack, idea_bulb (brightness, flicker, out + smoke) |
| `cameras.yaml` | front34_push, two_shot, side_truck, close_push, ots_mid, screen_insert |
| `icons/` | registry for wordless graphics: plates, suds, `!`, bulb, check, cross, laptop, phone (drawn by kit code) |
| `style.yaml` | line A settings, line-boil mode (default `soft`, shimmer 0.3), palette, ghost ink, paper grain, drawings at 12/s (`drawing_fps`) / camera on ones at 30 fps (`fps`) |

**Getting into the bank:** only via Tim's picks (options → pick → freeze), with provenance.
New *kinds* (for example a map or timeline graphic) need code plus a pick. The bank renders
its own review sheets: character model sheets (turnaround + expressions), pose and prop
contact sheets.

## 5. The scene file (part 3)

Scene files live at `assets/toon/scenes/<nnn-slug>.yaml` (in git, the source of truth).
Renders go to `output/own-show/scenes/<nnn-slug>/`. The library entry in
`docs/own-show-scenes.md` links both.

A scene is a list of **shots** (cuts). Each shot declares its set, camera, placements and
props, then **beats**: timed changes within the shot. Everything is named from the bank.
The example is the first two shots of `assets/toon/scenes/001-lioness-dishes.yaml`, and it
validates as written (a unit test loads it).

```yaml
id: 001-lioness-dishes
cast: {tim: tim, lioness: lioness}
shots:
  - at: 0.0                  # the first shot starts at 0
    set: office
    camera: front34_push     # a bank preset: its push (and any punch-in) is part of the preset
    place: {tim: {spot: desk_seat, pose: sit_typing, expr: focused}}
    props: {idea: {kind: idea_bulb, on: tim, b: 1.0}}
  - at: 3.5
    set: office
    camera: two_shot
    place:
      tim:     {spot: desk_seat, pose: sit_typing, expr: focused}
      lioness: {spot: doorway_out, pose: stand_point, expr: angry, layer: low}
    props:   {idea: {kind: idea_bulb, on: tim, b: 1.0}}
    beats:
      - {at: 0.05, door: open, over: 0.25}
      - {at: 0.1,  move: lioness, to: doorway, over: 0.6, ease: out, bob: 0.06}
      - {at: 0.12, show: {speed_lines: lioness}, over: 0.2}
      - {at: 0.25, pose: tim, to: sit_shock, expr: shocked, over: 0.2, ease: back}
      - {at: 0.35, prop: idea, flicker: true}
      - {at: 0.8,  show: {bubble: [dishes, bang], from: lioness}}
      - {at: 0.8,  show: {anger: lioness}}
```

**Beat verbs (v0).** Every beat has `at` and exactly one verb. `over` and `ease` time a change;
by default it is instant.

| Verb | Takes | Notes |
|---|---|---|
| `pose` | `to:` a pose and/or `expr:` an expression | An expression change alone is a pose beat with only `expr:`. `to:` cannot switch sit ↔ stand; cut to a new shot instead. |
| `move` | `to:` a set spot, optional `bob` | |
| `face` | `to:` another placed character | |
| `show` | one graphic: `{speed_lines: who}`, `{bubble: [icons], from: who}`, `{anger: who}`, `{x_card: icon, at: [x, y]}`, `{check_pill: icon, at: [x, y]}` | Pops in (0.25 s default; `over:` sets it). `from:` is for bubbles only; `at:` and an optional slug `id:` (never drawn) are for cards only. A show whose key is still visible fails (§11.2 b1). `over: 0` appears at once, and a negative `over` fails on any verb (§11.6). |
| `hide` | the graphic's key, `<kind>:<target>` (for example `bubble:lioness`; a card's target is its `id:` when it has one) | Must take down a graphic that is showing in the shot. |
| `prop` | `to: {b: …}` (idea_bulb brightness), `to: {count: …}` (plate_stack), `flicker`, `blink`, `out` | In v0, brightness `to: {b: …}` over time **is** the fade; there is no separate `fade` state. A plate has no animatable state. |
| `door` | `open` / `close` | |
| `camera` | a bank camera preset | A **cut** to that preset at the beat, not a blend. The new preset's own push, truck or punch restarts from the beat. `over` and `ease` are rejected. |

Prop uses are checked per kind as well. An `idea_bulb` needs `on:`, a `plate` needs
`held_by:`, and a `plate_stack` needs `count:`.

**Rules, enforced when the scene loads:**
- **Wordless:** graphics, bubbles and screens take icon names from the registry. There is no
  free-text field. Unknown fields are rejected, and so is every field that a verb or a prop
  kind would ignore (Sprint 11, §11.2 a): for example `ease` on `show`, `over`/`ease` on
  `hide`, `ease` without `over`, and `flicker`/`blink`/`out` on plates.
- **Every name resolves** to a bank item, set spot, camera or icon. Otherwise it fails with the
  file and path.
- **Limited-motion defaults:** drawings at 12/s (about 2.5 frames each at 30 fps), camera on ones, pop-ins of 0.25 s with
  overshoot. A beat can override them.
- **Timing:** `at` is seconds within the shot. Inside a pipeline storyboard, a beat may say
  `at: {sentence: n}`. v0 resolves that by splitting the scene's narration into sentences and
  sharing the scene's audio duration out by character count. That is an approximation; exact
  syncing comes later. Since Sprint 11 a shot's `at` takes the same anchor, and both take
  `plus: s` (§11.2 f).
- **Duration:** in the pipeline, the scene lasts as long as its narration. If the narration
  is longer, the last shot holds, still boiling. If it is shorter than the last beat, loading
  warns and the scene is cut at the narration's end.

## 6. Rendering

- `frame(scene, bank, t)` is a pure function. Boil seeds come from item keys and the drawing
  index (`floor(t·12)`), never from global random state. The same inputs give identical bytes
  on the same machine.
- `render_clip` renders frames in parallel worker processes: 4 cores on the hub, 11 on the
  Mac. 13 s at 30 fps (390 frames) takes about 12 s wall time on the Mac, cache miss, all
  cores. Frames stream to ffmpeg (libx264, yuv420p, 1920×1080, 30 fps — matches compose's
  concat rate, `COMPOSE_FPS` in `pipeline/stages/compose.py`, so clips don't judder when
  concatenated). The clip is cached by
  a hash of the scene, the bank files, the `src/toon` source files and the engine version, so
  any engine or kit edit re-renders.
- Only 16:9 in v0. The storyboard validator rejects a `toon` scene on a 9:16 storyboard.

## 7. Pipeline integration

- `render_scene()` gains `elif visual_type == "toon"`, which calls
  `composer/toon.py:render_toon_scene(scene, duration_sec, aspect_ratio, work_dir)`. The
  visual either references a scene (`{"type": "toon", "scene": "001-lioness-dishes"}`, which
  may override `boil`; any other key is rejected) or inlines the scene's keys (`cast`,
  `shots`, …; typos are rejected).
- The storyboard validator accepts `toon` and runs the scene loader's validation, so bad
  names fail at the review gate, not during composing.
- Subtitles, music, transitions and publishing are unchanged. Narration comes from TTS or
  Tim's prerecorded voice (existing workflow).
- Toon scenes produce ordinary clips, so frame-based review works as for any clip. Note:
  `visual-review extract-frames` is not registered on either machine (a known bug, tracked in
  the EM's arsenal-state), so pull evidence frames with `extract_review_frames` or ffmpeg.
- `toon` stays out of `overlay_rules._TEXT_VISUALS`, so narration subtitles are kept.

## 8. Testing and done criteria (part 4)

| Test | What it proves |
|---|---|
| Bank loader unit tests | every v0 YAML loads; provenance is present; a missing or unknown field fails with a clear path |
| Scene validation unit tests | unknown bank name → error; any free-text field → error (wordless); beats outside the shot → error; `sentence` anchors resolve |
| Engine unit tests | projection and IK maths; draw-order cases from the tryout (desk between camera and character or not; arms raised behind the head) |
| Determinism test | the same frame rendered twice (and in a worker process) → identical bytes |
| Golden frames | a few frames of scene 001 plus the Tim model sheet, compared **on the hub only** (hub-canonical, as in the E8 font policy); skipped elsewhere with a reason |
| **Acceptance: scene 001** | `assets/toon/scenes/001-lioness-dishes.yaml` renders a clip that matches the tryout's `animatic_v2_bulb.mp4` in shots, timing and look (key-frame side-by-side). **Tim confirms** it still meets his bar |
| Pipeline smoke | a two-scene storyboard (a `clip` plus a `toon` scene) composes end to end on the hub |
| `pipeline doctor` | the toon check passes on both machines |

**v0 is done when** all of the above pass and the engineering-manager's REVIEW gate passes
(this is visual-arsenal work: per `CLAUDE.md` it joins `docs/ROADMAP.md` through an EM
INTAKE once this spec is approved, and the EM owns its test-plan rows).

## 9. Delivery

- Work in a dedicated git worktree. Small commits per unit (engine → bank → scene → render →
  integration → CLI/doctor).
- Order: port the engine with its tests → bank loader and v0 YAML → scene model and
  validation → renderer → scene 001 file and acceptance → pipeline adapter → doctor and CLI.
- **Risks:** the draw order is heuristic (the tryout needed cases per shot; v0 keeps a small
  set of rules plus an explicit per-shot layer override). Render time on the hub's 4 cores is
  about 45 s per 13 s scene, which is acceptable. Golden frames can drift between cairo
  versions, which is why they are hub-only.

## 10. After v0 (not in this spec)

Word-level timing (Whisper word timestamps) · more characters and sets from Tim's picks ·
explainer graphics kinds (map, timeline, arrows between cards) · host A-roll ↔ toon transitions ·
Shorts / vertical framing · the Seedance accent-shot test · the audience-lens critics
(own-show next step 5).

## 11. Addendum: Sprint 11, finishing step 3 (E9 item 2), 2026-10-13

**Status:** Tim greenlit it on 2026-10-13 ("for step three, could you complete?"). The EM
proposed it in SPRINT mode. Roadmap: E9 item 2, **Sprint 11**. This section amends §4–§8 where
it says so. Everything else above still holds.

**Context.** Step 1 (style) is open again. Tim rejected the v0 doodle look on 2026-09-28, and on
2026-10-13 he also rejected the editorial cut-paper candidate (branch
`art/toon-editorial-tryout`, deleted, never merged). A tryout of a "totally different style" on
scene 001 runs in parallel. **The v0 bank stays the implemented baseline until Tim picks.**

So Sprint 11 builds only the **scene contract** half of step 3: what a scene file may say, how
it is timed against narration, and how it fails. That half holds for any look the engine draws
from bank names. The items that depend on the look are held (§11.4).

### 11.1 Scope

| Item | Sprint 11 | Why |
|---|---|---|
| 2a: silently ignored fields fail at load | **IN** | scene contract; loud failure |
| 2b: two cards with one icon collide on one key | **IN** | scene contract |
| 2b: sentence splitter (「」 quotes, "U.S.") | **IN** | timing; zh-TW narration drives anchors |
| 2b: `SceneError` names the scene file | **IN** | closes the v0 deferral Tim acked |
| 2b: `style.yaml` `line`/`palette` wired into renders | **HELD** | look-dependent (§11.4) |
| 2c: laptop ✓/✗ screen states | **HELD** | needs Tim's pick in the new look |
| 2d: `toon validate --narration/--duration` | **IN** | authoring tool for anchors |
| 2d: pose and prop contact sheets | **HELD** | review sheets for the next picks; look-dependent |
| 2e: hygiene (`PROP_KINDS` sync, camera `over`/`ease` check, workers reload the bank) | **IN** | correctness |
| 2f: shot starts follow the narration | **IN**, sentence-level | §11.2 f; word-level stays E9 item 3 |
| 2g: "on twos" wording | **done** in this edit (§4, §5) | — |

### 11.2 Design

**a. No silently ignored field.**
- `Beat.over` and `Beat.ease` become optional, where `None` means "not given". The timeline
  applies the defaults: `over` 0, `ease` smooth, and a 0.25 s pop for `show`.
- Rule: every field set on a beat must be read by the timeline for that verb (and, for `prop`,
  that prop kind). Otherwise the scene fails to load, with the path.
- Starting table. The builder confirms it against `timeline.py` and pins it in one table-driven
  test:

  | Verb | `over` | `ease` |
  |---|---|---|
  | `door`, `move`, `pose`, `face` | yes | yes |
  | `prop` | only with `to:` | only with `to:` |
  | `show` | yes (the pop length) | no |
  | `hide`, `camera` | no | no |

- `PROP_KINDS` gains a fourth entry: the beat flags each kind honours. Only `idea_bulb` takes
  `flicker`, `blink` and `out`. So a `plate` or `plate_stack` beat with one of them fails.
- Bank: when a character's `hair` has `layers:`, any top-level hair key that the layered drawing
  path doesn't read fails with a `BankError` naming the file and the key.

**b1. Graphic keys.**
- Cards (`x_card`, `check_pill`) take an optional `id:`, a slug (`^[a-z][a-z0-9_]*$`). It is
  never drawn, so the wordless rule still holds. The key becomes `<kind>:<id or icon>`.
- A `show` whose key is still visible in the shot fails, naming both beats. Showing it again
  after a `hide` is fine.

**b2. Sentence splitter** (`split_sentences`, pure). The v0 rules stay: a run of terminators is
one break, decimals don't break, and an ellipsis followed directly by text doesn't break. Added:
- **Closing quotes attach to the left.** A terminator still ends a sentence inside quotes,
  because TTS pauses there and anchors are about timing, not grammar. Any closing quotes or
  brackets right after it (」 』 ” ） ) ’) belong to the sentence they close, so no sentence
  starts with a closer. For example:
  - 他說：「我走了。」然後離開。 gives 他說：「我走了。」 and 然後離開。 (today the second is
    」然後離開。).
  - 「走吧！」「好。」 gives 2 sentences.
  - A narration quoted as a whole, 「A。B。」, still gives 2, so anchors can address the
    sentences inside a quoted line.
- **Abbreviations.** A "." doesn't end a sentence when it follows a one-letter word (U.S., J. K.,
  e.g., a.m.) or a word in a short list kept next to the splitter: Mr, Mrs, Ms, Dr, Prof, St,
  vs, etc, Sr, Sra, Srta. The list covers en and es-419. At the end of the text it still ends
  the sentence.
- The known cost: "…moved to the U.S. Then…" merges into one sentence. `toon validate
  --narration` prints the split (d), so the author sees how anchors count.

**b3. `SceneError` names its source.**
- `SceneError(problems, source=None)` reads `<source>: <problem>` for each problem.
- `read_scene` attaches the scene file. `load_scene(..., source=...)` takes it from the caller:
  - a scene file gives its repo-relative path;
  - an inline storyboard visual gives `<storyboard file> scene <sid>`;
  - a `scene:` reference gives `<scene file> (from <storyboard file> scene <sid>)`.
- `pipeline validate` and compose's `SceneRenderError` reason both carry it.

**d. `pipeline toon validate <scene> [--narration TEXT] [--duration SEC]`.**
- `--duration` defaults to the scene's own `duration`.
- It resolves the anchors and prints a sentence table (n, start in seconds, the sentence), each
  shot's resolved start, and warnings as `WARN` lines.
- Exit 0 when clean (warnings allowed), 1 on errors.
- A scene with anchors and no `--narration` exits 1 with a message that names the flag.

**e. Hygiene.**
- A test holds `PROP_KINDS` keys equal to the `PropDef.kind` literals.
- The camera `over`/`ease` check uses `is not None`; it no longer reads `model_fields_set`. This
  falls out of (a).
- Render workers get the caller's `Bank` (serialised) instead of reloading it from disk. The
  frames then come from the bank that was validated. (The clip's cache key still hashes the bank
  *files* on disk, not this object: an edit landing between load and render keys the new files.
  That gap is a Later item in the roadmap.)

**f. Shot starts follow the narration, without word-level timing.**
- **The defect:** shot starts are absolute seconds. When the narration length changes (a TTS
  draft, then Tim's recorded voice, then a re-take), every cut stays put, and only the last shot
  holds or is cut.
- **The fix:** `Shot.at` accepts the same anchor as a beat, `{sentence: n}`. The anchor gains
  `plus: s` (seconds after the sentence start, ≥ 0, default 0), on shots and beats alike.
- Resolution order:
  1. Shot anchors become absolute times: start of sentence n + `plus`.
  2. Beat anchors resolve relative to their shot's resolved start.
  3. The first shot must resolve to 0. After resolution, shot starts must strictly increase.
     Otherwise loading fails, naming each shot, its anchor and its resolved time.
- Beats given in seconds stay shot-relative. **Nothing is stretched uniformly:** a stretch would
  silently re-time comic timing the author wrote.
- **Drift warning.** A warning, not an error, because a scene timed in seconds is legitimate. It
  fires when all of these hold:
  - the scene has an authored `duration`;
  - some later shot starts at an absolute time;
  - the narration differs from the authored duration by more than 0.5 s.

  Text: "shots 2–4 are in seconds and won't follow the narration (authored 13.0 s, narration
  16.2 s); anchor them with `at: {sentence: n}`".
- **The seam:** every anchor resolves through `sentence_starts(narration, duration)`. Word-level
  timing (E9 item 3) later swaps in measured starts there, and no scene file changes.
- **Why word-level timing isn't pulled in:**
  - It needs a new provider or dependency (the Whisper API, or a local model) and a per-scene
    timing artifact.
  - It needs zh-TW character alignment.
  - No named beat needs sync inside a sentence yet.

  Sentence anchors fix the defect itself. The approximation (character share of the scene's
  measured duration) can put a cut a few hundred ms off against a real voice. `plus:` and the
  validate table make that visible and adjustable.
- **Cache:** the resolved scene and the duration are both in the clip's cache key, so a new
  narration re-renders.

### 11.3 Done criteria

- The `test-plan.md` rows **S11-1 … S11-16** (E9 section) all pass, at a single REVIEW.
- Each behaviour change lands red first: a test-only commit, then the fix (Sprint 10 precedent).
  The EM mutation-checks the fences.
- **Scene 001 is unchanged:**
  - hub goldens 4/4 with `UPDATE_GOLDENS` unset and no fixture churn;
  - parity worst ≤ 0.058;
  - the determinism tests pass.

  Scene 001 uses none of the newly rejected fields (EM probe, 2026-10-13). Its clip cache key
  changes once, because `over`/`ease` serialise differently; that is expected.
- **The non-goal fence holds:**
  - `assets/toon/scenes/` holds only `001-lioness-dishes.yaml`;
  - the bank gains no item;
  - anchored test scenes live under `tests/fixtures/toon/`.
- **Real-scene demo, hub:** a throwaway smoke project rebuilt from the Sprint 9 recipe
  (`tmp/toon-v0/compose-smoke/REPORT.md`: s2's three-sentence zh-TW narration). The original
  project `9920260928` is gone from the hub (EM check, 2026-10-13), and the report is only on
  the Mac (untracked). The s2 narration, three sentences, without the report's wrapping
  quotes: `提姆靈光一閃，想到一個好點子。獅子太太氣沖沖衝進來，要他馬上去洗碗。提姆只好站到水槽前，看著靈感一點點熄滅。`
  (edge-tts 13.44 s).
  - The visual is an inline, sentence-anchored copy of scene 001: shots 2 and 3 on sentences 2
    and 3, and shot 4 on `{sentence: 3, plus: …}`.
  - It runs against two real narration takes of different length: the existing 13.44 s edge-tts
    take, and a second voice or rate.
  - Check that each cut lands within one frame of its resolved start, and that the clip lasts
    exactly as long as the narration.
  - Evidence goes in `tmp/toon-s11/demo/`. This is not an EP1 scene.
- Full suite, ruff and mypy clean. A separate code review has happened.

### 11.4 Held until Tim picks the new style

| Item | Comes back when |
|---|---|
| 2c laptop ✓/✗ screen states | after the pick: options → Tim picks → freeze, drawn in the picked look |
| 2b `style.yaml` `line`/`palette` wiring | first item of the restyle sprint, if the pick stays on this engine. Until then, the equality test keeps an edit loud |
| 2d pose and prop contact sheets | with the restyle. Built now, they would show a rejected look and churn goldens |
| §2 "Look" and the §4 bank table | rewritten when the pick lands |

**Risk.** Some of this would be stranded if the new style leaves scene files behind, for example
a pure AI-video look. The scene contract is built to outlive the drawing code, not that pivot.

### 11.5 Tim's decisions (2026-10-13)

The SPRINT proposal left three questions for Tim before the build. His answers, passed on by the
coordinator when the build started:

1. **Hold the style-dependent items:** laptop ✓/✗ screen art, the `style.yaml` line/palette
   wiring, and the pose/prop contact sheets wait for the style pick (§11.4). Sprint 11 does not
   build them.
2. **Shot timing = sentence anchors** (`at: {sentence: n, plus: s}`), a loud failure when shots
   resolve out of order, and the drift warning (§11.2 f). Word-level timing stays E9 item 3.
3. **zh-TW quote rule:** a 。 inside 「」 ends a sentence, and the closing 」 stays with it.
   `他說：「我走了。」然後離開。` gives `他說：「我走了。」` + `然後離開。` (§11.2 b2).

### 11.6 Build rulings (Sprint 11 plan)

Where the build went past this section's letter, the plan
(`docs/superpowers/plans/2026-10-13-e9-sprint11-scene-contract.md`, "Rulings") records why:

- `ease` without `over` fails too: with no `over` the change is instant and every ease maps
  1 → 1, so the field would be silently ignored.
- A second `hide` of an already hidden key fails (a no-op beat).
- `none:` beside `layers:` fails like the per-layer keys: only `layers` and `bun` are read there.
- The one-letter-word abbreviation rule skips the pronoun "I" ("Neither did I. We left." is two
  sentences).
- Closers also include ASCII `"` and `'` and 】》〉], so `She said "Stop." Then…` keeps its quote
  on the first sentence.
- The drift warning is its own function, `drift_warnings`; compose logs it as
  `toon.scene.drift`, apart from the `toon.scene.cut` warning.
- Shot order (the first shot at 0, then strictly increasing) is checked once, as the anchors
  resolve, so a misordered scene fails with the order problems alone, not also with bogus
  "outside the shot" windows.
- **`over` values mean what they render** (EM REVIEW 1, R4; row S11-17). A negative `over` fails
  at load on any verb; it used to load and act as instant. `over: 0` on a `show` is an instant
  appear with no pop; it used to load and still pop over 0.25 s. A `show` with no `over` keeps
  the 0.25 s pop. A `blink` needs a positive `over`: one of 0 s or less never showed.

**Code review R1 (fresh reviewer, 2026-10-13): rulings.**

- **Splitter, es-419 (I1).** A word before a "." is Latin letters with accents (`À`–`ɏ`), never
  CJK: `día.` and `camión.` end sentences, and `他在U.S.工作。` still reads "U" as one letter.
  The abbreviation list gains `ee`, `uu` (EE. UU.), `dra`, `ud`, `uds`. `»` and `›` close, like
  `」`.
- **A retake can push a beat out of its shot (I2).** A beat in seconds inside a shot whose window
  depends on sentence anchors may fit one narration and not another. It stays a load error,
  because a mid-video beat is never dropped silently. The error names the shot's anchor and its
  window at this narration, e.g. `shot 2 {sentence: 2} → 2.50–5.67 s at this narration (9.0 s);
  anchor the beat (at: {sentence: n, plus: s}) or move it`. `toon validate` prints every shot's
  `start – end` window, so the margin shows before recording.
- **An ellipsis, a closing quote, then more text ends the sentence (M8).** `他說：「我不知道……」他沉默了。`
  gives two, the closer staying left, as Tim's 。」 rule does. Without a closer, `我……不知道。` is
  still one sentence.
- **A straight `"` closes only an unmatched opening `"` (M9).** In `他走了。"你好。"` it opens the
  next sentence. A straight `'` still always closes, because apostrophes make counting unreliable.
- **No-op beat fields fail (M5, M6).** `out` takes only `true`; `out: false` did nothing. A prop
  `to: {}` animates nothing and fails. `bob` needs `over`, as `ease` does: without it the move is
  instant and leaves a fixed lift. Falsy values that do load mean what they render: `over: 0` is
  instant (a `show` appears at once), `bob: 0` is no lift, and `flicker: false` stops an earlier
  flicker. The residual lift `bob` leaves at the end of a timed move (scene 001's lioness ends
  0.025 above `doorway`) is not changed here: fixing it would churn the goldens.
- **Bank hair (M7).** `layers: []` fails (the drawing would fall back to the top-level hair). The
  `none:` message says what happens: `none: true` wins and every layer is dropped.
- **Errors (M3, M10, M11).** `toon validate` prints each problem whole, even when its text holds
  "; ". `--narration` on a scene with no duration names `--duration` (M4). The still-gate passes
  the storyboard file, so its toon errors name it as compose's do. A hide listed before a show
  of its key at the same time says so.
