# Own-show scene library

Every scene idea, tryout or finished scene for Tim's own videos gets an entry here, even if it
never makes it into a video. Keep Tim's brief in his own words. Rules for how scenes look and
move are in [`own-show.md`](own-show.md): wordless animation, Tim's doodle look, Hana grammar.

**Files** (code, option sheets, renders) live in `output/own-show/scenes/<nnn-slug>/`. They are
not in git. The hub copy is canonical, and the Mac may hold a partial copy. Renders go stale
when the rig changes, so the entry records what was decided, not just where the files are.

| # | Scene | Status | Episode | Files |
|---|---|---|---|---|
| 001 | Locked in → the lioness → dishes → the idea fades | tryout · animatic v2 (wordless, bulb) — **meets Tim's expectation** (quality bar) | not assigned | `output/own-show/scenes/001-lioness-dishes/` · engine scene `assets/toon/scenes/001-lioness-dishes.yaml` |
| 002 | Before: the school run (lioness bursts in → you leave → the bulb fades) | tryout · v2 draft (3D toy); Tim's eyes A picked; koala daughter round 2 awaiting Tim | EP1 scene 1 (cold open) | `output/own-show/scenes/002-before-school-run/` (open `index.html`; wording in `scene.md`) |

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
  `index.html`.
- **v1 (2026-10-17):** 11 s, 4 shots: push-in on the desk → clock insert → shock close-up → wide,
  you walk out the door, the bulb dies, then the empty desk.
- **v2 (Tim's notes, 2026-10-17):** no clock. In shot 2 **the lioness bursts in and points: "take
  the koala to school"** (her acting from scene 001; a "!" bubble stands in). 12.6 s.
- **Tim's picks:**
  - **Default eyes = "dead fish" A** (v0 lid: heavy flat lids, pupils hanging under them), keeping
    today's smile, for Tim in every scene. Sheet: `options/eyes_options.png`.
  - **Daughter = a koala.** Round 1 (three designs from scratch) was "all not good" and too big.
    **Round 2** is built after the **Sylvanian Families Koala Family babies** (Tim's reference),
    with proportions measured off the product photo, smaller, in sizes S/XS. It waits on Tim's
    verdict and size pick. Sheet: `options/koala2_options.png`.
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
  `renders/002_v{1,2}.mp4` · `scene.md` · `index.html` · `options/`.
