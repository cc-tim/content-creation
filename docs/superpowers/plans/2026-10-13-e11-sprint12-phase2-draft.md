# E11 Sprint 12, Phase 2 — Toy3D Engine v0 (DRAFT, pending the Phase 1 checkpoint)

> **Status: draft.** Written while the EM reviews Phase 1. It is not executed until the checkpoint
> passes and the decisions in "Decisions needed" are settled. Then it becomes the executable plan
> (task steps with code, red-first ledger), in the format of the Phase 1 plan.

**Goal:** `assets/toy3d/scenes/001-beat2-break-in.yaml` (`engine: toy3d`) renders the locked look
headless and deterministically through compose on both machines. It matches the frozen v7 clip,
and goldens hold on both machines.

**Spec:** `docs/superpowers/specs/2026-10-13-toy3d-engine-v0-design.md` §5–§9, §12. Rows S12-6 …
S12-21. **Port source:** the immutable snapshot `style-tryouts/r7-3d/frozen-v7-20261013/` (§12
provenance).

## What the frozen tryout is (read 2026-10-13)

`scene.js` (1,501 lines) builds:
- the room: a dollhouse office with the hall behind the door, window, curtains, painting, clock,
  bookshelf, plants, rug, desk, laptop with wordless code bars, and a swivel chair;
- Tim (H3 hair, wire glasses, hoodie);
- the lioness (Sylvanian, apron);
- GuoGuo, standing and seated: lofted shell-fur bodies whose colours are painted from
  `guo_trace.json`;
- the bubble (plates + "!");
- the idea bulb (glow, rays, light);
- dust and smoke puffs;
- look A (physical vinyl, PCF shadows, RoomEnvironment at 0.3, GTAO, bloom 0.42/0.45/1.6, Neutral
  tone mapping at exposure 0.95, vignette 0.16).

Everything is a pure function of `t`, with the beat times hard-coded (`T = {door 2.2, walk0 2.3,
arrive 3.0, point 3.0, bubble 3.12, turn 3.78, shock 3.9, sweat 4.08, bulbDead 5.5}`).

**The motion is hand-keyed procedural acting, not pose blends:**
- typing sines on Tim's arms, torso, neck and legs;
- a wiggle that starts only once the shock blend completes, plus a tremble that decays over
  5.4–6.2 s;
- a half-sine hip hop on the shock;
- the chair pushed back over 0.35 s, while the shock pose takes 0.2 s;
- a cheated turn: the chair turns −0.75 rad, not toward the lioness;
- the lioness's walk cycle, from the distance walked;
- her turn 90°→45°, cheated toward the camera, on its own timing;
- her point pose with two Gaussian jabs, akimbo on another timing, ear flick and tail sway;
- GuoGuo's reactive acting: look-at with a head/body split, hop, squash and stretch, flipper
  flaps, jiggle, wide eyes, and fur secondary motion;
- the door's overshoot spring;
- the bulb's 14-step flicker table, then dead with a droop and smoke;
- the bubble's pop and "!" pulses synced to the jabs;
- one continuous five-segment camera move.

## The central design question: parity through the contract

Parity (S12-18) means the scene file, written in the contract's verbs, must reproduce those
frames within a tight same-backend tolerance. Phase 1's contract can't express the tryout as it
stands:

| Tryout feature | Contract today | Gap |
|---|---|---|
| `ease` = cubic in-out (camera, lioness turn, GuoGuo look, akimbo arm) | `smooth` is smoothstep | **missing ease** (`inout`) |
| Overlapping partial motions on different timings (shock 0.2 s, chair push 0.35 s, turn 0.34 s easeBack; point vs akimbo) | a pose beat blends the whole pose | **partial (layered) poses**: a pose sets only its channels |
| Loops with envelopes (wiggle after the blend completes; tremble decaying 1.5–2.3 s after) | 2.5D loops are always on | **loop envelopes** relative to the pose beat |
| One-shot accents (hip hop, jabs, ear flick, GuoGuo hop/flap/squash/jiggle) | none | **pose accents**: typed one-shot programs, timed from the beat |
| The door spring, the sweat-drop pop and fall, puff timing | `door` is a 0..1 lerp | `beats_at` must give each change's **time since start** |
| Cheated turns (chair −0.75, lioness 45°, GuoGuo looking at Tim − 0.3) | `face` aims geometrically | turns as **poses with a root-yaw channel**; GuoGuo's look as `face` + a yaw-offset pose channel |
| The bulb flicker table | `to: {b:}` beats | expressible today: 14 instant prop beats |
| Camera path | camera presets | a **keyframe-path preset** (bank data), local time = since the cut |

