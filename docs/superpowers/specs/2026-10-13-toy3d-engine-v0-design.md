# Toy3D engine v0: the locked own-show look as a pipeline visual (E11, Sprint 12)

**Status:** proposed by the EM (SPRINT, 2026-10-13); **greenlit by Tim on 2026-10-13**, with his
answers to the open questions in §12. Phase 1 (the contract seam) is built on `feat/e11-sprint12`. Roadmap: `docs/ROADMAP.md` → E11 and Sprint 12. Test rows: `.agent-memory/engineering-manager/test-plan.md`
→ E11, S12-1…S12-21.

## 1. Problem

Tim locked the own-show style on 2026-10-13: a **3D toy, in the smooth Animal Crossing look** (r7-3d
look A; `docs/own-show.md` → "Style exploration", next step 4b). The only renderer for that look is a
throwaway tryout (`output/projects/20260724-hybrid-ai-agent-controller/style-tryouts/r7-3d/`): one
1,441-line `scene.js` that hard-codes the cast, the set, the timing and the camera. The pipeline's
`toon` visual renders only the 2.5D cairo engine (E9), which is now the backup style's engine.

v0 makes the locked look a deterministic pipeline visual: bank items as data from Tim's picks, scenes
as files in the **same scene contract** as E9 (Sprint 11), rendered headless, composed like any
other scene, and guarded by goldens on both machines.

**Non-goals:** EP1 scenes or story (`own-show.md` step 6); new bank items beyond the frozen tryout
picks; fixing the tryout's known weak points (primitive lioness, sine-driven motion, hands vs the big
head); camera verbs in scene files; IK; sculpted or glTF parts; draft or speed profiles; a Style
Manifest element or a dashboard surface (E4/E6, named and deferred).

## 2. Evidence (EM probes, 2026-10-13, scratch only)

| Probe | Result |
|---|---|
| Pinned browser on both machines | Chrome for Testing 151.0.7922.34 (playwright build `chromium-1234`, full and headless shell) is installed on the Mac and the hub |
| Mac WebGL2 backends | `--use-angle=metal` → "ANGLE Metal Renderer: Apple M3 Pro". Default flags → SwiftShader (LLVM backend) |
| Hub WebGL2 backends | `--use-angle=gl-egl` → "NVIDIA GeForce GTX 1050 … OpenGL ES 3.2" (driver 580.178). `--use-angle=vulkan` → the NVIDIA device, but **every frame comes back all black (0,0,0)** with no error. Default flags → SwiftShader (Subzero backend) |
| Speed, the tryout at 1920×1080, 30 frames, PNG through CDP | Mac Metal ≈ 85 ms a frame (≈ 12 fps). Hub GL-EGL ≈ 188 ms a frame (≈ 5 fps). Mac SwiftShader: no frame within 10 min |
| Determinism, same frame twice (t = 4.6 s) | Mac Metal: byte-identical, and identical across system Chrome 155 and CfT 151. Hub GL-EGL: not byte-identical; at most 1 level on a few pixels |
| Mac Metal vs hub GL-EGL, same frame | mean abs diff 0.14/255; 11% of pixels differ by ≥ 1; 0.05% by > 8; max 129. The > 8 pixels sit on silhouette edges (glasses, hair rim, eyes) and GuoGuo's fur tips. Perceptually identical side by side |

What follows from it: the hub is **not** SwiftShader-only; byte-exact goldens can't hold across
machines (or even run to run on the hub); and two silent hazards exist, a SwiftShader fallback and
the Vulkan black frames, which the runner must refuse loudly.

## 3. Architecture

```
scene YAML (engine: toy3d) ──► toon.scene  (one contract: schema, anchors, splitter, loud load errors)
                                 │  validates against SceneCatalog (names + engine capabilities)
                                 ▼
                        toon.timeline.beats_at(scene, t)   ← engine-neutral symbolic state
                         │                         │
            toon2d (E9, cairo, backup)       toy3d (E11)
            state_at → frame                 toy3d.render: Python → pinned Chrome (playwright)
                                               → stage.html + vendored three r170 + engine JS
                                               → renderState(json) → PNG → ffmpeg @ COMPOSE_FPS
```

