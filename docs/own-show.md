# Own hosted shows — guideline & status

**Scope:** every original video Tim hosts (first: "[$20 Subscriber] EP1. Hybrid AI Agent
Controller", project `output/projects/20260724-hybrid-ai-agent-controller/`). For these videos
this doc is the **top guideline** and overrides the zh-TW porting defaults in `CLAUDE.md`.
The porting pipeline keeps its existing rules. (Decided with Tim 2026-09-26.)

## Guideline

- **Format:** Tim on camera as the host — sets context, guides the viewer, hands off to
  animation or screen recording for the deep details.
- **Audience:** office workers, developers, and people who want to work better with AI.
  Every critic/evaluator judges from that angle: can a non-developer follow it, would a
  developer find it accurate (not hand-wavy), is the workflow benefit concrete and actionable,
  does the pacing work with a host on screen. The faceless-port lens does not apply (e.g. a
  run of host A-roll is not a "slideshow act").
- **Who decides what:** Tim owns the early creative decisions — the elements that form each
  scene's animation/video (characters, set, props, poses, camera feel, style, narrative
  angle). Propose options; Tim chooses. Downstream evaluate steps stay automatic (critic
  auto-patches, proofread auto-apply).
- **Order of work:**
  1. Style tryouts → freeze a **style guide**.
  2. Build a reusable **resource bank**: Tim's character first, then other characters, sets
     ("my desk"), props, poses, backgrounds, camera feels. Built for many videos, not just EP1.
  3. Scene scripts reference bank elements by name ("me at my desk working on the laptop") and
     must render consistently by construction.
  4. Tim gives the latest high-level script → agree the scene breakdown together → per-scene
     style + narrative → build each scene until done.
- **Randomness belongs at design time.** Generate options, Tim picks, the pick is frozen into
  the bank. Scene rendering must be deterministic.
- **Wordless animation** (Tim, 2026-09-26): scenes tell it with images, emotion and gestures
  — no words drawn on screen, so a scene works in any language. Laptop/phone screens show icons
  (bars, ✓/✗, progress), bubbles hold pictograms, cards hold icons. Words live only in the
  narration and subtitles, which the pipeline makes per locale.
- **Line boil = soft shimmer** (Tim, 2026-09-28): full boil re-jitters every line 12×/s, and
  Tim felt it as constant trembling. The default is now *soft*: the drawing holds its shape and
  the lines only shimmer faintly. `full` and `still` remain available per scene (bank
  `style.yaml` → `boil`).
- **Mascot GuoGuo** (Tim, 2026-10-13): a child-size **king penguin** called GuoGuo appears
  **somewhere in every scene**, as a recurring easter egg (peeking, reacting in the background).
  The design follows Tim's king-penguin plush photo (2026-10-13), which replaces the r7 A/B/C
  options:
  - a pear-shaped plush body;
  - a black head with orange teardrop ear patches and blue bead eyes;
  - a wide yellow collar band and a white belly;
  - a blue-grey back and flippers;
  - big black feet.
