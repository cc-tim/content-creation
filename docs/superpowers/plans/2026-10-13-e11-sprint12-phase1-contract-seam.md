# E11 Sprint 12, Phase 1 — Scene-Contract Seam Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One scene contract checks a scene against *any* engine's catalog (names + what that
engine renders), with an `engine:` key and an engine-neutral symbolic timeline. The 2.5D engine is
rebuilt on that timeline, and scene 001 renders byte-identical.

**Architecture:**
- New engine-neutral module `src/toon/catalog.py`:
  - the `SceneCatalog` protocol;
  - a plain `Catalog` dataclass that implements it (toy3d's bank builds one in Phase 2);
  - per-engine `Capabilities` tables (`TOON2D`, `TOY3D`) and the engine list;
  - `load_catalog(engine)`, which compose, the validator and the CLI use to dispatch.
- The 2.5D `Bank` satisfies the protocol through a few adapter members (`capabilities`, `icons`,
  `spots`, `pose_class`, `expressions_of`, `prop_kind`). So `load_scene(data, bank)` keeps working
  everywhere, and `toon.scene` no longer imports `toon.bank` or the 2.5D kit.
- `toon.timeline.beats_at(scene, t, t_cam)` is the symbolic state: placements, an ordered tuple of
  started move/pose/face changes (name + eased k), door, prop values and flags, graphics with pop k,
  and the camera (preset, time since the cut, span). The 2.5D `state_at` folds it with exactly
  today's arithmetic, in exactly today's order.

**Tech Stack:** Python 3.13 (uv), pydantic 2.12, pytest, PyYAML.

**Spec:** `docs/superpowers/specs/2026-10-13-toy3d-engine-v0-design.md` §3–§4 (Phase 1). Test plan
rows **S12-1 … S12-5** in `.agent-memory/engineering-manager/test-plan.md`; roadmap E11 / Sprint 12.

**Base and where to build:** worktree `.worktrees/e11-sprint12`, branch `feat/e11-sprint12`, from
master `5d0f9b3` (Sprint 11 merged as `55670c9`). Base gates on the Mac: 1604 passed, 62 skipped;
ruff and mypy clean (163 files).

**Tim's answers (2026-10-13), recorded in spec §12 by Task 6:**
1. The scope includes the lioness, so the worked scene is the locked r7-3d clip itself.
2. GuoGuo freezes into the bank only when Tim approves the v7 tryout render. Build everything else
   first, and ask before porting GuoGuo (Phase 2).
3. OK to add Python `playwright` (pinned), vendor three.js r170 (MIT), and use the three-layer
   tolerant golden policy for GPU renders (Phase 2).

**Rulings on the spec's letter:**
1. **The protocol is satisfied structurally by the 2.5D `Bank`** (adapter members on the model)
   rather than by a wrapper object. Over 100 existing `load_scene(…, bank)` call sites (compose, the
   validator, the CLI, doctor, tests) stay unchanged, and the seam is still a protocol that any
   catalog meets (the toy3d one in tests now, its bank in Phase 2).
2. **Both engines' capability tables live in the contract (`toon/catalog.py`).** An engine-relative
   error must say which other engine renders the field ("toy3d doesn't render bob on a move beat
   (toon2d does)"). That needs both tables, and the contract must not import an engine package.
3. **The toy3d table is provisional for Phase 2 and errs narrow:**
   - all 8 verbs;
   - the 2.5D beat fields minus `bob` (the tryout's walk has its own step cycle);
   - prop kind `idea_bulb` only (on/b; to: b; flicker/blink/out);
   - show kind `bubble` only (the tryout's dirty-plates + "!" bubble);
   - place field `loop` (pose loops such as typing);
   - no `layer`, no fx, no `boil`.

   Phase 2 must render all of it. Widening the table later is additive; being too wide would be
   silent, which is never allowed.
4. **`boil` is engine-relative too.** It is the 2.5D line boil, so the table gains `scene_fields`.
5. **`Place.layer` and `Place.loop` become optional (None = split, on),** like the Sprint 11 beat
   fields. "Set" then means "not None", so a toy3d scene that writes `layer:` fails. Scene 001's
   cache key changes once (it serialises `null`); its frames don't.
6. **`beats_at` keeps play order.** Its changes are one ordered tuple (by time, then as listed).
   That lets the 2.5D fold repeat today's float operations exactly, overlapping blends and `face`
   (which aims at another actor's *current* position) included. The spec's per-actor
   "(from, to, k)" view is that tuple filtered by actor.
7. **The toy3d catalog in Phase 1 is a test fixture** with the 2.5D MINI's names and the `TOY3D`
   capabilities. `load_catalog("toy3d")` raises "toy3d has no bank yet" until Phase 2. So compose
   and the validator refuse a toy3d scene loudly. They never fall back to 2.5D.

## Global Constraints

- **Scene 001 byte-identical:** 41 evenly spaced frames at 960×540 (t = i·13/40), plus all 390
  compose frames at 320×180, must hash identical to the sprint base `5d0f9b3`. Baseline:
  `scratchpad/s001_base_5d0f9b3.txt`. Hub goldens 4/4 and parity ≤ 0.058 are confirmed at the
  checkpoint (isolated hub clone).
- **No churn:** `assets/toon/**` and `tests/fixtures/toon/**` unchanged; no golden re-mint.
- **Import fence:** `toon.scene` has no module-level import of `toon.bank`, `toon.kit*`,
  `toon.engine*`, `toon.render`, `toon.timeline`, or cairo.
- **Never silent:** a field the chosen engine doesn't render fails at load, naming the engine and
  the path.
- **Red first:** a test-only commit `test(toon): red — …`, then the fix commit. The ledger below
  records both.
- **Commits:** small `type(scope): message`; end with a blank line and
  `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`; `git add` explicit
  paths (never `tmp/`); no push, no merge.
- **Gates per task:**
  `uv run pytest tests/unit/toon tests/unit/test_composer_toon.py tests/director/test_storyboard_validator.py -q`.
  At the end: `uv run pytest -q`, `uv run ruff check src/ tests/`, `uv run mypy src/`.
- **Stop after Phase 1** and report to the lead for the EM checkpoint REVIEW.

## Review Focus

1. **A storyboard visual that references a toy3d scene file by `scene:`** must dispatch on the
   file's engine, not the default. Pinned in Task 2 (the reference case of
   `test_dispatches_by_scene_engine`).
2. **A toy3d scene that writes `layer: split` explicitly** (the 2.5D default value) still fails:
   setting it is the error, not the value. Pinned in Task 3.
3. **A move followed by a face in the same shot** (face aims at the mover's current spot): the
   2.5D fold must give today's yaw exactly. Pinned in Task 4
   (`test_state_at_matches_the_pre_split_fold_on_overlapping_beats`).
4. **An unknown `engine:` in an inline storyboard visual** fails at the review gate, listing the
   engines, not as a pydantic dump. Pinned in Task 2.
5. **A scene loaded against the other engine's catalog** fails with one clear engine-mismatch
   problem, not dozens of name errors. Pinned in Task 1.

---

### Task 1: The catalog seam and the `engine:` key (S12-1, S12-3 load side)

**Files:**
- Create: `src/toon/catalog.py`
- Create: `tests/unit/toon/test_contract_seam.py`, `tests/unit/toon/catalogs.py` (test catalogs)
- Modify:
  - `src/toon/scene.py` (imports, `ToonScene.engine`, `Place` optionals, `_check*` against the catalog);
  - `src/toon/bank.py` (protocol adapter members);
  - `src/toon/timeline.py` (`Place` optionals);
  - `tests/unit/toon/test_scene.py` and `tests/unit/toon/test_bank.py` (Sprint 11 fences now read
    `TOON2D.beat_fields` / `TOON2D.prop_kinds`; fix commit).

**Interfaces (produces):**
```python
# toon/catalog.py
ENGINES = ("toon2d", "toy3d"); DEFAULT_ENGINE = "toon2d"; PROP_BEAT_FLAGS = ("flicker", "blink", "out")
class PropKind(NamedTuple): needs, draws, states, flags  # frozensets
@dataclass(frozen=True) class Capabilities: engine, verbs, beat_fields, prop_kinds, show_kinds,
                                            place_fields, fx_kinds, scene_fields
TOON2D: Capabilities; TOY3D: Capabilities; CAPABILITIES = {"toon2d": TOON2D, "toy3d": TOY3D}
class SceneCatalog(Protocol):
    capabilities: Capabilities (property); characters, sets, cameras, props, icons: Collection[str]
    def spots(set_name) -> Collection[str]; def pose_class(character, pose) -> str | None
    def expressions_of(character) -> Collection[str]; def prop_kind(prop) -> str
@dataclass(frozen=True) class Catalog  # implements SceneCatalog from plain names
def load_catalog(engine: str) -> SceneCatalog  # toon2d → the 2.5D bank; toy3d → Phase 2
```

- [ ] **Step 1: Failing tests.** `tests/unit/toon/catalogs.py`:

```python
"""Test catalogs. TOY3D_TEST stands in for the toy3d bank until Phase 2 builds it: the 2.5D
MINI's names with the toy3d engine's capabilities, so contract cases run unchanged on both."""
from toon.catalog import TOY3D, Catalog

TOY3D_TEST = Catalog(
    capabilities=TOY3D,
    characters=frozenset({"tim", "lioness"}),
    set_spots={"office": frozenset({"desk_seat", "doorway", "doorway_out"})},
    cameras=frozenset({"front34_push", "two_shot", "close_push"}),
    prop_items={"idea_bulb": "idea_bulb"},
    icons=frozenset({"dishes", "bang"}),
    poses={"tim": {"sit_typing": "sit", "sit_shock": "sit", "stand_point": "stand"},
           "lioness": {"stand_point": "stand"}},
    expressions={"tim": frozenset({"neutral", "focused", "shocked"}),
                 "lioness": frozenset({"neutral", "angry"})},
)
```

`tests/unit/toon/test_contract_seam.py`:

```python
import ast
import copy
from pathlib import Path

import pytest

import toon
from tests.unit.toon.catalogs import TOY3D_TEST
from tests.unit.toon.test_scene import BANK, MINI
from toon.scene import SceneError, load_scene


def test_load_scene_takes_any_catalog():
    from toon.catalog import SceneCatalog

    assert isinstance(BANK, SceneCatalog) and isinstance(TOY3D_TEST, SceneCatalog)
    assert load_scene(copy.deepcopy(MINI), BANK).engine == "toon2d"              # the 2.5D bank adapts
    assert load_scene({**copy.deepcopy(MINI), "engine": "toy3d"}, TOY3D_TEST).engine == "toy3d"
    bad = {**copy.deepcopy(MINI), "engine": "toy3d"}
    bad["shots"][0]["place"]["tim"]["pose"] = "moonwalk"                         # names come from it
    with pytest.raises(SceneError, match=r"shots\[0\]\.place\.tim\.pose: unknown pose 'moonwalk'"):
        load_scene(bad, TOY3D_TEST)


def test_a_scene_against_the_other_engines_catalog_fails_once():
    with pytest.raises(SceneError) as e:
        load_scene({**copy.deepcopy(MINI), "engine": "toy3d"}, BANK)
    assert e.value.problems == ["engine: a toy3d scene, but this is the toon2d catalog"]


def test_engine_key_defaults_and_unknown_fails():
    from typing import get_args

    from toon.catalog import ENGINES
    from toon.scene import ToonScene

    assert get_args(ToonScene.model_fields["engine"].annotation) == ENGINES
    assert load_scene(copy.deepcopy(MINI), BANK).engine == "toon2d"
    with pytest.raises(SceneError, match=r"engine: Input should be 'toon2d' or 'toy3d'"):
        load_scene({**copy.deepcopy(MINI), "engine": "toy4d"}, BANK)


_FENCED = ("toon.bank", "toon.kit", "toon.engine", "toon.render", "toon.timeline", "cairo", "cairocffi")


def test_scene_module_does_not_import_the_2d_bank():
    tree = ast.parse((Path(toon.__file__).parent / "scene.py").read_text())
    names = [a.name for n in tree.body if isinstance(n, ast.Import) for a in n.names]
    names += [n.module or "" for n in tree.body if isinstance(n, ast.ImportFrom)]
    assert not [m for m in names if m.startswith(_FENCED)]
```

- [ ] **Step 2: Verify red** (`ModuleNotFoundError: No module named 'toon.catalog'`; the AST
  fence finds `toon.bank`, `toon.kit.icons`). Commit
  `test(toon): red — load_scene only takes the 2.5D bank; no engine key (S12-1, S12-3)`.
- [ ] **Step 3: Implement** `toon/catalog.py` (the interface above; `TOON2D` = today's
  `BEAT_FIELDS`/`PROP_KINDS`/`SHOW_KINDS` with place fields {layer, loop}, fx {glow},
  scene fields {boil}; `TOY3D` per Ruling 3). `Catalog` fields: `capabilities`, `characters`,
  `set_spots`, `cameras`, `prop_items` (name → kind), `icons`, `poses` (character → pose →
  class), `expressions` (character → names); properties `sets`, `props`; methods per protocol.
  `load_catalog`:

```python
def load_catalog(engine: str) -> SceneCatalog:
    """The catalog a scene of `engine` is checked against (each engine's bank, adapted)."""
    if engine == "toon2d":
        from toon.bank import load_bank
        return load_bank()
    if engine == "toy3d":
        raise SceneError(["engine: toy3d has no bank yet (E11 Sprint 12 phase 2 builds it)"])
    raise SceneError([f"engine: unknown engine {engine!r} (engines: {', '.join(ENGINES)})"])
```
  (`SceneError` stays in `toon.scene`; `load_catalog` imports it inside the function, because
  `toon.scene` imports `toon.catalog` at module level.) Bank adapter members on `toon.bank.Bank`:
  `capabilities` → `TOON2D`; `icons` → `frozenset(ICONS)` (lazy import of `toon.kit.icons`);
  `spots(s)` → `self.sets[s].spots`; `pose_class(c, p)` → `self.poses[p].hip` or None;
  `expressions_of(c)` → `self.expressions`; `prop_kind(p)` → `self.props[p].kind`.
  `toon.scene`:
  - `ToonScene.engine: Literal["toon2d", "toy3d"] = "toon2d"`;
  - `Place.layer: Literal["split", "low"] | None = None`, `Place.loop: bool | None = None`;
  - `load_scene(data, catalog, …)`; the engine mismatch fails first, then every name check goes
    through the protocol;
  - prop kinds, flags and beat fields come from `catalog.capabilities`;
  - `scenes_root()` imports `default_root` inside the function.

  The 2.5D fold reads `pl.layer or "split"`, `True if pl.loop is None else pl.loop`.
- [ ] **Step 4: Green** (sprint gate; scene-001 hashes identical). Commit
  `feat(toon): scenes load against any SceneCatalog; engine: key; the 2.5D bank adapts (S12-1, S12-3)`.

### Task 2: Compose and the validator dispatch by `engine` (S12-3)

**Files:** Modify `src/pipeline/composer/toon.py`, `src/pipeline/director/storyboard_validator.py`,
`src/toon/cli.py` (`_load`); Test `tests/unit/test_composer_toon.py`.

- [ ] **Step 1: Failing test**

```python
def test_dispatches_by_scene_engine(tmp_path, monkeypatch):
    # S12-3: the scene's engine picks the catalog and the renderer; a toy3d scene never falls
    # back to the 2.5D engine, and an unknown engine fails listing the engines.
    import copy

    import yaml

    from tests.unit.toon.test_scene import MINI

    rendered = []

    def fake_clip(scene, bank, out, duration, width, height, workers=None):
        rendered.append(scene.engine)
        Path(out).write_bytes(b"x")
        return Path(out)

    monkeypatch.setattr("toon.render.render_clip", fake_clip)
    base.render_scene({"id": "s1", "narration": "One.", "visual": {"type": "toon", "scene": "001-lioness-dishes"}},
                      13.0, "16:9", tmp_path)
    assert rendered == ["toon2d"]
    toy = {"type": "toon", **copy.deepcopy(MINI), "engine": "toy3d"}
    with pytest.raises(SceneRenderError, match=r"toy3d has no bank yet"):
        base.render_scene({"id": "s2", "narration": "One.", "visual": toy}, 4.0, "16:9", tmp_path)
    ref = tmp_path / "toy.yaml"                                    # a reference: the file's engine
    ref.write_text(yaml.safe_dump({**copy.deepcopy(MINI), "engine": "toy3d"}))
    with pytest.raises(SceneRenderError, match=r"toy3d has no bank yet"):
        base.render_scene({"id": "s3", "narration": "One.", "visual": {"type": "toon", "scene": str(ref)}},
                          4.0, "16:9", tmp_path)
    assert rendered == ["toon2d"]                                  # never a 2.5D fallback
    with pytest.raises(SceneRenderError, match=r"unknown engine 'toy4d' \(engines: toon2d, toy3d\)"):
        base.render_scene({"id": "s4", "visual": {**toy, "engine": "toy4d"}}, 4.0, "16:9", tmp_path)
    (issue,) = validation_errors(validate_storyboard(Storyboard(scenes=[
        Scene(id="s5", section="content", narration="One.", narration_est_sec=4.0, visual={**toy, "engine": "toy4d"})]),
        tmp_path))
    assert "unknown engine 'toy4d' (engines: toon2d, toy3d)" in issue.issue
```

- [ ] **Step 2: Verify red** (the toy3d scene loads against the 2.5D bank: an engine mismatch, not
  "toy3d has no bank yet"; the unknown engine surfaces as a pydantic literal error). Commit
  `test(toon): red — compose and the validator check every toon scene against the 2.5D bank (S12-3)`.
- [ ] **Step 3: Implement.** Add `scene_engine(data) -> str` in `toon.scene`: `data.get("engine",
  DEFAULT_ENGINE)`, an unknown value raising the listing error. The adapter, the validator and the
  CLI `_load` call `load_catalog(scene_engine(data))`. Compose renders a `toon2d` scene with
  `toon.render.render_clip`. Any other engine reaches no renderer in Phase 1, because
  `load_catalog("toy3d")` already raised.
- [ ] **Step 4: Green; commit**
  `feat(toon): compose, the validator and the CLI pick the catalog by the scene's engine (S12-3)`.

### Task 3: Engine-relative "means what it renders" (S12-2)

**Files:** Modify `src/toon/scene.py`; Test `tests/unit/toon/test_contract_seam.py`.

- [ ] **Step 1: Failing test**

```python
# What toy3d (v0) doesn't render but toon2d does: each must fail on toy3d, naming the engine.
_TOY3D_GAPS = [
    ({"boil": "still"}, None, r"^boil: toy3d doesn't render boil \(toon2d does\)"),
    (None, {"place": {"tim": {"spot": "desk_seat", "pose": "sit_typing", "layer": "split"}}},
     r"shots\[0\]\.place\.tim\.layer: toy3d doesn't render layer \(toon2d does\)"),
    (None, {"fx": [{"glow": {"at": [0, 2, 0], "radius": 1, "color": "warm", "alpha": 0.3}}]},
     r"shots\[0\]\.fx\[0\]\.glow: toy3d doesn't render glow fx \(toon2d does\)"),
    (None, {"beats": [{"at": 1.0, "show": {"anger": "tim"}}]},
     r"shots\[0\]\.beats\[0\]\.show\.anger: toy3d doesn't render anger shows \(toon2d does\)"),
    (None, {"place": {"tim": {"spot": "desk_seat", "pose": "sit_typing"}},
            "beats": [{"at": 1.0, "move": "tim", "to": "doorway", "over": 1.0, "bob": 0.1}]},
     r"shots\[0\]\.beats\[0\]\.bob: toy3d doesn't render bob on a move beat \(toon2d does\)"),
]


@pytest.mark.parametrize("scene_change, shot_change, path", _TOY3D_GAPS)
def test_field_the_engine_does_not_render_fails_naming_the_engine(scene_change, shot_change, path):
    d = {**copy.deepcopy(MINI), **(scene_change or {})}
    d["shots"][0].update(copy.deepcopy(shot_change or {}))
    load_scene(copy.deepcopy(d), BANK)                                    # toon2d renders it
    with pytest.raises(SceneError, match=path):
        load_scene({**d, "engine": "toy3d"}, TOY3D_TEST)


@pytest.mark.parametrize("engine", ["toon2d", "toy3d"])
def test_a_verb_or_prop_kind_the_engine_lacks_fails_naming_the_engine(engine):
    # Both v0 engines render every verb, so a narrowed copy proves the check per engine.
    import dataclasses

    from toon.catalog import CAPABILITIES

    caps = CAPABILITIES[engine]
    narrow = dataclasses.replace(caps, verbs=caps.verbs - {"hide"},
                                 prop_kinds={k: v for k, v in caps.prop_kinds.items() if k != "idea_bulb"})
    catalog = dataclasses.replace(TOY3D_TEST, capabilities=narrow)
    d = {**copy.deepcopy(MINI), "engine": engine}
    d["shots"][0]["beats"] = [{"at": 0.5, "show": {"bubble": ["dishes"], "from": "tim"}},
                              {"at": 1.0, "hide": "bubble:tim"}]
    with pytest.raises(SceneError) as e:
        load_scene(d, catalog)
    assert f"shots[0].beats[1].hide: {engine} doesn't render hide beats" in str(e.value)
    assert f"shots[0].props.idea.kind: {engine} doesn't render idea_bulb props" in str(e.value)
```

- [ ] **Step 2: Verify red** (toy3d loads `boil`, `layer`, `fx`, `anger`, `bob`; `DID NOT RAISE`).
  Commit `test(toon): red — a field toy3d doesn't render loads silently (S12-2)`.
- [ ] **Step 3: Implement** in `_check`:
  - scene fields (`boil` when not None);
  - place fields (`layer`, `loop` when not None);
  - fx kinds;
  - verbs (an unrendered verb skips that beat's other checks);
  - show kinds;
  - prop kinds (`catalog.prop_kind(item)` not in `caps.prop_kinds`).

  Each fails as `"{path}: {engine} doesn't render {what}"` plus `" ({others} does)"` when another
  engine in `CAPABILITIES` does. `_unread` names the engine when another engine reads the field
  on that verb.
- [ ] **Step 4: Green; commit**
  `feat(toon): a field the scene's engine doesn't render fails, naming the engine (S12-2)`.

### Task 4: Symbolic timeline; the 2.5D `state_at` folds it (S12-4)

**Files:** Modify `src/toon/timeline.py`; Test `tests/unit/toon/test_symbolic_timeline.py`.

**Interfaces (produces):**
```python
beats_at(scene: ToonScene, t: float, t_cam: float | None = None) -> SymbolicState
SymbolicState(shot, set, t_draw, door, camera: CameraAt(preset, since, span),
              actors: tuple[ActorAt(name, character, spot, pose, expr, layer, loop)],
              changes: tuple[Change(verb, who, to, expr, k, bob)],   # play order
              props: tuple[PropAt(name, item, on, held_by, b, count, mode, smoke, blink, flicker)],
              graphics: tuple[GraphicAt(key, show, k)], fx: tuple[Fx, ...])
```

- [ ] **Step 1: Failing tests**

```python
import copy
import inspect

import pytest

from tests.unit.toon.catalogs import TOY3D_TEST
from tests.unit.toon.test_scene import MINI
from tests.unit.toon.test_timeline import BANK, BASE
from toon.scene import load_scene


def test_beats_at_is_symbolic_and_engine_neutral():
    from toon.timeline import beats_at

    assert list(inspect.signature(beats_at).parameters) == ["scene", "t", "t_cam"]   # no bank
    s = load_scene(copy.deepcopy(BASE), BANK)
    sym = beats_at(s, 1.5)
    assert (sym.shot, sym.set, sym.door) == (0, "office", pytest.approx(0.5))
    assert [(c.verb, c.who, c.to, c.expr) for c in sym.changes] == [
        ("move", "lioness", "doorway", None), ("pose", "tim", "sit_shock", "shocked")]
    assert [c.k for c in sym.changes] == pytest.approx([0.5, 0.5])
    assert (sym.camera.preset, sym.camera.since, sym.camera.span) == ("two_shot", 1.5, 4.0)
    assert [(g.key, g.k) for g in sym.graphics] == [("bubble:lioness", 1.0)]
    (idea,) = sym.props
    assert (idea.name, idea.b, idea.flicker) == ("idea", 1.0, None)
    assert beats_at(s, 1.5) == sym                                                 # pure
    toy = load_scene({**copy.deepcopy(MINI), "engine": "toy3d"}, TOY3D_TEST)        # any engine's scene
    assert beats_at(toy, 0.0).actors[0].pose == "sit_typing"


def test_state_at_is_built_on_beats_at(monkeypatch):
    import dataclasses

    from toon import timeline

    s = load_scene(copy.deepcopy(BASE), BANK)
    real = timeline.beats_at
    monkeypatch.setattr(timeline, "beats_at", lambda *a, **k: dataclasses.replace(real(*a, **k), door=0.25))
    assert timeline.state_at(s, BANK, 1.5).door == 0.25


def test_state_at_matches_the_pre_split_fold_on_overlapping_beats():
    # Review Focus 3: a move then a face (aimed at the mover's *current* spot) and two
    # overlapping poses fold exactly as the pre-split loop did (values pinned at 5d0f9b3).
    from toon.timeline import state_at

    d = copy.deepcopy(BASE)
    d["shots"][0]["beats"] += [{"at": 1.2, "face": "tim", "to": "lioness", "over": 0.5},
                               {"at": 1.4, "pose": "tim", "to": "sit_typing", "over": 0.5, "ease": "linear"}]
    fs = state_at(load_scene(d, BANK), BANK, 1.6)
    assert (fs.chars["tim"].yaw, fs.chars["tim"].pose.lean) == (PINNED_YAW, PINNED_LEAN)
```
  (`PINNED_YAW`, `PINNED_LEAN`: exact floats measured at the base `5d0f9b3`, written into the
  test as literals.)

- [ ] **Step 2: Verify red** (`ImportError: cannot import name 'beats_at'`; the monkeypatch
  test fails on the missing attribute; the overlapping-beats pin is *green* at red time: it guards
  the refactor). Commit
  `test(toon): red — no engine-neutral symbolic timeline; state_at owns the beat loop (S12-4)`.
- [ ] **Step 3: Implement** `beats_at`: today's beat loop with every bank lookup removed. It keeps
  - names and k for changes;
  - door, prop values and flags, graphics and the camera folded symbolically.

  `state_at` builds the 2.5D placements from `sym.actors` and folds `sym.changes` with the same
  `lerp`/`mix` calls in the same order. It applies flicker by drawing index, blink, loops and the
  camera from `sym`. No other line of the 2.5D path changes.
- [ ] **Step 4: Green, then the byte-identity check:** all 431 hashes equal the base. Commit
  `feat(toon): beats_at, the engine-neutral symbolic timeline; 2.5D state_at folds it (S12-4)`.

### Task 5: Contract conformance across both engines (S12-5)

**Files:** Create `tests/unit/toon/test_contract_conformance.py`.

Each Sprint 11 contract case runs against `BANK` (toon2d) and `TOY3D_TEST` (toy3d) with the same
data (+ `engine:`), and must fail with the **same problems** where the field is engine-neutral:
- S11-1 timing fields (show `ease`, hide `over`/`ease`, camera `over`/`ease`, prop `over`/`ease`
  without `to`, `ease` without `over`);
- S11-5 (a bubble over a visible bubble key, a double hide);
- S11-7 / S11-12 / S11-13 (anchored scenes resolve to the same times; out-of-order fails alike);
- S11-8 (`SceneError.source`);
- S11-9 (`NeedsNarration`);
- S11-14 (`drift_warnings`);
- S11-17 (negative `over`, `blink.over: 0`, `over: 0` show k = 1 via `beats_at`).

Engine-relative cases run per engine from `catalog.capabilities`:
- S11-2: each table field is read (it changes `beats_at`) or rejected;
- S11-3: prop flags outside a kind's flags fail.

The suite is a guard; behaviour is already in place, so it lands as one green commit
`test(toon): contract conformance suite across toon2d and toy3d catalogs (S12-5)`.
Its mutation evidence goes in the ledger: drop a case's check in `scene.py`, and both engines'
params go red.

### Task 6: Spec record, gates, checkpoint

- [ ] Spec §12 "Tim's answers (2026-10-13)" and the status line; plan ledger; README (the
  `engine:` key in the toon table).
- [ ] Gates: `uv run pytest -q`, ruff, mypy; the 431-hash identity check; the isolated hub pass
  (goldens 4/4 with `UPDATE_GOLDENS` unset, parity ≤ 0.058, no fixture churn).
- [ ] Stop and report to the lead (HEAD, plan path, ledger, Mac gates, scene 001 byte-identical).

## Red-run ledger

| Row | Test | Task | Expected red | Observed red | Red commit | Fix commit |
|-----|------|------|--------------|--------------|------------|------------|
| S12-1 | `test_contract_seam.py::test_load_scene_takes_any_catalog`, `::test_scene_module_does_not_import_the_2d_bank`, `::test_a_scene_against_the_other_engines_catalog_fails_once` | 1 | `ModuleNotFoundError: toon.catalog`; fence lists `toon.bank`, `toon.kit.icons` | collection `ModuleNotFoundError: No module named 'toon.catalog'`; the fence's AST scan of `scene.py` finds `['toon.bank', 'toon.kit.icons']` | `dd4b79a` | `3d7b245` |
| S12-3 (load) | `test_contract_seam.py::test_engine_key_defaults_and_unknown_fails` | 1 | `ModuleNotFoundError: toon.catalog` | collection `ModuleNotFoundError: No module named 'toon.catalog'` | `dd4b79a` | `3d7b245` |
| S12-3 (dispatch) | `test_composer_toon.py::test_dispatches_by_scene_engine` | 2 | engine mismatch / pydantic literal error instead of the dispatch errors | `SceneRenderError: s2: toon: storyboard scene s2: engine: a toy3d scene, but this is the toon2d catalog` (compose checked the toy3d scene against the 2.5D bank) | `96a8359` | `883fcfb` |
| S12-2 | `test_contract_seam.py::test_field_the_engine_does_not_render_fails_naming_the_engine` + `::test_a_verb_or_prop_kind_the_engine_lacks_fails_naming_the_engine` | 3 | `DID NOT RAISE` | `DID NOT RAISE` for toy3d boil, layer, glow fx, anger show, and both narrowed-table cases (an unrendered verb or prop kind); bob fails but says only `not valid with a move beat` (no engine named) | `aa6458e` | `1aa6967` |
| S12-4 | `test_symbolic_timeline.py` | 4 | `ImportError: cannot import name 'beats_at'` | `ImportError: cannot import name 'beats_at' from 'toon.timeline'`; `AttributeError: module 'toon.timeline' has no attribute 'beats_at'`; the overlapping-beats pin is green (it guards the refactor; values measured at `5d0f9b3`) | `19e5335` | `0350583` |
| S12-5 | `test_contract_conformance.py` (28 cases: 17 engine-neutral cases compared problem for problem, the catalogs' own name lists aside; anchors at 3 durations; anchor failures, NeedsNarration and drift; the source; `over: 0` via `beats_at`; per-engine S11-2 and S11-3 fences) | 5 | green (guard); mutation evidence | green, 28 passed. Mutations: M-a (the ease-without-over rule only on toon2d) → `[S11-1 ease without over]` red; M-b (a show over a visible key allowed) → `[S11-5 a bubble over a visible bubble]` red; both reverted | n/a (guard) | |
