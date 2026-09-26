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

## Style exploration — status (2026-09-26: **character + line frozen**)

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
| ✅ | **FROZEN: Tim = likeness 2 + short crop A + navy hoodie, line A (marker)**, 2.5D code rig. Preset + model sheet in `r4/character_tim.py` → `r4/tim_model_sheet.png` (turnaround 0–180°, 6 expressions, palette, line rules) | Seed of the character bank. |

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
4. Style guide + **bank v0** — architectural (spec first, via brainstorming → spec →
   plan): promote the throwaway `r4/` rig into a real repo module; bank as data (Tim preset,
   desk set, laptop/phone, core poses, camera presets incl. OTS + screen insert); scene spec that
   references bank items by name and renders deterministically.
5. Retarget critics/evaluators to the audience lens above before scene reviews start.
6. Tim hands over the latest high-level script → scene breakdown together.

Housekeeping: fal key is flagged exhausted (`python3 ~/.claude/bin/keymanager.py reset fal tim`
after a top-up; still used for Flux images).