- **Scene library:** every scene idea or tryout is recorded in
  [`own-show-scenes.md`](own-show-scenes.md) (brief in Tim's words, picks, status), even if it
  never reaches a video; files in `output/own-show/scenes/<nnn-slug>/`.

## Style exploration — status (2026-10-13: **reopened; r7 variants awaiting Tim**)

The v0 bank (round 5 / ✅ row below) is the implemented baseline. Tim reopened the style on
2026-09-28, and two candidates were rejected:
- **Editorial cut-paper** (branch deleted 2026-10-13).
- **r6 AI style board** (2026-10-13): pixel art, clay, painted storybook and manga concept
  stills. Tim: "all not good".

**Tim's direction (2026-10-13):**
- Express the human through expression and gesture, "more like a cute stickman".
- The current locked character is fine; he wants to see more variants of it.
- The camera must turn easily (pan, tilt, zoom).
- References: *Animal Crossing: New Horizons* and *Sylvanian Families*.
- He asked to see both readings of those references: drawn variants (r7) and a 3D toy look
  (r7-3d).

Tryouts (throwaway; code + renders + comparison page) are in the EP1 project folder under
`style-tryouts/` — open `style-tryouts/index.html`. All tested on one beat: typing at the desk
→ agent errors → shock → grab phone, tap → relieved.

| Round | What | Result |
|---|---|---|
| 1 | Python/cairo vector rig (xkcd-like) vs AI images (Flux + Kontext edits) | Rig: fully consistent, $0, real motion, basic charm. AI: more polished stills but drifted off-brief; reference edits hold the character, prompt-only drifts badly; AI video untested (fal out of balance). Tim slightly preferred the AI look but distrusts its randomness. |
| 2 | Rig restyled to **Cyanide & Happiness, a bit cuter** (Tim's reference) | Reads well; three cuteness levels + expressions + palette sheet. |
| 3 | **Chibi** (Tim's pick) — hair/glasses options sheet; chibi in **3D** (Three.js toon shading + screen-space ink outlines) | 3D keeps the C&H look from any angle (turntable, side, ¾ front, over-the-shoulder showing the real laptop screen). Open issue: the big chibi head blocks the screen in over-the-shoulder while typing. |
| 4 | **Hand-drawn 2.5D rig** (`r4/`, built on the Mac, synced to the hub) — 3D joints/props/camera, but every line drawn flat (constant width, no shading, line boil + drawings on twos); head = drawn circle with sphere-projected face/glasses/hair; billboard props. Three inks: **A marker doodle**, **B pencil tie-down**, **C brush pen**. Picks A + 1 built in | Camera orbits/trucks while it still reads as a drawing (turnaround sheet 0–180°). Over-the-shoulder solved by film grammar: OTS as a mid shot + a **screen insert** without the actor (chibi head > laptop screen, so no angle from behind clears it). Screen carries hand-lettered UI. Tim: **A ≈ C, both acceptable** (B not picked); drawing "looks pretty good"; face doesn't feel right. |
| 4b | Face + hair option sheets (`r4/faces_r4.py`): 12 faces (front + turned) × 6 spiky-hair variants (front/40°/side/back), mix-and-match; face/hair are presets in the rig | Superseded by 4c (Tim sent his headshot instead of picking). |
| 4c | **Likeness from Tim's headshot** (`r4/likeness_r4.py`; photo not stored): two-layer hair (black spiky top with high M-hairline + forward tuft, grey buzzed sides + sideburns), thin wire panto glasses, ears, small almond eyes, straight brows, navy hoodie. 4 likeness levels (cute → closest, + C&H-simple); desk beat re-rendered with level 2 | Tim: hairline a little higher, hair more like short crop → 4d. |
| 4d | Hairline raised (forehead y 0.62 → 0.70) + **short crop** top (even short spikes, near-straight fringe, receding corners kept); variants A all-black crop (default) / B crop over grey buzzed sides / C = 4c. Likeness sheet + desk beat re-rendered with A + level 2 | **Tim: "A it is — my character is settled."** |
| 5 | **Tryout scene 1** — Tim's lioness brief, run as: brief → beat table → option sheets (lioness A/B/C, bulb A/B, draft stills) → timed animatic (bulb vs campfire) → wordless v2. Library entry **001** | Tim: lioness A, bulb, "your calls" on timing; **animation must be wordless**; keep every idea findable → scene library. |
| ✅ | **FROZEN: Tim = likeness 2 + short crop A + navy hoodie, line A (marker)**, 2.5D code rig. Preset + model sheet in `r4/character_tim.py` → `r4/tim_model_sheet.png` (turnaround 0–180°, 6 expressions, palette, line rules) | Seed of the character bank. |
| 6 | **AI style board** (`output/own-show/scenes/001-lioness-dishes/r6-style-board/`): beat 2 as pixel art, clay, painted storybook and manga, 2 GPT-Image stills each (~$1.40) | Tim: "all not good". |
| 7 | **Cute-stickman variants on the toon engine** (`r7/`, throwaway: `stickman.py` + `head7.py`): v0 vs A cute stickman, B hoodie stickman, C Animal Crossing chunky, D noodle limbs. Each has 9 gestures, 8 expressions with Animal Crossing-style reaction marks (sparkles, anger mark, gloom, tears, Aha-bulb) and a 2×2 camera demo (pan, tilt, zoom, orbit). Also **GuoGuo** options A/B/C (`guoguo.py`) with a scale check next to Tim. **r7-3d:** the same beat as a 3D toy (Three.js) in an Animal Crossing look and a Sylvanian flocked look. | Tim liked **B's lean torso, C's stubby sleeve arms and the expressions**, but wants a **full style rebuild**, not a v0 tweak. GuoGuo is to follow his plush photo. |
| 8 | **Drawn style rebuild** (`r8/`: `rebuild.py`, `clip.py`, `index.html`): the r7 picks in two new renderings, *soft-cel* (Animal Crossing feel: coloured lines, soft shading, warm skin, cozy coloured room) and *plush* (Sylvanian feel: fuzzy felt edges, fabric texture). Each has a turnaround, reactions, a room frame and an 8 s camera clip, plus GuoGuo from the photo. `r8/index.html` compares them 2×2 with the r7-3d toy pair. | Awaiting Tim's pick (drawn vs 3D × Animal Crossing vs Sylvanian). |

**Animation grammar (Tim, 2026-09-26): "their grammar, my doodle look"** — reference: the opening
of *How to raise calm kids like the Japanese* (Hana Explores, youtu.be/UdOx9lAbLvo). Take its
structure, keep the frozen doodle character + line A: the chibi-Tim **hosts** (stands beside the
content and presents: open palm, point, think, wave); explainer graphics **build up** beside him
(framed icon cards, red ✗ over wrong ways, green ✓ pills joined by arrows, bubbles,
maps/timelines — icons and pictograms only, see *Wordless animation*); **sets are ghosted** (faint thin line art, no fill) while the focus
character is in colour, optional warm focus **glow** and crowd fade; comic emphasis (speed lines,
tears/shake marks); **limited motion** — 3–5 s holds where elements pop in one by one, gentle
zoom, pose changes between beats, small wiggle loops (line boil). Not their clean/AI look.

**Tim's inputs so far:** chibi proportions; signature features = hair + glasses (clothes and
colours don't matter) — **picked hair A (spiky) + glasses 1 (round)**; wants more camera
angles; can work on the M3 Mac. On round 3: camera may move but **must not feel 3D (2.5D)**;
rounds 2/3 **too vivid**; wants **thick outline, doodle, rough tie-down — hand-drawn**.

**Research (2026-09-26):**
- Tools: keep the bank as repo data (JSON/SVG/YAML); Remotion as scene/compositing engine
  (headless render + Studio preview, `@remotion/three` for 3D); Rive or Blender Grease Pencil if
  quality plateaus; template apps (Vyond etc.) rejected (not agent-drivable, generic look).
- **Seedance 2.x** (Tim's chosen AI-video model): use the **official BytePlus ModelArk** API —
  fal charges exactly 2x. BytePlus: ≥$30 prepay to activate, available in Taiwan. Approx USD per
  output second: 2.0-mini 720p 0.076 · 2.0 720p 0.151 / 1080p 0.374 · 2.5 720p 0.231 / 1080p
  0.569. Replicate is the fallback (~20% more, no minimum). Known 2D weaknesses: line
  shimmer, over-smoothed motion (fights C&H snap), proportion drift. At normal volume it would
  eat the whole $50/month, so: **one ~$1 test** (rig animatic → Seedance restyle) before
  deciding whether it earns accent-shot use.

## Next steps (resume here — planned on the M3 Mac)

1. ~~Tim picks hair + glasses~~ — done: **A (spiky) + 1 (round)**, built into the round-4 rig.
2. ~~Decide 2D rig vs 3D toon~~ — Tim chose neither pure option: **hand-drawn 2.5D**. Round 4
   built it; ~~fix over-the-shoulder~~ — done (OTS mid shot + screen insert).
   Line: **A/C** (thick marker/brush ink). Engine: Tim likes the drawing → keep the code rig
   (Python/cairo, deterministic) as the animation engine; Remotion no longer the default.
   ~~Pick the character~~ — done: **likeness 2 + short crop A** (model sheet above).
3. **⏳ NEEDS TIM:** Tim creates the BytePlus ModelArk account (Taiwan) and provides the API
   key next session. Then: add a BytePlus provider to `~/.claude/bin/gen-video.py` and the key
   to `~/.claude/api-keys.json` → run the ~$1 Seedance restyle test.
4. ~~Style guide + **bank v0**~~: **shipped** (2026-09-28, EM REVIEW 3 = PASS; Sprint 9 / E9 v0).
   What it contains:
   - the `src/toon` engine;
   - Tim's picks as YAML in `assets/toon/bank/`;
   - scene 001 as a scene file, pixel-matched to the tryout;
   - the `toon` storyboard visual type;
   - `pipeline toon validate|render|sheet`;
   - line boil set to soft by default;
   - rendering at 30 fps with drawings at 12/s (Tim picked A), so compose's 30 fps concat
     doesn't judder;
   - hub-canonical goldens, and a compose smoke run on the hub.

   Before the first EP1 scene file, clear the E9 residuals in `docs/ROADMAP.md`.
   **Sprint 11** (greenlit 2026-10-13, branch `feat/e9-sprint11`) covers the style-independent
   ones. The style-dependent ones wait for the new style pick: laptop ✓/✗ screen art,
   `style.yaml` wiring and contact sheets. See README → *Toon*.
5. Retarget critics/evaluators to the audience lens above before scene reviews start.
6. Tim hands over the latest high-level script → scene breakdown together.

Housekeeping: the fal key works again (it rendered the r6 Flux pass on 2026-10-13). It's still
used for Flux images.
