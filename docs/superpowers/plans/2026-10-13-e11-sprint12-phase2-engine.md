# E11 Sprint 12, Phase 2 — Toy3D Engine v0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `assets/toy3d/scenes/001-beat2-break-in.yaml` (`engine: toy3d`) renders the locked look
headless and deterministically through compose on both machines. It matches the frozen v7
snapshot, and three layers of goldens hold on both machines.

**Architecture:**
- **Python does the acting; the page only draws.**
  - `toy3d.acting.resolve(scene, bank, t)` turns `beats_at` plus the bank's poses (channels, loops,
    accents, flags), walk cycles, look-at, door spring, bulb, bubble, laptop and camera tweens into
    a frame spec: joint values, world transforms of roots, the camera, visibility and decal ids.
  - The page (`src/toy3d/web/`, three r170 vendored) builds the world once from the resolved bank
    JSON (`init`). It then only applies a frame spec (`applyState`) and renders it
    (`renderState` → PNG).
  - So Layer A (the frame spec) is exact Python in the default suite, Layer B (applied world
    matrices) is a no-GL browser check, and the JS port is the snapshot's builders plus a thin
    applier.
- `toy3d.runtime` launches the pinned Chrome for Testing through Python `playwright==1.62.0`
  (chromium-1234 = CfT 151.0.7922.34, on both machines).
  - It serves the page through `page.route` (no port).
  - It enforces the GPU allow-list (darwin `metal`, linux `gl-egl`), refusing SwiftShader, Vulkan,
    llvmpipe or anything unlisted.
- `toy3d.render` streams PNG frames into ffmpeg at `COMPOSE_FPS`. It has a blank-frame guard, an
  atomic `.part` → rename and a cache key that covers every input.

**Tech Stack:** Python 3.13 (uv), pydantic 2.12, playwright 1.62 (Python), Chrome for Testing 151,
three.js r170 (vendored, MIT), ffmpeg, PIL, numpy, pytest.

**Spec:** `docs/superpowers/specs/2026-10-13-toy3d-engine-v0-design.md` §5–§9, §12. Rows S12-5
(A2) and S12-6 … S12-23; the EM checkpoint record (D1–D4, A1–A3) is in `docs/ROADMAP.md`
Sprint 12. **Port source:** `style-tryouts/r7-3d/frozen-v7-20261013/` (SHA256SUMS
`d9c61f63…5d75`; `scene.js` `4dbdf8e4…0356`).