**Recommendation (Decision D2):** close the gaps in the contract and the bank, so parity is
genuinely faithful rather than "within a loosened tolerance":
- `inout` ease (engine-neutral; `beats_at` computes it; toon2d gets it too, as it renders any
  ease);
- `Change.since` and door/prop `since` in `beats_at` (engine-neutral data);
- partial poses, loop envelopes and accents (**toy3d capabilities**, bank data per character
  pose). The accent types are the tryout's programs ported verbatim (`hop`, `bump`, `flap`,
  `squash`, `jiggle`, `tremble`), each a pure function of (time since the beat, params);
- cheated turns as poses.

**Estimate:** about 0.5 session over the spec's 2. **Risk:** the accent library grows with EP1's
acting. That is fine: bank-fill sprints add accents the same way, from Tim's picks.

## Decisions needed (EM at the checkpoint, Tim where it's his call)

- **D1. Parity reference.** `locked_clip_v7.mp4` is H.264 CRF 16, so frames decoded from it carry
  compression noise.
  - **Recommend:** the gate compares the worked scene against **PNG reference frames rendered from
    the frozen snapshot's own code** on the Mac (Metal, ≥ 6 key times, in
    `tests/fixtures/toy3d/tryout_ref/`). That gives a tight tolerance.
  - The locked mp4 supplies the eyeball side-by-side sheet that Tim confirms.
- **D2. Faithful choreography** (above): contract extensions (`inout`, `since`) and toy3d bank
  capabilities (partial poses, loop envelopes, accents). The alternative is a looser parity
  tolerance that tolerates transient deviations. That's cheaper, but parity would no longer prove
  faithfulness.
- **D3. What is not ported:**
  - look B (retired);
  - hair options H1/H2/`beads` (only H3);
  - the GuoGuo mask/overlay fitting tooling (design-time; it stays in the snapshot);
  - the hair turntable.

  GuoGuo's **standing** build is ported only for the model sheet (S12-12's cast sheet).
- **D4. Frame transport.** The tryout returns PNG data URLs (base64) per frame, about 85 ms a
  frame on the Mac.
  - **Recommend:** keep PNG + base64 in v0, which is proven deterministic. `readPixels` is E11
    item 7.
  - ffmpeg takes `image2pipe` PNGs at `COMPOSE_FPS`.

## Architecture (Phase 2)

```
scene YAML ─► toon.scene (Phase 1) ─► beats_at ─► toy3d.state.resolve(sym, bank) ─► JSON state
                                                     (spots → positions, pose names → channels,
                                                      camera preset → path + local t)
toy3d.render (Python, playwright, pinned CfT) ─► stage.html + three r170 + engine modules
   page.init(bankJSON, {width, height, mode}) / page.applyState(state) / page.renderState(state) → PNG
```

