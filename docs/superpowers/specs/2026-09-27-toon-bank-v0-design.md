# Toon engine + resource bank v0 — design

**Status:** approved by Tim (2026-09-27) · roadmap: epic **E9**, **Sprint 9** (`docs/ROADMAP.md`)
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
  Drawings are held on twos (12 fps); the camera moves on ones (24 fps). By default the boil
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
| `style.yaml` | line A settings, line-boil mode (default `soft`, shimmer 0.3), palette, ghost ink, paper grain, drawings on twos / camera on ones |

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
| `show` | one graphic: `{speed_lines: who}`, `{bubble: [icons], from: who}`, `{anger: who}`, `{x_card: icon, at: [x, y]}`, `{check_pill: icon, at: [x, y]}` | Pops in (0.25 s default). `from:` is for bubbles only, and `at:` is for cards only. |
| `hide` | the graphic's key, `<kind>:<target>` (for example `bubble:lioness`) | Must match a graphic shown earlier in the shot. |
| `prop` | `to: {b: …}` (idea_bulb brightness), `to: {count: …}` (plate_stack), `flicker`, `blink`, `out` | In v0, brightness `to: {b: …}` over time **is** the fade; there is no separate `fade` state. A plate has no animatable state. |
| `door` | `open` / `close` | |
| `camera` | a bank camera preset | A **cut** to that preset at the beat, not a blend. The new preset's own push, truck or punch restarts from the beat. `over` and `ease` are rejected. |

Prop uses are checked per kind as well. An `idea_bulb` needs `on:`, a `plate` needs
`held_by:`, and a `plate_stack` needs `count:`.

**Rules, enforced when the scene loads:**
- **Wordless:** graphics, bubbles and screens take icon names from the registry. There is no
  free-text field. Unknown fields are rejected, and so are fields that a verb or a prop kind
  would ignore.
- **Every name resolves** to a bank item, set spot, camera or icon. Otherwise it fails with the
  file and path.
- **Limited-motion defaults:** drawings on twos, camera on ones, pop-ins of 0.25 s with
  overshoot. A beat can override them.
- **Timing:** `at` is seconds within the shot. Inside a pipeline storyboard, a beat may say
  `at: {sentence: n}`. v0 resolves that by splitting the scene's narration into sentences and
  sharing the scene's audio duration out by character count. That is an approximation; exact
  syncing comes later.
- **Duration:** in the pipeline, the scene lasts as long as its narration. If the narration
  is longer, the last shot holds, still boiling. If it is shorter than the last beat, loading
  warns and the scene is cut at the narration's end.

## 6. Rendering

- `frame(scene, bank, t)` is a pure function. Boil seeds come from item keys and the drawing
  index (`floor(t·12)`), never from global random state. The same inputs give identical bytes
  on the same machine.
- `render_clip` renders frames in parallel worker processes: 4 cores on the hub, 11 on the
  Mac. At the tryout's rate of about 0.3 s per frame, 13 s at 24 fps takes about 20 s on the
  Mac. Frames stream to ffmpeg (libx264, yuv420p, 1920×1080, 24 fps). The clip is cached by
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