| Component | Where | Role |
|---|---|---|
| Contract seam | `src/toon/scene.py`, `src/toon/timeline.py` | `SceneCatalog` protocol, per-engine capability tables, `engine:` key, symbolic timeline |
| Toy3D bank | `assets/toy3d/bank/**` + `src/toy3d/bank.py` | YAML picks with provenance → typed Pydantic `Toy3DBank` → its catalog |
| Runner | `src/toy3d/render.py` | browser launch, backend allow-list, frame loop, blank-frame guard, cache, atomic mp4 |
| Engine | `src/toy3d/web/` | `stage.html`, engine/cast/set modules ported from the tryout, `vendor/three-0.170.0/` (MIT, with `SHA256SUMS`) |
| Adapter | `src/pipeline/composer/toon.py` | dispatch by `engine`; same duration fence; `SceneRenderError` only |
| Tooling | `pipeline toon validate\|render` (engine read from the file), `pipeline doctor` toy3d check | — |

**Precedents to copy:** `src/toon` (bank/scene/render/cli layout, provenance, cache, goldens with a
`PROVENANCE.md`), `composer/toon.py` (adapter), and the tryout (`scene.js` builders; `render.mjs`
PNG pipe into ffmpeg with `.part` + rename; `stage.html` seeded `Math.random`).

## 4. The contract seam (Phase 1, red first, 2.5D byte-identical)