**Base:** `feat/e11-sprint12` at `8d78e95` (Phase 1 + the EM's checkpoint records).

## Rulings (EM checkpoint D1–D4, plus the design rulings this plan adds)

- **EM D1:** the parity references are PNGs rendered from the snapshot's own code:
  - hash-checked against its SHA256SUMS;
  - on the pinned CfT, Mac Metal;
  - at 6 key times, plus one standing-GuoGuo design view (D3).

  `PROVENANCE.md` records the browser build, the renderer string and the snapshot hashes. A
  one-time check ties the references to decoded `locked_clip_v7.mp4` frames within H.264 noise.
  The mp4 makes Tim's side-by-side sheet.
- **EM D2:**
  - The only new authored field is the `inout` ease. Time since start is internal `beats_at`
    data.
  - Partial poses, loop envelopes, verbatim accents and cheated turns are toy3d bank data. Every
    one of them is used by the worked scene or the model sheet.
  - No new motion.
- **EM D3:** look B, hair H1/H2/beads, the mask/overlay tooling and the hair turntable are not
  ported. Standing GuoGuo is.
- **EM D4:** PNG + base64 frame transport.
- **P2-R1, the acting model (per character, bank data):**
  - **Rig channels:** each character's rig lists the channels its poses may set (joint rotations
    in radians, offsets in metres, and for GuoGuo, named acting signals).
  - **Poses:** a pose is `full` (all rig channels; unset = 0) or `partial` (only its channels). It
    has a `class` (sit/stand), `channels`, `loops`, `accents` and `flags`.
  - **The fold:** a pose change blends its target into each channel it sets, `v = lerp(v, target,
    k)`, in `beats_at` play order. That is the 2.5D fold, per channel.
  - **Loops** are periodic terms inside a pose's target, so they blend with it:
    `sin`/`abs_sin` at absolute scene time. `until_next: stop` ends one at the next **full** pose
    change on that actor (partial poses such as the chair turn don't).
  - **Accents** are additive after the fold, never blended, and timed from their change's start:
    - `half_sine`, `bump`, `decay_sine`, `flap`, `hold` and `osc`, each the snapshot's own formula;
    - with envelopes: `start`, `fade: [a, b]`, and `until_next: {fade: s}`.
  - **Flags** (the finger, GuoGuo's wide eyes) turn on once their change's eased k > 0.05 and
    `since ≥ from`, and stay on.
  - **An expression-only pose beat** (`to` equals the current pose) only swaps the face decal. It
    starts nothing and ends no loop.
- **P2-R1a (found by the every-frame oracle, Task 5):** a full pose resets the body channels
  only. The cheated turns (`root.*`, `seat.*`, `look.*`, P2-R3) stay where they are unless the pose
  names them, so Tim's chair turn (3.78) survives his full shock pose (3.9), as in the snapshot.
  A pose beat's decal switches only when its `expr` differs from the expression `beats_at`
  inherits (a later beat without `expr` inherits the last *completed* one and must not undo a
  switch still blending in). The walk's terms enter the fold at the move's place in play order,
  so later poses blend them away (the snapshot's `lerp(-swing, …, pk)`). A face aims at where its
  target is at `t` (the snapshot's `aim(lion.root.position)`), not where earlier changes left it.
- **P2-R1b (the code reviews, Task 11):** `Change` carries `to_set` / `expr_set` (internal
  `beats_at` data, not authored fields). A pose beat with a `to` blends that pose in from
  wherever the fold is, unless it is the pose already heading in. A beat without `to` changes
  the face only. An authored `expr` switches the face as its beat starts. A face turns the short
  way round.
- **P2-R10, seats (Phase 2 review I2, M6, M8):** toy3d refuses at load, so the validator and the
  CLI refuse too, through `SceneCatalog.scene_problems`, which runs once every name resolves:
  - a seated character's move;
  - a move into a seat;
  - a seat for a character with no `seat_height`;
  - sitting without a seat, or standing in one;
  - a partial pose as a placement.

  So the laptop's typist is the character placed at its seat.
- **P2-R11, never silent at runtime (Phase 2 review I4, I5, M1, M2):**
  - `runtime.start` is the one way in for clips, stills and doctor: init, the backend allow-list
    and the renderer record.
  - Console errors fail the next page call. three's `onShaderError` throws. A lost WebGL context
    fails `renderState`.
  - A watchdog (`CALL_TIMEOUT`) stops a hung call's driver and browser: `evaluate` has no timeout.
  - A frame whose strongest edge is under 24 levels is an empty world.
- **P2-R12, the engine-neutral timeline (A3 m2):** `beats_at`, its dataclasses, `_progress`, `POP`
  and the eases live in `toon/beats.py`; `toon.timeline` and `toon.engine.mathx` re-export them.
  Loading the contract and the timeline loads no 2.5D code. The 2.5D renderer refuses a
  non-toon2d scene (A3 m1).
- **P2-R13, the clip cache key (A3 I1, Phase 2 review M4):** the key hashes:
  - each frame's resolved spec (computed once, and reused for the render);
  - every vendored three.js file;
  - the module-level import closure of `src/toy3d`.

  The toy3d bank is its own `SceneCatalog`, so compose renders with the bank it validated (A3 m5).
- **P2-R2, engine programs are code; their parameters are bank data:**
  - the lioness's walk cycle on `move`: phase from the distance walked, a step envelope settling
    `1/settle` s after arrival;
  - GuoGuo's look-at on `face`:
    - head/body split with seat yaw, body share and head clamp;
    - squash and stretch from hop velocity;
    - flipper and fur-push mixing;
  - the door's overshoot spring;
  - the bulb's idle drift, droop and smoke;
  - the bubble's pop (`e_back`) and its "!" pulse, driven by the speaker's `bubble_bang` signal;
  - the laptop's code bars, which fill while the actor at its desk spot holds a pose flagged
    `typing`.

  Each is the snapshot's code, ported verbatim to Python with the constants moved to YAML.
- **P2-R3, cheated turns are partial poses:**
  - Tim's chair turn: `seat.ry`;
  - the lioness's 90°→45°: `root.ry`, relative to the spot's yaw;
  - GuoGuo's look offset: the `look.dy` signal.

  `face` aims geometrically at the target's **root** (spot or walked position). A seat offset
  such as Tim's chair push is a pose channel, not his root, as in the snapshot (`aim(TIM_X,
  TIM_Z)`).
- **P2-R4, GuoGuo's build is his pose class:** `sit` → the seated build, `stand` → the standing
  build. The worked scene seats him on the shelf. The design view stands him at the `turntable`
  spot.
- **P2-R5, a `move` in toy3d translates and walks; it never turns.** Facing comes from poses and
  `face`, as in the snapshot. A destination spot's yaw is not read, and the bank's spots carry
  `yaw` only for placement.
- **P2-R6, camera presets are tween lists** (bank data) for an orbit `pivot` / `az` / `el` /
  `dist`, a `target` and a `fov`. Each tween is `{at, over, ease, to}`, folded in order with
  `lerp(prev, to, eased k)`: `camAt`'s five segments exactly. Fixed presets (the design-view
  stills) have no tweens. Local time is the time since the camera cut.
- **P2-R7, references and goldens downscale 1920×1080 renders to 960×540** with PIL LANCZOS. The
  snapshot's renderer size is fixed at 1080p, and that keeps the fixtures small. Parity and Layer C
  compare those.
- **P2-R8, the cache key carries the renderer string from a per-machine record**
  (`~/.cache/content-creation/toy3d/renderer.json`, rewritten at every browser launch). So a cache
  hit launches nothing. A changed GPU or driver re-keys on the next launch, and doctor launches.
- **P2-R9, the look is bank data:** palettes, material parameters, lights, environment, fog, tone
  mapping, GTAO, bloom and the grade. The static fence (S12-7) forbids colour literals and
  tone/post numbers in engine JS. Geometry dimensions stay in the ported builders (geometry, not
  look). Design-pick tables (GuoGuo's profiles, beak, flippers, ear patch, eye; Tim's hairline)
  are bank data.

## Global Constraints

- **Scene 001 (2.5D) byte-identical** after every task that touches `toon` (431 hashes against
  `5d0f9b3`).
- **Non-goal fence:**
  - `assets/toy3d/scenes/` holds only `001-beat2-break-in.yaml`;
  - the bank holds only the snapshot's picks;
  - every accent, loop and partial pose is used by the worked scene or the model sheet;
  - `assets/toon/**` and `tests/fixtures/toon/**` are unchanged.
- **Never silent:** a missing build, a disallowed backend, a blank frame or an unknown bank field
  each fail loudly, naming the fix. Compose sees `SceneRenderError` only, and never a 2.5D
  fallback.
- **Red first** for behaviour: a test-only commit, then the fix; the ledger records both. Guards
  and pins carry mutation evidence.
- **Commits:** small `type(scope): message` with the Co-Authored-By line; explicit `git add`
  paths (never `tmp/`, `.agent-memory/` or `docs/ROADMAP.md`); no push, no merge.
- **Hub:** isolated bundle clones only.
- **Gates:** the Sprint 12 run command from the test plan; at the end, the full suite, ruff and
  mypy on both machines.

## Review Focus

1. **A scene whose narration is longer than the authored 8.0 s:** the last shot holds, the
   camera path's local time runs past its last tween and holds, and the clip frame count follows
   the narration. Pinned in Task 9 (`test_clip_frame_count_equals_narration`, both lengths).
2. **The browser build is missing** (playwright's cache wiped): a loud `Toy3DRenderError` naming
   `uv run playwright install chromium` and the build id. Not a traceback, and not a fallback to
   system Chrome. Pinned in Task 4.
3. **The page throws during init** (a bank value the builder can't take): the page error text
   reaches `Toy3DRenderError`. Never a hang until the timeout. Pinned in Task 4 (fake page) and
   Task 6 (a real bad colour).
4. **A frame half-written by ffmpeg when the process dies:** no `.mp4` and no cache stamp survive.
   Pinned in Task 4.
5. **Mac versus hub renderer strings differ, so the cache keys differ:** a clip rendered on the
   Mac is never served on the hub as cached. Pinned in Task 4 (`test_cache_key_covers_every_input`
   renderer case).

---

### Task 1: The `inout` ease and time since start (S12-22)

**Files:** `src/toon/scene.py` (`Ease`), `src/toon/engine/mathx.py` (`EASES["inout"]`),
`src/toon/timeline.py` (`Change.since`, `Change.over`, `DoorAt`, `PropAt.since`); Test
`tests/unit/toon/test_symbolic_timeline.py`, `tests/unit/toon/test_contract_conformance.py`.

- [ ] **Red:**
  - `inout` loads on both engines, and its value at 0.25 / 0.5 / 0.75 equals the snapshot's
    `x < .5 ? 4x³ : 1 − (−2x+2)³/2`;
  - `beats_at` gives each change's `since` and `over`, and the door's (`DoorAt(value, to, since,
    over)`);
  - a prop's last `to`/`out` change carries `since`.

  Expected: `Input should be 'linear', 'smooth', 'out' or 'back'`; `AttributeError: 'Change'
  object has no attribute 'since'`.
- [ ] **Fix:** add `inout` to `Ease` and `EASES`. `beats_at` keeps `door: float` (2.5D reads it)
  and adds `door_at: DoorAt | None`. `Change` gains `since` and `over` (defaults keep existing
  constructors valid).
- [ ] Byte-identity: 431 hashes against `5d0f9b3`.

### Task 2: Bank v0, loader and catalog (S12-6, S12-20, S12-23 bank half, S12-5 A2)

**Files:**
- Create:
  - `assets/toy3d/bank/` (`style.yaml`, `characters/{tim,lioness,guoguo}.yaml`,
    `poses/{tim,lioness,guoguo}.yaml`, `expressions/{tim,lioness,guoguo}.yaml`,
    `sets/office.yaml`, `cameras/{beat2,stills}.yaml`, `props/idea_bulb.yaml`, `guo_trace.json`);
  - `src/toy3d/{__init__,bank}.py`;
  - `tests/unit/toy3d/test_bank.py`.
- Modify:
  - `toon/catalog.py` (`load_catalog("toy3d")`);
  - `tests/unit/toon/test_contract_conformance.py` (the real toy3d catalog);
  - `pyproject.toml` (hatch packages + package data).

- **Models:**
  - `Toy3DBank(root, style, characters, poses, expressions, sets, cameras, props, trace)`, every
    pick with `picked: {date, source}` citing the snapshot sha;
  - `Pose(class_, partial, channels, loops, accents, flags)`;
  - `Loop(channel, wave, amp, rate, phase, until_next)`;
  - `Accent`, a discriminated union on `type`;
  - unknown fields fail as `<file>: <path>: <msg>`, through pydantic `extra="forbid"` plus
    channel names checked against the character's `rig.channels`.
- **`.catalog`:** a `toon.catalog.Catalog` with `TOY3D`, the names, per-character poses with
  their class, and per-character expressions; icons `dishes` and `bang`.
- [ ] **Red:**
  - `test_bank.py::test_v0_bank_holds_exactly_the_picked_items`;
  - `::test_every_item_carries_provenance`;
  - `::test_acting_fields_fail_naming_file_and_path` (an unknown accent type, an unknown channel,
    an extra field);
  - `::test_every_accent_is_used` (each accent, loop and partial pose is referenced by the worked
    scene or the design view; until the scene exists, the test reads the worked-scene fixture
    committed in this task);
  - `test_contract_conformance.py`, parametrised with the real catalog's roles;
  - `test_contract_seam.py::test_load_catalog_toy3d_returns_the_bank_catalog`.

  Expected: `ModuleNotFoundError: toy3d`.
- [ ] **Fix:** the YAML ported from the snapshot constants (`P` palette, `T` timeline into the
  scene, the builders' design tables), plus the models and the catalog.

### Task 3: Vendored three r170, the page skeleton, static fences (S12-7 static, S12-10 static)

**Files:**
- `src/toy3d/web/vendor/three-0.170.0/`: `build/three.module.js` + 16 addon files + `LICENSE` +
  `SHA256SUMS`, from the npm tarball (sha512 `FQK+LEpY…BhuQ==`, the tryout lockfile's);
- `src/toy3d/web/stage.html` (the seeded `Math.random`, verbatim; importmap to vendor);
- `src/toy3d/web/engine/*.js` (stubs exporting the API);
- tests: `tests/unit/toy3d/test_engine_source_fences.py`.

- [ ] **Red:**
  - `::test_vendored_three_matches_its_sums`;
  - `::test_engine_js_has_no_unseeded_time_or_text` (`Math.random(`, `Date`, `performance.now`,
    `requestAnimationFrame`, `fillText`, `strokeText`);
  - `::test_no_look_constants_in_engine_js` (`#rrggbb`, `rgb(`/`rgba(` literals,
    `toneMappingExposure =` with a number, and so on; allow-list: none in v0).

  Expected: the files are missing.
- [ ] **Fix:** vendor the files and write the stubs.

### Task 4: Runtime and runner, with a fake page (S12-8, S12-9, S12-13, S12-14 unit half)

**Files:** `src/toy3d/runtime.py`, `src/toy3d/render.py`; `pyproject.toml`
(`playwright==1.62.0`); tests: `tests/unit/toy3d/test_runner.py`, `tests/unit/toy3d/test_render.py`.

- **Interfaces:**
  - `runtime.Page` protocol: `init(bank_json, w, h, mode)`, `info()`, `apply_state(spec)`,
    `render_state(spec) -> bytes`;
  - `runtime.open_page(w, h, mode) -> ContextManager[Page]` (real); tests inject a fake;
  - `runtime.check_renderer(info, platform) -> str` raises `Toy3DRenderError`;
  - `render.render_clip(scene, bank, out, duration, w, h, *, page_factory=None) -> Path`;
  - `render.cache_key(scene, bank, duration, w, h, renderer) -> str`.
- [ ] **Red:**
  - `test_backend_allow_list_refuses_swiftshader_vulkan_and_unknown`;
  - `test_missing_build_names_the_install_command`;
  - `test_page_error_reaches_the_render_error`;
  - `test_uniform_frame_fails_loud` (nothing encoded, no stamp);
  - `test_cache_key_covers_every_input`: scene, `Bank.model_dump_json`, engine JS, three sums,
    build, renderer, size, fps; each changes the key;
  - `test_cache_hit_launches_no_browser`;
  - `test_clip_has_round_duration_times_fps_frames` (fake page, real ffmpeg);
  - `test_a_dying_encode_leaves_no_file_and_no_stamp`.

  Expected: `ModuleNotFoundError: toy3d.runtime`.
- [ ] **Fix:**
  - `chromium.launch(args=[f"--use-angle={metal|gl-egl}", "--ignore-gpu-blocklist"])` on the
    pinned build;
  - the renderer string via `WEBGL_debug_renderer_info`;
  - allow-list: darwin `/ANGLE Metal Renderer/`; linux `/OpenGL ES/` and not
    `/Vulkan|SwiftShader|llvmpipe/`;
  - `page.route("http://toy3d.local/**")` serves `web/` and the bank JSON;
  - the frame loop decodes base64, and `PIL.Image.getextrema()` uniform → error;
  - ffmpeg `image2pipe` PNG at `COMPOSE_FPS` → libx264 → `.part.mp4` → rename, then the stamp.

### Task 5: The acting resolver (S12-11 Layer A, S12-23 Python half)

**Files:** `src/toy3d/acting.py`; test `tests/unit/toy3d/test_acting.py`,
`tests/unit/toy3d/test_state_symbolic.py`.

- `resolve(scene, bank, t) -> FrameSpec` (a JSON-able dict):
  - `camera {pos, target, fov, up}`;
  - `actors[name] {build, root {pos, yaw}, channels {..}, face, flags, extras}`;
  - `door {angle}`, `puffs {door_k, smoke_k}`;
  - `bulb {level, dead, out, anchor, drift}`;
  - `bubble {visible, pop, bang, speaker, bob, icons}`;
  - `laptop {lines, cursor}`;
  - `frame`.
- [ ] **Red:** each accent type and the walk, look-at, door, bulb, bubble, laptop and camera
  programs, pinned at sample times to the snapshot's formulas (values computed in the test from
  the snapshot's expressions, written as literals). Plus:
  - `test_state_symbolic.py::test_worked_scene_frame_specs_match_golden` (Layer A, exact JSON,
    the key times);
  - `::test_every_toy3d_capability_changes_the_frame_spec` (the Ruling 3 read-or-rejected fence,
    Python half).

  Expected: `ModuleNotFoundError: toy3d.acting`.
- [ ] **Fix:** port `poseTim`, `poseLion`, `poseGuo`, `poseDoor`, `poseBulb`, `posePuffs`,
  `poseBubble`, `drawScreen`'s counters and `camAt` into the bank-driven model (P2-R1…R6).

### Task 6: The engine port (page) and Layer B (S12-7 runtime, S12-11 Layer B, S12-23 JS half)

**Files:** `src/toy3d/web/engine/`:
- `core.js` (`V3`, `lerp`, `seg`, the eases, `mulberry32`, `canvasTex`, `noiseNormal`, materials
  from the style);
- `room.js` (scene.js 278–550: the room, hall, window, painting, clock, shelf, plants, rug, desk,
  laptop screen, chair);
- `tim.js` (552–716, H3 only);
- `lioness.js` (731–801);
- `guoguo.js` (803–1069: fur hook, loft, trace painting, seated + standing);
- `faces.js` (185–276);
- `props.js` (1071–1137: bubble, bulb, puffs);
- `post.js` (1139–1226, look A only);
- `world.js` (assembly + `applyState`);
- `page.js` (`init` / `applyState` / `renderState` / `info`).

Tests: `tests/integration/toy3d/test_state_goldens.py`, `tests/integration/toy3d/test_style_wiring.py`.
- [ ] **Red:**
  - `test_apply_state_creates_no_webgl_context_in_state_mode`;
  - `test_applied_world_matrices_match_goldens` (≤ 1e-6, named nodes);
  - `test_every_toy3d_capability_is_rendered` (each TOY3D table entry changes `applyState`);
  - `test_style_values_change_pixels` (exposure, a palette colour, bloom strength → pixels
    differ);
  - `test_a_bad_bank_colour_fails_init_loudly`.

  Expected: integration failures (the page stubs).
- [ ] **Fix:** port verbatim, with constants read from the bank JSON.

### Task 7: The worked scene and parity (S12-18, D1, D3)

> **As built:** the snapshot driver is `tests/toy3d_snapshot.py` (a test helper with a `__main__`:
> `refs`, `nodes`, `random`), not `tools/toy3d/render_tryout_refs.py`. The repo has no `tools/`,
> and the Layer B goldens (task 6) and the denoise noise position need the same driver. The
> engine renders the 7 frames pixel-identical to the snapshot (max diff 0), so the tolerance is
> set by margin over a driver's drift, and the sensitivity table in `PROVENANCE.md` bounds it.

**Files:** `assets/toy3d/scenes/001-beat2-break-in.yaml`; `tests/fixtures/toy3d/tryout_ref/`
(7 PNGs at 960×540 + `PROVENANCE.md`); `tools/toy3d/render_tryout_refs.py` (renders the
snapshot's own code, hash-checked); tests: `tests/integration/toy3d/test_parity_tryout.py`;
evidence: `tmp/toy3d-v0/parity/`.

- **Key times:**
  - 0.6 (typing, the orbit);
  - 2.4 (the door spring, the walk, GuoGuo's hop);
  - 3.3 (the point, the bubble, the jab);
  - 4.0 (the shock, the turn, the push, the sweat);
  - 5.3 (the bulb flicker, the zoom);
  - 7.0 (the pull-back).

  The design view is `guo` at 0.714, standing.
- [ ] **Red:** `test_worked_scene_matches_the_frozen_tryout` at each key time, and
  `test_standing_guoguo_matches_the_design_view`. Expected: the scene file is missing.
- [ ] **Fix:**
  - the scene YAML (the `T` timeline as contract beats; the flicker table as 13 instant prop
    beats);
  - the references rendered and hash-checked;
  - the tolerance calibrated: the Mac run-to-run floor (0), then the measured port differences,
    with a margin; recorded in `PROVENANCE.md`;
  - a one-time mp4 tie check (`tmp/toy3d-v0/parity/mp4_tie.txt`);
  - the side-by-side sheets.

### Task 8: Layer C goldens and the tolerant policy (S12-12)

**Files:** `tests/golden_policy.py` (`assert_close_to_golden(img, path, *, mean, p999, max_frac)`,
hub-canonical minting); `tests/fixtures/toy3d/goldens/` (key frames + the cast model sheet +
`PROVENANCE.md`); `src/toy3d/sheet.py` (the model sheet); tests:
`tests/integration/toy3d/test_goldens.py`, `tests/unit/test_golden_policy.py`.

- [ ] **Red:**
  - the tolerant helper's unit tests (`UPDATE_GOLDENS` off-linux raises; thresholds);
  - the sensitivity set must fail the compare:
    - an expression decal swapped on a close-up;
    - a 5° shoulder rotation;
    - one material colour;
    - GuoGuo hidden;
    - fur shells halved.
- [ ] **Fix:**
  - the helper;
  - goldens minted on the hub (isolated clone);
  - the noise floor measured as the maximum of hub run-to-run and Mac against hub;
  - the thresholds set above the floor and below the sensitivity set.

### Task 9: Compose, validator, CLI and doctor; fps and cadence (S12-14 to S12-17, A1)

**Files:** `src/pipeline/composer/toon.py`, `src/toon/cli.py`, `src/pipeline/cli_doctor.py`;
tests in `tests/unit/test_composer_toon.py`, `tests/unit/toy3d/test_cli.py`,
`tests/unit/test_cli_doctor.py`, `tests/integration/toy3d/{test_render,test_cadence}.py`.

- [ ] **Red:**
  - `render_scene` with a toy3d visual calls `toy3d.render.render_clip` (fake), never the 2.5D
    engine;
  - a failure becomes `SceneRenderError` with the fix;
  - the validator fails a bad toy3d name (exit 2);
  - `toon validate` on a toy3d file loads the toy3d catalog. M10 must go red: a spy on
    `load_catalog`;
  - `check_toy3d` passes here and fails, with the install hint, when the build is missing;
  - `test_toy3d_fps_matches_compose_concat`;
  - integration: the clip frame count at two narration lengths; cadence through concat.
- [ ] **Fix:** wire the dispatch; the doctor check (build present, renderer allow-listed, a
  one-frame non-blank smoke).

### Task 10: The two-machine demo (S12-19)

> **As built (2026-10-13):** PASS on both machines; the evidence is `tmp/toy3d-v0/compose-smoke/`
> (`smoke.py`, per-take JSON and logs, subtitle frames, the held-shot frames). The harness would not
> let the builder write `REPORT.md`, so the summary went to the lead in the Phase 2 report. A finding
> outside toy3d: the same prerecorded WAV narrates 0.08–0.10 s longer on the hub (TtsStage's MP3
> transcode), so the two machines' cuts differ by about 3 frames per scene.

Two prerecorded `say` takes, through the prerecorded path, compose s1 (a synthetic `clip`) and
s2 (the worked scene, inline or referenced) on the Mac and in an isolated hub clone. Checks:
- toy3d frames = round(narration × 30);
- `blackdetect` is clean;
- subtitles are kept;
- cadence;
- ms per frame on each machine.

Evidence goes in `tmp/toy3d-v0/compose-smoke/REPORT.md`.

### Task 11: Gates on both machines and the review (S12-21, A3)

> **As built:** the two reviews' findings are folded in red-first: the Phase 1 review (A3, range
> `5d0f9b3..045e47e`: 0 Critical, 3 Important, 7 Minor) and a fresh review of Phase 2 (range
> `8d78e95..94de1da`: 0 Critical, 5 Important, 10 Minor). The findings and their dispositions
> are under "Code reviews" below, and their ledger rows close the red-run ledger. The gates on
> both machines ran after the last fix.

The full suite, ruff and mypy on the Mac and in the hub clone. Fold in the Phase 1 code review's
findings (A3) red-first. Run a separate review of the Phase 2 diff. Then the ledger and the
report to the lead.

## Red-run ledger

| Row | Test | Task | Expected red | Observed red | Red commit | Fix commit |
|-----|------|------|--------------|--------------|------------|------------|
| S12-22 | `test_symbolic_timeline.py` (inout, since) + conformance (inout on both engines) | 1 | literal error; no `since` | `KeyError: 'inout'` (EASES); `shots.0.beats.0.ease: Input should be 'linear', 'smooth', 'out' or 'back'` on both engines; `ImportError: cannot import name 'DoorAt'` | `61426df` | `de1fddc` |
| S12-6/20/23a, S12-5 A2 | `tests/unit/toy3d/test_bank.py`, conformance with the real catalog | 2 | `ModuleNotFoundError: toy3d` | 9 × `ModuleNotFoundError: No module named 'toy3d'`; 2 × `SceneError: engine: toy3d has no bank yet`; the conformance suite errors at collection on the same | `c4af74a` | `ca14f7f` |
| S12-7s/10s | `test_engine_source_fences.py` | 3 | files missing | `FileNotFoundError` on `vendor/three-0.170.0/SHA256SUMS` and `stage.html`; `AssertionError: no engine modules` (×2) | `5e00b45` | `1216373` |
| S12-8/9/13/14u | `test_runner.py`, `test_render.py` | 4 | `ModuleNotFoundError: toy3d.runtime` | 20 × `ModuleNotFoundError: No module named 'toy3d.runtime'`, 5 × `… 'toy3d.render'`, 4 × `ImportError: cannot import name 'runtime'/'render' from 'toy3d'` (29 failed) | `57ccfe8` | `7b77d99` |
| S12-11A/23p | `test_acting.py` (every frame against `snapshot_oracle.py`, a verbatim transcription of the snapshot's animation), `test_state_symbolic.py` | 5 | `ModuleNotFoundError: toy3d.acting` | 62 × `ModuleNotFoundError: No module named 'toy3d.acting'` (53 failed, 9 errors); `test_every_toy3d_capability_has_a_probe` passes (a table fence, mutation-checked) | `f35942e` | (this commit) |
| S12-7r/11B/23j | `test_state_goldens.py` (node matrices minted from the snapshot's own scene graph: `tests/toy3d_snapshot.py nodes`), `test_style_wiring.py` | 6 | page stubs | against the committed stub page: 41 errors (`Toy3DRenderError: toy3d page: init failed: toy3d engine: not built yet`), 3 failed (the loud-init messages). Order deviation, recorded honestly: the engine port was written before these tests, then the red was observed against the committed stub | `dcf432d` | `1149dad` |
| S12-18 | `test_parity_tryout.py` | 7 | scene file missing (the scene landed in task 2: the references are what's missing) | 7 × `FileNotFoundError: …/tryout_ref/PROVENANCE.md`; `AssertionError: assert [] == ['guo@0.714.png', …]` | `6a16ac4` | `b81254a` |
| S12-12 | `test_goldens.py`, `test_golden_policy.py`, `tests/unit/toy3d/test_sheet.py` | 8 | helper missing | 10 × `ImportError: cannot import name 'assert_close_to_golden'`; `ModuleNotFoundError: No module named 'toy3d.sheet'`; `test_goldens.py` errors at collection on the same import | `cde5f97` | `971d526` (helper, sheet), `c94bf64` (the hub-minted goldens) |
| S12-14…17 | `test_composer_toon.py`, `test_storyboard_validator.py`, `test_cli_doctor.py`, `tests/unit/toy3d/test_cli.py` (unit; the integration half follows) | 9 | no toy3d dispatch | 15 failed: 7 × `AttributeError: … no attribute 'check_toy3d'`; the scene id `001-beat2-break-in` → `assets/toon/scenes/…: scene file not found` (composer, validator, CLI); `DID NOT RAISE SceneError` (an id in both libraries). `test_pipeline_validate_fails_a_bad_toy3d_name_with_exit_two` passes: the Phase 1 seam already routes the validator (a pin) | `b651c18` | `6088dd5` |

| A3-I2 | `test_state_at_folds_a_face_before_a_later_move` | 11 | a pin | passes on arrival; the "faces fold last" mutant goes red | `2b840ae` | (a pin) |
| A3-I3 | `test_a_cast_name_is_checked_as_its_character`, `test_a_pose_beat_is_checked_as_its_character` | 11 | pins | pass on arrival; both reviewer mutants and both `_check` cast-name mutants go red | `2b840ae` | (pins) |
| A3-m2 | `test_the_contract_and_the_symbolic_timeline_load_no_2d_engine_code` (subprocess), `test_toy3d_no_longer_depends_on_the_2d_bank` | 11 | modules loaded | `toon.bank`, `toon.timeline`, `numpy`, … in `sys.modules`; `bank.py` / `timeline.py` in toy3d's sources | `2b840ae` | `4b86fec` |
| A3-m1 | `test_the_2d_renderer_refuses_a_toy3d_scene`; `test_an_engine_without_a_renderer_is_a_scene_render_error` | 11 | no guard | `DID NOT RAISE ToonRenderError`; the compose guard pin passes (now reachable) | `2b840ae` | `4b86fec` |
| A3-m4 | `test_an_unknown_character_is_one_problem_not_a_cascade`, `test_a_field_no_engine_reads_on_that_verb_says_which_verb_does` | 11 | messages | 3 problems for one unknown character; "toy3d doesn't render bob on any beat (toon2d does)" | `2b840ae` | `4b86fec` |
| A3-m3, m6, m7 | `test_toy3d_takes_the_place_fields_its_table_lists`, `test_the_render_field_lists_are_the_models_optional_render_fields`, `test_the_spec_is_plain_json_for_any_scene` | 11 | pins | pass on arrival; each mutant red | `2b840ae` | (pins) |
| A3-I1, P2-M4 | `test_the_key_follows_the_python_that_shapes_each_frame`, `test_the_key_covers_the_vendored_files_not_just_their_sums` | 11 | key unchanged | `assert eased != base` failed; the patched vendor file left the key the same | `2b840ae` | `4b86fec` |
| A3-m5 | `test_toy3d_validation_and_rendering_read_one_bank` | 11 | two loads | `assert len(loads) == 1` (2) | `2b840ae` | `4b86fec` |
| P2-I1 (face), P2-I3 | `test_an_expression_beat_during_a_blend_switches_the_face_when_it_starts`, `test_no_state_leaks_between_frames` | 11 | the reviewer's repros | `tim_shock` at 1.25 (want `tim_neutral`); the chair at t 3.0 rotated (m00 0.732) after t 1.0 | `24db608` | `61686c1` |
| P2-I3 | `test_a_still_matches_the_same_frame_of_a_clip` | 11 | a pin | passes on arrival (after `61686c1`); without the seat reset it goes red | `21ed9ae` | (a pin) |
| P2-I4, I5, M1, M2, M3 | `test_a_page_console_error_fails_the_next_call`, `test_start_…`, `tests/integration/toy3d/test_runtime.py`, `test_a_background_only_frame_fails_loud`, `test_a_render_never_touches_another_renders_partial_file`, `test_toy3d_stills_refuse_*` | 11 | silent | 6 unit failures (no raise; no `runtime.start`; the stale partial overwritten); 3 integration (no `CALL_TIMEOUT`; no raise after `loseContext`; none after `console.error`) | `b136382` | `57ad1d8` |
| P2-I1 (pose), I2, M5, M6, M7, M10 | `test_an_authored_pose_during_a_blend_takes_over_smoothly`, `test_a_face_turns_the_short_way`, `tests/unit/toy3d/test_seats.py`, `test_bank.py` (decal, programs) | 11 | unchecked | 11 failed: a 0.79 rad pop; −196° instead of +164°; 6 × `DID NOT RAISE SceneError` / no validator error; 3 bank cases | `5d3d7c0` | `0d8c0e9` |
| P2-M9 | `test_toy3d_render_never_loads_the_2d_renderer`, `test_a_toy3d_render_failure_is_an_error_line_not_a_traceback` | 11 | cairo; traceback | exit 1 on the blocked `toon.render` import; the `PlaywrightError` escaped | `21ed9ae` | `b85d3d3` |

### Mutation evidence

Each guard below was removed (one at a time, `scratchpad/mutate.py`) and its pinning test went red.

| Task | Guard removed | Pinning test | Result |
|------|---------------|--------------|--------|
| 4 | the uniform-frame check | `test_uniform_frame_fails_loud` | red |
| 4 | the renderer, or the web sources, in the cache key | `test_cache_key_covers_every_input` | red (both) |
| 4 | the stamp drop before rendering | `test_a_dying_page_leaves_no_file_and_no_stamp` | red |
| 4 | the `.part.mp4` cleanup | `test_a_dying_encode_leaves_no_file_and_no_stamp` | red (after the fake ffmpeg was made to leave a half-written file; it was green before) |
| 4 | `check_renderer` in the runner | `test_a_disallowed_backend_renders_nothing` | red |
| 4 | the record-keyed cache check, or the record write | `test_cache_hit_launches_no_browser` | red (both) |
| 4 | the build-present check; the build-version check | `test_missing_build_…`; `test_a_different_browser_build_is_refused` | red (both) |
| 4 | the Vulkan/SwiftShader/llvmpipe refusal | `test_backend_allow_list_refuses_…` | red |
| 4 | the early page-error exit in `wait_ready` | `test_a_page_that_fails_to_load_is_reported_at_once_…` | red (was a 600 s timeout; the stub now fails fast) |
| 4 | submodule and enclosing-package imports in `import_closure` | `test_import_closure_follows_submodule_imports` | red (both; was green before that test) |
| 4 | `exclude={"root"}` in the key | `test_the_bank_root_is_not_in_the_key` | red |
| 5 | full-pose reset of the cheated turns (`TURNS`) | `test_tim_matches_the_snapshot_every_frame` | red |
| 5 | `until_next: stop` on loops; on osc accents (the fade) | `test_tim_…`; `test_guoguo_…` (every frame) | red (both) |
| 5 | the expression-only beat (`to` = current pose) | `test_lioness_…` (the 4.61 blink would replay the jabs) | red |
| 5 | the decal switch against the inherited expression | `test_tim_…` (the shock face) | red |
| 5 | the flag threshold 0.05 → 0.5 | `test_a_flag_turns_on_once_its_pose_is_five_percent_in` | red (was green on the worked scene's frames; that test was added) |
| 5 | the walk's place in the fold | `test_lioness_…` | red |
| 5 | the aim, the hop speed, the flipper whip | `test_guoguo_…` | red (each) |
| 5 | the door spring; the dust of the latest open | `test_door_…`; `test_a_closing_door_…` | red (both) |
| 5 | the bulb level rounding; flicker; blink | `test_bulb_…`; `test_flicker_…`; `test_blink_…` | red (each) |
| 5 | `loop: false`; standing GuoGuo's whole-body turn | `test_loop_false_…`; `test_standing_guoguo_…` | red (both) |
| 5 | the laptop's typing stop | `test_the_laptop_stops_filling_when_the_typist_stops` | red (was green: the worked scene caps at 11 lines before the stop matters; that test was added) |
| 5 | a camera tween starting early | `test_camera_…` | red |
| 5 | a capability probe removed | `test_every_toy3d_capability_has_a_probe` | red |
| 6 | the face decal swap; the fur push; the seated root's local position; the bubble billboard; the finger flag | `test_applied_world_matrices_match_goldens` (the snapshot's own node matrices) | red (each) |
| 6 | the laptop screen drawing (`drawScreen(4, true)`) | the same, once it pinned the screen's pixels (FNV over a copy of the canvas) | red (was green: Layer B had no screen; added) |
| 6 | the unread-key fence; the palette colour check | `test_a_bad_bank_value_fails_init_loudly` | red (both) |
| 6 | the exposure read; the bloom strength read | `test_style_values_change_pixels` | red (the bloom mutant fails init: the unread fence catches it first) |
| 6 | a WebGL renderer in state mode | `test_apply_state_creates_no_webgl_context_in_state_mode` | red |
| 7 | the denoise noise position (skip 11060 → 11061); bloom 0.42 → 0.45 | `test_worked_scene_matches_the_frozen_tryout` | red (both) |
| 8 | the frame limits widened (p99.9 30, >8 0.003, tile 30) | `test_a_five_degree_shoulder_fails` | red |
| 8 | the tile metric dropped; UPDATE_GOLDENS allowed off the hub | `test_golden_policy.py` | red (both) |
| 9 | the clip length from the scene instead of the narration | `test_clip_frame_count_equals_narration` (integration; a pin: green on arrival) | red |
| 9 | toy3d at 24 fps | `test_toy3d_cadence_survives_compose_concat_normalisation` (a pin); `test_toy3d_fps_matches_compose_concat` | red (both) |
| 9 | **M10**: the CLI's `_load` on the 2.5D bank | `test_toon_validate_loads_a_toy3d_scene_against_the_toy3d_catalog` | red |
| 9 | the composer's toy3d branch; the CLI's toy3d branch | `test_dispatches_by_scene_engine`; `tests/unit/toy3d/test_cli.py` | red (both) |
| 9 | the both-libraries refusal | `test_a_scene_id_in_both_libraries_is_refused` | red |
| 9 | doctor's renderer check; its frame check; its renderer record | `test_check_toy3d_*` | red (each) |
| 11 | each of the review fixes above | its test | red (each, under the hardened mutation script: no stale bytecode); two redundant pairs stay green alone: the context check before and after a render, and the error check before and after a call |

## Code reviews

**Phase 1, A3** (a fresh reviewer, `5d0f9b3..045e47e`; relayed by the lead). It found 0 Critical,
3 Important and 7 Minor, and confirmed the seam: `state_at` was identical at base and branch over a
1,500-scene seeded fuzz. Every finding is fixed or pinned (ledger rows A3-*):
- I1 the cache key;
- I2 the face-before-move pin;
- I3 per-character scoping;
- m1 the 2.5D renderer's engine guard;
- m2 `toon/beats.py`;
- m3 toy3d's `loop`;
- m4 the messages;
- m5 one bank;
- m6 the render-field fence;
- m7 plain-JSON specs.

**Phase 2** (a fresh reviewer, `8d78e95..94de1da`). It found 0 Critical, 5 Important and 10
Minor, and checked fine: the route handler, the lifecycle, the stamp order, the cache key's
coverage, the GTAO reseed, and that compose never falls back.

| Finding | Disposition |
|---|---|
| I1 an overlapping pose pops; an expression mid-blend ignored | `to_set` / `expr_set` (P2-R1b): `61686c1`, `0d8c0e9` |
| I2 seated actors and seat spots fail silently | refused at load, validator included (P2-R10): `0d8c0e9` |
| I3 the chair leaks between frames | the seat rests every frame, plus a still = clip-frame pin: `61686c1`, `21ed9ae` |
| I4 CLI stills skip the backend gate | `runtime.start` for every caller, plus a frame check per still: `57ad1d8` |
| I5 shader errors and a lost context are silent | console errors, `onShaderError`, a context check: `57ad1d8` |
| M1 the per-call timeout is a no-op | the watchdog: `57ad1d8` |
| M2 the blank check misses an empty world | an edge check: `57ad1d8` |
| M3 a fixed temp name | `mkstemp`: `57ad1d8` |
| M4 the key misses vendor edits | vendored files hashed: `4b86fec` |
| M5 no angle wrap | the short way: `0d8c0e9` |
| M6 a partial pose as a placement | refused (P2-R10): `0d8c0e9` |
| M7 a null decal keeps the previous face | a face with decals needs one per expression: `0d8c0e9` |
| M8 the typist by placement spot | moot under P2-R10: the typist can't leave the seat, and nobody moves into it |
| M9 the CLI imports cairo for toy3d; tracebacks | `b85d3d3` |
| M10 program channels unchecked | checked at bank load: `0d8c0e9` |

Left as is, by name:
- A door closing during its spring snaps by at most 0.05 rad.
- The "standing in a seat" refusal can't be reached with the v0 bank: Tim has only sit poses.
