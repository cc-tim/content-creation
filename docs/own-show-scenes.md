# Own-show scene library

Every scene idea, tryout or finished scene for Tim's own videos gets an entry here, even if it
never makes it into a video. Keep Tim's brief in his own words. Rules for how scenes look and
move are in [`own-show.md`](own-show.md): wordless animation, Tim's doodle look, Hana grammar.

**Files** (code, option sheets, renders) live in `output/own-show/scenes/<nnn-slug>/`. They are
not in git. The hub copy is canonical, and the Mac may hold a partial copy. The EP1 board (plot, every
scene draft, clips, open picks) is `output/own-show/index.html`, served by the dashboard at
https://dashboard.keeppro.io/output/own-show/index.html. After a Mac render, rsync the scene folder to the hub. Renders go stale
when the rig changes, so the entry records what was decided, not just where the files are.

| # | Scene | Status | Episode | Files |
|---|---|---|---|---|
| 001 | Locked in → the lioness → dishes → the idea fades | tryout · animatic v2 (wordless, bulb) — **meets Tim's expectation** (quality bar) | not assigned | `output/own-show/scenes/001-lioness-dishes/` · engine scene `assets/toon/scenes/001-lioness-dishes.yaml` |
| 002 | Before: the school run (lioness bursts in → you leave → the bulb fades) | tryout · v4 (3D toy, Tim's face A + flat mouth) · **OK'd by Tim 2026-10-29**; daughter = koala round 3 B, not in this scene (no placement pick yet, not blocking) | not assigned (was EP1 scene 1 until 2026-11-02, replaced by 003) | `output/own-show/scenes/002-before-school-run/` (open `index.html`; wording in `scene.md`) |
| 003 | Steer from anywhere (Claude works at the desk while you're on the sofa / toilet / train; then you just talk to it) | voice cut in (2026-11-03) · script timed in `scene.md` · picking elements | EP1 scene 1 (cold open) | `output/own-show/scenes/003-steer-from-anywhere/` (wording in `scene.md`) |

## 001 · Locked in → the lioness → dishes → the idea fades

- **Brief (Tim, 2026-09-26):** "I was really lock in on building app with ai agent, but my wife
  (A fierce lioness) break into the room and tell me to do the chores (washing dishes), while I
  am doing that, the light bulb (idea) in my head fade out."
- **Tim's picks:** lioness **A**, a full lioness in an apron (B, a wife with a mane, and C, a
  lioness shadow, were not picked). The idea is a **light bulb** (a campfire was tried and not
  picked). It fades slowly and ends in a snuffed-out smoke wisp. Staging notes were "good";
  timing was left to Claude.
- **Beats (13 s):** 1 locked in (typing, focus glow, bright bulb) · 2 break-in (door swings,
  speed lines, the lioness points, a plates + "!" bubble, anger mark, you shocked, the bulb
  flickers) · 3 dishes (you scrub at the sink, the stack shrinks, the bulb dims) · 4 idea gone
  (close-up, one last flicker, out, smoke, ✗-bulb card).
- **Placeholder narration** (for Tim's voice; never drawn in the animation): "I was locked
  in, building an app with my agent…" / "…then the lioness arrived." / "So I did the
  dishes." / "And the idea? Gone."
- **Bank candidates it created:** lioness A (character); office wall with a door and the
  kitchen (ghosted sets); idea bulb and campfire (props); plates, plate stack, faucet and suds;
  pictogram speech bubble, anger mark, ✗ card, speed lines, focus glow (graphics); standing
  point and washing dishes (poses).
- **Verdict (Tim, 2026-09-26):** "this tryout scene meet my expectation" — use v2 as the
  reference bar for scene quality and the acceptance scene for bank v0.
- **Engine port (Tim, 2026-09-28):** the scene now also lives as the scene file
  `assets/toon/scenes/001-lioness-dishes.yaml` on the toon engine, pixel-matched to v2. Tim:
  "looks good". His one caveat was the constant trembling, so line boil became a setting and
  soft shimmer is the default.
- **Files:** `scene_lioness.py` (throwaway; uses the style-tryouts `r4` rig) · step-3 sheets
  `r5_lioness_options.png`, `r5_bulb_options.png`, `r5_idea_options.png`, `r5_thumbs.png` ·
  v1 animatics with on-screen words `r5_animatic_{bulb,fire}.mp4` · **v2 wordless**
  `animatic_v2_bulb.mp4`.

## 002 · Before: the school run

- **Brief (Tim, 2026-10-16):** EP1 is built as "Before / After" (Tim's pick A). Scene 1, the cold
  open, shows the "before" morning: you're at the desk with the agent working, it's time for the
  school run, you leave, and the idea fades. The real "after" moment is a few minutes with your
  daughter, a quick check from the phone, and the context doesn't fade.
- **How we work on it (Tim, 2026-10-17):** `scene.md` holds the scene in plain words with times.
  It is the source Tim edits directly ("I want to know the wording and give the change directly").
  The scene YAML follows it, and every version gets a line in its Changes log and a clip on
  `index.html`. Option sheets Tim has decided move into the board's collapsed archive (Tim,
  2026-10-19), so the board shows only what is still open.
- **v1 (2026-10-17):** 11 s, 4 shots: push-in on the desk → clock insert → shock close-up → wide,
  you walk out the door, the bulb dies, then the empty desk.
- **v2 (Tim's notes, 2026-10-17):** no clock. In shot 2 **the lioness bursts in and points: "take
  the koala to school"** (her acting from scene 001; a "!" bubble stands in). 12.6 s.
- **v3 (2026-10-19):** v2 with Tim's "dead fish" A eyes as his default face.
- **v4 (2026-10-19):** v3 with v0's flat mouth instead of the smile, and a blink that matches.
- **Tim's OK (2026-10-29):** scene 1's open items are cleared — v4 stands and the "!" bubble stays
  as the stand-in. No daughter placement pick; not blocking.
- **Tim's picks:**
  - **Default face = "dead fish" A eyes + v0's flat mouth** (v0 lid: heavy flat lids, pupils hanging
    under them; no smile), for Tim in every scene. Eyes picked 2026-10-17, the flat mouth 2026-10-19.
    Decal `tim_deadA_flat`, blink `tim_deadA_flat_blink`. Sheet: `options/eyes_options.png`.
  - **Daughter = a koala.** Round 1 (three designs from scratch) was "all not good" and too big.
    **Round 2** is built after the **Sylvanian Families Koala Family babies** (Tim's reference),
    with proportions measured off the product photo, smaller, in sizes S/XS. Sheet:
    `options/koala2_options.png`. Tim (2026-10-19): "another version… a bit more realistic… make it
    feel fluffy". **Round 3** puts GuoGuo's shell fur on her, with bead eyes and a slit blink:
    A = round 2's shape with short fur, B = real-koala markings (white chin, chest and ear tufts, a big
    dark nose), C = B with long fur. All size S. **Tim picked B (2026-10-19), size S.** Sheet:
    `options/koala3_options.png`. With her fur, GuoGuo is no longer the only furry one. She isn't in
    the scene yet: where she comes in is Tim's next pick.
- **Engine gap found:** the door resets to closed at every cut (no carry-over of door state), so
  shot 4 re-opens it with a faint dust puff. This is a candidate for the EM.
- **Throwaway, not frozen:** Tim's stand/walk/glance/sit_rest poses, a body-turn channel, the new
  spots and cameras. They live in a bank copy in the scene folder. The eye decals and the koala
  builder are engine code on the local branch `tryout/ep1-s002` (worktree
  `.worktrees/ep1-s002-tryout`). They go into the real bank through the EM (E11 item 3) once Tim
  picks.
- **Render:** from the worktree, `TOY3D_ASSETS=<scene folder>/toy3d uv run pipeline toon render
  <scene folder>/toy3d/scenes/002-before-school-run.yaml`. Master's engine can't load the bank copy
  any more, because the koala kind exists only on the tryout branch.
- **Files:** `toy3d/scenes/002-before-school-run.yaml` (v1 kept as `.v1.yaml`) ·
  `renders/002_v{1,2,3,4}.mp4` · `scene.md` · `index.html` · `options/`.

## 003 · Steer from anywhere

- **Brief (Tim, 2026-11-02):** the new EP1 cold open. It replaces 002.
  - **Part 1, under "Have you enter the usage of AI that you can keep steering the working progress
    no matter if your are in front of desktop or not? …":** "Claude working on my computer and I'm
    sitting in front of computer (typing keyboard), then I am switching from place to place (stand and
    walk out from my computer, then start a split screen, left screen is keeping exactly same as Claude
    working (spinning banner). At the right screen, in order is 1. me laying on the sofa and focus
    watching on mobile phone, 2. Sitting on the toilet 3. Standing inside the crowded train, and
    grabbing handrails."
  - **Part 2, under "And among the all, the way of communication could be changed, maybe through
    talking …":** "1. Laying down on sofa, eating snack, only to talk with mobile 2. Sitting on the
    toilet but face is very focus on pooping, and squeeze out a short sentence: 'agree, proceed'."
- **First scene under the less-detail rule** (`own-show.md`): you plus one or two key props per place,
  on a plain ground.
- **Timing:** Tim cuts the voice track first; the shots are timed to it.
- **Open picks:** the minimal look, the laptop's "working" icon, new props (phone, sofa, snack, toilet,
  handrail, a minimal crowd), new poses, the split screen, and a ✓ bubble on
  "agree, proceed". These are listed in `scene.md`.
- **GuoGuo (Tim, 2026-11-02):** "let GuoGuo stay at where the screen I belong, it have no actions or
  expression for scene 1". He sits wherever you are (on your side of the split screen) and stays still.
- **Minimal-look sheet v1 (2026-11-02):** the desk shot drawn three ways: A plain colour, B a soft floor
  patch, C faint room outlines (`options/minimal_look_v1.png`). Engine switch `params.minimal` on the
  office set, tryout branch `tryout/ep1-s002`; bank copies per look in `toy3d-look/{A,B,C}/`.
- **EP1 scene 2 outline slide mock (2026-11-02):** A numbers, B icons, C A as a chapter card, plus a motion
  preview of the shrink-to-corner and pop-in (`output/own-show/scenes/ep1-s2-outline/`, source `outline.html`).
- **Tim's picks (2026-11-02):** minimal look **C · faint room outlines**. GuoGuo is "too obvious": make him
  about 5–6% smaller and **hide him under the desk**. At 5.5% smaller his head pokes through the desktop
  and at 12% he fits, so the size is back with Tim (`options/guoguo_under_desk_v1.png`). Engine: the
  character `scale` now applies to GuoGuo (tryout branch).
- **Scene 2 outline (Tim, 2026-11-02):** **A · numbers**. C (the chapter card) is optional and kept for now.
  Tim says all the points quickly in scene 2; the slide probably isn't shown again in later scenes.
- **GuoGuo size (Tim, 2026-11-02): 12% smaller** in scene 003, so he fits fully under the desk.
- **Working-icon sheet v1 (2026-11-02):** A a floating coral asterisk beside the laptop, B a floating loading ring,
  C the asterisk on the screen with the camera behind the empty chair (`options/working_icon_v1.png`,
  bank copies in `toy3d-icon/{A,B,C}/`).
- **Working icon (Tim, 2026-11-02): A**, the coral asterisk, "spins … filled white circle background and 1~2
  smaller white bubble to point linking to the desktop". Built as `toy3d-icon/A2`. C rejected: "not showing the
  screen in animation to show a fake screen" (now a rule in `own-show.md`).
- **Sofa sheet v1 (2026-11-02):** A lying on your side facing the camera, phone at your chest; B slumped deep in
  the sofa, phone under your chin. Lying flat on the back was tried and dropped (head twists, phone edge-on).
  `options/sofa_v1.png`, bank copies in `toy3d-sofa/{A,B}/`. Engine: sofa piece, hidden desk, phone holds
  (flags `phone_<hold>`), tryout branch.
- **Tim (2026-11-02):** GuoGuo stays **under the desk the whole scene** (replaces "wherever you are"). Sofa: **A**
  (lying on your side), but "the posture need some fix, looks weird".
- **Sofa A posture fix v2 (2026-11-02):** body flat on the cushion, head upright on the armrest (neck counter-tilt),
  legs stacked on the seat; no GuoGuo on the sofa. `options/sofa_A_fix_v2.png`, pose `side_v1` in `toy3d-sofa/A`.
- **Sofa A fix v3 (2026-11-02):** Tim: "not the head posture, should be body and legs". Head back to sheet v1's tilt; body
  sunk onto the seat and moved off the back cushion, legs stretched along the sofa (feet away from the camera), head at
  the armrest end. Also shown from a higher camera. `options/sofa_A_fix_v3.png`, poses `side_v7`/`side_v8`.
- **Sofa A v4 (2026-11-02):** Tim: keep the original camera; fix v3's flat stacked legs were still wrong. New shape:
  back propped on the armrest, A1 one knee up / A2 both knees up (legs bend side-on to the camera).
  `options/sofa_A_v4.png`, poses `lounge_knee`/`lounge_knees`, phone hold `lounge`.
- **Sofa decision (Tim, 2026-11-02):** "prefer the original version (first one)" — keep sheet v1 A (side-lying, the
  original pose and camera). Fixes v2–v4 are kept for reference only.
- **Voice cut + new script (Tim, 2026-11-03):** Tim's voice track (`audio/voice_v1.m4a`, 1:09, Whisper word
  timings in `audio/voice_v1.whisper.json`) with a [ ] animation note per line. It replaces the 2-part brief:
  - [Base: Claude working on my computer and I'm sitting in front of computer (typing keyboard)] [1. Show up multiple
    working progress 2. Show up the lighting day and night] → "We're in the age that AI can work in parallel…24/7 for you."
  - [Looks very focus but then quickly get the sleeping eyes and decide to stand and walk out] → "But have you enter the
    AI usage that you can keep steering the working progress even your are not in front of desktop?"
  - [Little robot growing into the buff doge (head swap by the little robot)] → "Because no matter how AI capabilities grow"
  - [Switching from place to place (reuse the stand-and-walk-out, then a split screen, left keeps Claude working
    (spinning banner); right in order: 1. me laying on the sofa focused on the phone, 2. standing inside the crowded
    train grabbing handrails, 3. entering and sitting on the toilet)] → "The condition for a human won't change, we're
    constrained by low focus span…or the time too fragmented…or … we're just a mortal"
  - [Laying down on sofa, eating snack, while scrolling phone, show mouth talking with mobile] → "And among the all, the
    way to communicate also changing, typing is not that convenient"
  - [Sitting on the toilet but face is very focus on pooping, but in the middle, quickly change face expression and
    showing a dialogue "Looks good, proceed" with mouth talking to the phone] → "what we're hoping to achieve… is continuity"
  - Timed rows are in `scene.md` → *Script* (the EP1 board reads them from there). The place-to-place note is split
    4a–4d so sofa / train / toilet each land on their reason (suggested).
- **Tim's answers (2026-11-03):** "Looks good, proceed" is a **text bubble**: "this is a inside joke, so no harm to break our
  rule". Little robot: "you build it, might be our future character". Buff doge: "yes, reference is Swole Doge meme". Tim
  will send a slightly faster voice cut; times get redone from it.
- **Row 1 sheet v1 (2026-11-03):** many tasks A several task bubbles / B one bubble + progress bars / C task bubbles +
  progress rings; day → night L1 light only (blue room, the laptop lights your face) / L2 + a floating sun → moon / L3 +
  the faint window fills with sky. `options/row1_wip_daynight_v1.png`, bank copies in `toy3d-row1/<variant>/`; engine
  keys `minimal.working.more|progress`, `minimal.sky` (tryout branch).