1. **`SceneCatalog` protocol.** `load_scene(data, catalog, …)` takes any catalog: characters, sets
   with spots, cameras, poses (with a pose class, the `hip` rule), expressions, props with kind,
   icon names, and **capabilities**: the verbs, the per-verb beat fields (Sprint 11's `BEAT_FIELDS`),
   prop kinds (`PROP_KINDS`), show kinds, place fields (`layer`) and fx kinds the engine renders.
   The 2.5D `Bank` gets an adapter. `toon.scene` stops importing `toon.bank` and the 2.5D kit at
   module level (an import fence test).
2. **Engine-relative "means what it renders".** A field the chosen engine doesn't render fails at
   load, naming the engine (`layer:` and `fx: glow` are 2.5D-only today; toy3d v0 rejects whatever
   it doesn't draw). v0 may be partial; it may never be silent.
3. **`engine:`** is an optional scene key, default `toon2d`, so every existing scene and storyboard
   is unchanged. An unknown engine fails, listing the engines.
4. **Symbolic timeline.** `beats_at(scene, t)` gives, per actor: spot or move (from, to, k), pose
   (from, to, eased k), expression, facing; per prop: values and flags; shows with their pop k; the
   door; and the camera as (preset, time since the cut). The 2.5D `state_at` is rebuilt on top of it.
   **Scene 001 stays byte-identical** (41 of 41 frames; hub goldens 4/4, no churn; parity ≤ 0.058).
   If that can't hold cheaply, stop at the checkpoint rather than re-mint backup goldens.

Phase 1 ends in an **EM checkpoint REVIEW** (rows S12-1…S12-5) before Phase 2 builds on it.

## 5. Toy3D bank v0 (Phase 2)

Only Tim's frozen picks, as in the locked clip: **Tim** (H3 textured crop, round wire glasses, navy
hoodie), **GuoGuo** (the r7-3d build from Tim's hand-puppet photos, **frozen by Tim at greenlight**),
the **lioness**, and the **office + hall** set with the door, desk, laptop (the tryout's wordless code
bars), bulb, plant and bookshelf. Every item carries `picked:` provenance. Layout:

```
assets/toy3d/bank/
  style.yaml            # look A: tone map, exposure, GTAO, shadows, bloom, env, fog: read by the engine
  characters/<name>.yaml  # builder id + params + palette
  poses/<character>.yaml  # named joint rotations (deg) + class (sit/stand) + optional loop (typing, sway)
  expressions/<character>.yaml  # named face decals: drawn by code (canvas paths, no text)
  sets/<name>.yaml      # builder + spots + lights + props in place
  cameras/<name>.yaml   # presets as keyframe paths (pos, target, fov, eases): own-show "camera feels"
  props/<name>.yaml
```

- Geometry is **code-built** (the tryout's builders, now parameterised by bank data). The part
  schema reserves `gltf:` (a frozen GLB with sha256 and provenance) for sculpted parts. It's built
  when the first pick needs it (E11 item 6), not in v0.
- Python validates the bank and sends the page a **resolved JSON** of it. JS never reads YAML.
- **No look constants in engine code.** The palette and post settings live in the bank. This closes,
  by design, the 2.5D `style.yaml` residual (E9 2b) for the locked look.
- The worked scene: `assets/toy3d/scenes/001-beat2-break-in.yaml`, the r7-3d look-A beat (8.0 s,
  `engine: toy3d`), using the contract's verbs (door, move, pose, face, prop, show, camera).

## 6. Runner

- Python `playwright` (uv-locked) launches the pinned CfT build. There's no Node on the render path
  (the hub's Node is nvm-only and isn't on a systemd `PATH`).
- **Backend allow-list:** darwin `--use-angle=metal`; linux `--use-angle=gl-egl`. At start the
  runner reads `UNMASKED_RENDERER_WEBGL` and **refuses** SwiftShader, Vulkan or anything unlisted,
  naming the string and the fix.
- **Blank-frame guard:** a uniform frame (the Vulkan symptom) fails the render; it is never encoded
  or cached.
- **Page API:**
  - `init(bank, {width, height, mode})`: `mode: "state"` creates no WebGL context;
  - `renderState(state)` → PNG;
  - `applyState(state)` → named world matrices, visibility, decal ids and the camera;
  - `info()` → three, engine and renderer versions.
- **Clip:** frames = round(duration × `COMPOSE_FPS`). Frames go into ffmpeg through a pipe, and the
  mp4 is written as `.part` then renamed.
- **Cache key:** the scene; the **Bank object** (`model_dump_json`, not the files, per the 2.5D
  lesson); the engine JS; the vendored three hash; the browser build; the renderer string;
  width × height; fps. A cache hit doesn't launch the browser.
- **Determinism fences:** engine JS has no unseeded `Math.random`, no `Date`, no `performance.now`,
  no `requestAnimationFrame`, and no `fillText`/`strokeText` (wordless). A static test enforces it.

## 7. Compose integration

The `toon` visual type stays; `composer/toon.py` dispatches on the scene's `engine`. Everything else is
the E9 adapter contract:
- the clip lasts exactly as long as the narration, holding the last shot or cutting with a warning;
- failures raise `SceneRenderError` with a `suggested_fix`;
- the validator branch checks toy3d names at the review gate;
- toon is not in `_TEXT_VISUALS`.

There is **no engine fallback**: a toy3d failure never quietly renders on the 2.5D engine. The fps
guard and cadence tests follow standards anatomy item 9.

## 8. Goldens: three layers

| Layer | What | Where it runs | Compare |
|---|---|---|---|
| A | symbolic timeline state (`beats_at`) for the worked scene | default suite, both machines | exact |
| B | applied scene graph (`applyState`, no GL) at key times | `--integration`, both machines | ≤ 1e-6 |
| C | pixels: key frames + a Tim/GuoGuo/lioness model sheet, 960×540 | `--integration`, both machines | tolerance |

Layer C is **hub-canonical**: it is minted on the hub only (`UPDATE_GOLDENS` off-linux stays an
error). Unlike E8's byte-exact policy, it is **compared on the Mac too**, through a tolerant helper in
`tests/golden_policy.py`. Thresholds are calibrated in the build:
- **Noise floor:** the maximum of hub run-to-run and Mac against hub on every golden. The probe
  gives a starting point: mean ≤ 0.14/255, and 0.05% of pixels > 8.
- **Sensitivity set**, which must go red: an expression-decal swap on a close-up, a 5° shoulder
  rotation, one material colour shift, GuoGuo hidden, and the fur shell count halved.

`PROVENANCE.md` records the browser build, both renderer strings, the driver, the noise floor and
the thresholds. Layer B catches the small logic regressions a pixel tolerance could miss.

## 9. Acceptance vehicles

- **Parity with the locked look (gating).** Freeze reference frames from the r7-3d snapshot at
  greenlight (Mac Metal, ≥ 6 key times) into `tests/fixtures/toy3d/tryout_ref/`. The worked scene
  must match them within the parity tolerance on the Mac (same backend) and the cross-machine
  tolerance on the hub. A side-by-side sheet goes to Tim, and **Tim confirms it still meets his
  bar**.
- **Real-scene demo (gating, standards anatomy 6).** A throwaway two-scene smoke project (a `clip` +
  the toy3d scene, prerecorded narration in two takes of different length) composes on **both
  machines** with:
  - toy3d clip frames = narration × 30;
  - `blackdetect` clean;
  - subtitles kept;
  - clean cadence;
  - ms per frame recorded on each machine.
  Evidence goes in `tmp/toy3d-v0/compose-smoke/`.

## 10. Risks

| Risk | Handling |
|---|---|
| Headless shell vs full CfT behave differently with the GPU flags | Pin whichever build works on both; doctor proves it on both machines |
| An NVIDIA driver or browser bump shifts pixels | Tolerance + `PROVENANCE.md`; a bump = re-mint on the hub with Tim's eyeball, never silently |
| The tolerance hides a small regression | Layer B exact + the Layer C sensitivity set, mutation-checked by the EM |
| The symbolic-timeline split churns the backup engine | Byte-identity gate at the Phase 1 checkpoint |
| Fur dominates frame time and cross-machine variance | Measure with and without fur; LOD later (E11 item 7) |
| Python playwright version ↔ browser build coupling | Pin both; doctor names `playwright install` when the build is missing |

## 11. Deferred (E11 items)

- camera verbs in scene files (2);
- bank fill from EP1's needs, including the laptop ✓/✗ screens (3);
- contact sheets (4);
- IK and secondary motion (5);
- sculpted or glTF parts and lighting polish (6);
- speed and draft profiles with fur LOD (7);
- 3D explainer graphics (8);
- the contract-level items re-homed from E9 item 3 (9);
- the Style Manifest element (E4) and the dashboard surface (E6).

## 12. Open questions: Tim's answers (2026-10-13)

The roadmap's "Needs Tim before the build" list, answered at greenlight (passed on by the coordinator
when the build started):

1. **Scope includes the lioness.** The worked scene is the locked r7-3d clip itself, so parity
   (S12-18) covers all of it.
2. **GuoGuo freezes into the bank only when Tim approves the v7 tryout render.** Another agent is
   still tuning him in `r7-3d/`. Everything else is built first, and the builder asks before
   porting GuoGuo (Phase 2).
3. **Accepted:** the Python `playwright` dependency (pinned), three.js r170 vendored into git
   (MIT), and the three-layer tolerant golden policy for GPU renders (§8).

Phase 1 build rulings (protocol satisfied structurally by the 2.5D `Bank`, both capability tables
in `toon/catalog.py`, the narrow provisional toy3d table, `boil` and `Place.layer`/`loop` as
engine-relative optional fields, play-ordered changes in `beats_at`) are in the plan:
`docs/superpowers/plans/2026-10-13-e11-sprint12-phase1-contract-seam.md`, "Rulings".