| Unit | Responsibility |
|---|---|
| `assets/toy3d/bank/**.yaml` | characters (builder id, params, palette), `poses/<char>.yaml` (class, channels, loops with envelopes, accents, flags), `expressions/<char>.yaml` (face-decal recipe id + extras such as the sweat drop), `sets/office.yaml` (builder params, spots, lights, door, props in place), `cameras/*.yaml` (keyframe paths), `props/idea_bulb.yaml`, `style.yaml` (look A). Every item has `picked:` citing the snapshot sha |
| `src/toy3d/bank.py` | Pydantic models (`extra="forbid"`, file + field path errors), `Toy3DBank`, `.catalog` → `toon.catalog.Catalog` with `TOY3D` capabilities (widened per D2) |
| `src/toy3d/state.py` | `beats_at` → resolved JSON per frame (names → bank data); Layer A goldens serialise it |
| `src/toy3d/web/` | `stage.html` (seeded `Math.random`), `vendor/three-0.170.0/` (+ `SHA256SUMS`, MIT license), `engine/` modules ported from `scene.js`: `core.js` (helpers, seeded textures, materials from the style), `room.js`, `tim.js`, `lioness.js`, `guoguo.js` (loft + fur shells + trace painting; `guo_trace.json` is copied into the bank), `faces.js` (decal recipes), `props.js` (bulb, bubble, puffs), `perform.js` (channel blends, loops, accents, walk cycle, look-at), `camera.js` (paths), `post.js` (GTAO, bloom, output, grade) and `page.js` (the API) |
| `src/toy3d/render.py` | launch with `--use-angle=metal` (darwin) or `gl-egl` (linux); reads `UNMASKED_RENDERER_WEBGL` and refuses SwiftShader, Vulkan or anything unlisted; blank-frame guard; frame loop → ffmpeg (`.part` → rename); cache key (scene JSON, `Bank.model_dump_json`, engine JS hash, three `SHA256SUMS`, browser build, renderer string, size, fps). A cache hit launches no browser |
| `pipeline/composer/toon.py` | `engine == "toy3d"` → `toy3d.render.render_clip`; same duration fence; `SceneRenderError` only |
| `toon.catalog.load_catalog("toy3d")` | → `toy3d.bank.load_bank().catalog` |

## Tasks (to be expanded into steps after the checkpoint)

1. **Contract extensions for faithful choreography (D2),** red first:
   - `inout` ease;
   - `Change.since`, plus door and prop timing in `beats_at`;
   - the toy3d capability table gains `pose` partial/accents (catalog-level, so toon2d rejects
     them by name).

   Scene 001 stays byte-identical (the hashes are re-checked).
2. **Bank v0 + loader + catalog** (S12-6, S12-20):
   - YAML ported from the snapshot's constants, with provenance;
   - the exact-picks fence;
   - unknown and missing fields name the file and the path.
3. **Vendored three r170 + page skeleton + determinism fences** (S12-10 static part):
   - no `Math.random` / `Date` / `performance.now` / `requestAnimationFrame` / `fillText` /
     `strokeText` in the engine JS;
   - the no-look-constants fence (S12-7 static part).
4. **Runner** (S12-8, S12-9, S12-13, S12-14), with a fake page for the unit tests:
   - the allow-list and its refusals;
   - the blank-frame guard;
   - the cache key covering every input;
   - a cache hit that never launches a browser;
   - frame count = round(duration × `COMPOSE_FPS`);
   - atomic writes.
5. **Engine port** (the bulk):
   - the room, Tim (H3), the lioness, GuoGuo (seated + standing) and the props;
   - `perform.js` from `poseTim` / `poseLion` / `poseGuo` / `poseDoor` / `poseBulb` /
     `posePuffs` / `poseBubble`, restructured as channels, loops, accents and look-at driven by
     the resolved state;
   - the camera path from `camAt`;
   - look A from `style.yaml`.
6. **The worked scene + parity** (S12-18):
   - `001-beat2-break-in.yaml` reproduces the `T` timeline in contract beats;
   - the reference PNGs are rendered from the frozen snapshot (D1);
   - the parity test; the side-by-side sheet for Tim.
7. **Layers A/B/C goldens** (S12-11, S12-12):
   - symbolic state, exact;
   - `applyState` world matrices ≤ 1e-6 on both machines;
   - pixel goldens minted on the hub;
   - the tolerant compare in `tests/golden_policy.py`, with the noise floor calibrated on both
     machines;
   - the sensitivity set must go red: expression swap, a 5° shoulder rotation, a material colour,
     GuoGuo hidden, fur shells halved;
   - `PROVENANCE.md`.
8. **Compose integration** (S12-15, S12-16, S12-17):
   - the adapter;
   - the validator;
   - `pipeline toon validate|render` for toy3d;
   - the doctor check;
   - the fps fence;
   - cadence.
9. **Two-machine demo** (S12-19): two prerecorded takes; `blackdetect`; ms per frame on each
   machine.
10. **Gates on both machines + a separate code review** (S12-21).
