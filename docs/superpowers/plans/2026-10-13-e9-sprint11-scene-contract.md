# E9 Sprint 11 — Toon Scene Contract (v0 residuals) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A toon scene file either means exactly what it renders or fails at load, naming the
file it came from. Its shot cuts follow the narration when the narration's length changes.

**Architecture:**
- `src/toon/scene.py` stays the one owner of the scene contract. One per-verb table
  (`BEAT_FIELDS`) says which optional beat fields the timeline reads; `PROP_KINDS` gains the beat
  flags each prop kind honours. Every other field fails at load.
- Graphic keys become `<kind>:<id or icon>` for cards. One time-ordered pass over shows and hides
  (`_check_graphics`) replaces the old "shown anywhere" dict.
- `split_sentences` attaches closing quotes to the left and skips abbreviations.
  `sentence_starts` stays the single seam every anchor resolves through.
- `SceneError(problems, source)` prefixes every problem with its source. `read_scene` returns a
  `SceneData` mapping that remembers its file; `scene_data_from_visual(visual, origin)` builds the
  storyboard source. `Storyboard.path` (set by `load`/`save`, never serialised) lets the validator
  name the storyboard file.
- `Shot.at` takes `{sentence: n, plus: s}`. `_resolve_anchors` resolves shots first, checks the
  order, then resolves beats relative to their shot. `load_scene` records the authored duration
  and each shot's authored start in pydantic private attributes (never serialised, so never in
  the cache key), which `drift_warnings` and `toon validate` read.
- Render workers get the caller's `Bank` as JSON instead of reloading it from disk.

**Tech Stack:** Python 3.13 (uv venv), pydantic 2.12, PyYAML, typer, pytest, cairocffi, ffmpeg.

**Spec:** `docs/superpowers/specs/2026-09-27-toon-bank-v0-design.md` **§11** (and §5, which §11
amends). Test plan rows **S11-1 … S11-16** in `.agent-memory/engineering-manager/test-plan.md`.
Roadmap: `docs/ROADMAP.md`, Sprint 11 / E9 item 2.

**Base and where to build:** worktree `.worktrees/e9-sprint11`, branch `feat/e9-sprint11`, from
master `a2e9b55` plus the EM's sprint-definition commit `d1d4ca2`.

**Tim's decisions (2026-10-13, recorded in spec §11.5 by Task 10):**
1. Hold the style-dependent items: laptop ✓/✗ screen art, `style.yaml` line/palette wiring,
   pose/prop contact sheets. They are not built here.
2. 2f shot timing: sentence anchors (`at: {sentence: n, plus: s}`), loud failure when shots fall
   out of order, drift warning. Word-level timing stays E9 item 3.
3. zh-TW quote rule: a 。 inside 「」 ends a sentence, and the closing 」 stays with it.
   `他說：「我走了。」然後離開。` gives `他說：「我走了。」` + `然後離開。`.

**Rulings on the spec's letter** (the capability is unchanged):
1. **`ease` without `over` fails too.** §11.2 a's table says door/move/pose/face read `ease`. The
   timeline only reads it through `_progress`, where a missing or zero `over` makes `k = 1` and
   every ease maps 1 → 1, so `ease` alone is silently ignored. Rule (a) ("every field set on a
   beat must be read") therefore rejects it: "ease: does nothing without over:".
2. **A second `hide` of an already-hidden key fails.** It is a no-op beat, the same class of
   silent field as (a). The spec names only the show collision; this falls out of the same
   time-ordered pass.
3. **`none:` beside `layers:` fails, like the per-layer keys.** With `none: true` the layers are
   silently dropped; with `none: false` it is a no-op. Only `layers` and `bun` are read there.
4. **"One-letter word" excludes the pronoun "I".** "Neither did I. We left." is more common in
   narration than an initial "I." (I. M. Pei). The spec's examples (U.S., J. K., e.g., a.m.) are
   all covered.
5. **Closers include ASCII `"` and `'` plus 】》〉] besides the spec's 」 』 ” ） ) ’.** A straight
   quote right after a terminator is a closer in practice (`She said "Stop." Then…`); without it
   that sentence would start with `"`, which S11-7's "no sentence starts with a closer" forbids.
6. **The drift warning is its own function, `drift_warnings`, not part of `scene_warnings`.**
   compose logs `scene_warnings` as `toon.scene.cut`; drift gets `toon.scene.drift`. The
   validator and `toon validate` report both. Two existing validator tests that count warnings
   on 001 at 8.0 s of narration now see two (cut + drift: 13.0 s authored vs 8.0 s); they are
   updated in Task 7's fix commit.
7. **Shot order is checked once, after anchors resolve,** in `_resolve_anchors` (moved from
   `_check`), so a misordered scene fails with the order problems alone rather than also with
   bogus "outside the shot" windows.

## Global Constraints

- **Scene 001 unchanged** (S11-15): its frames must be byte-identical to master's; hub goldens
  4/4 with `UPDATE_GOLDENS` unset and no fixture churn; parity worst ≤ 0.058. Its clip cache key
  changes once (over/ease serialise as `null`); that is expected.
- **Non-goal fence:** `assets/toon/scenes/` holds only `001-lioness-dishes.yaml`; the bank gains
  no item. Anchored test scenes are built in test code from scene 001 (never under `assets/`).
- **Wordless:** a card's `id:` is a slug (`^[a-z][a-z0-9_]*$`) and is never drawn.
- **Zero runtime:** sentence anchors move cuts inside the narration; the duration = narration
  fence is untouched. No uniform stretch of seconds-timed beats.
- **Held, not built:** laptop ✓/✗ screens, `style.yaml` line/palette wiring, pose/prop contact
  sheets.
- **Red first:** each behaviour change lands as a test-only commit
  `test(toon): red — …`, then `fix(toon): …` / `feat(toon): …`. The ledger below records both.
- **Commits:** small `type(scope): message`; end with a blank line and
  `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`; `git add` explicit
  paths only (never `tmp/`); no push, no merge.
- **Gates:** `uv run pytest tests/unit/toon tests/unit/test_composer_toon.py tests/director/test_storyboard_validator.py -q`
  per task; at the end `uv run pytest -q`, `uv run ruff check src/ tests/`, `uv run mypy src/`.

## Review Focus

1. **Straight ASCII quotes after a terminator** (`She said "Stop." Then she left.`): two
   sentences, the `"` stays with the first. Pinned in Task 4's cases.
2. **A much faster narration on an anchored scene** (9.0 s against 001's authored 13.0 s): the
   scene loads (no false out-of-order), cuts land on the sentence starts, and the cut warning
   fires for the beats past 9.0 s. Pinned in Task 6,
   `test_shot_sentence_anchor_follows_the_narration`.
3. **A storyboard saved under a locale name** (`storyboard_zh-TW.json`): `pipeline validate`'s
   issue names that file, not `storyboard.json`. Pinned in Task 5,
   `test_render_error_and_validator_name_the_scene_source`.
4. **The same card `id:` in two different shots**: keys are per shot, so it loads. Pinned in
   Task 3, `test_two_cards_one_icon_with_ids_both_show`.
5. **A beat anchor whose `plus:` pushes it past its shot's end**: fails "outside the shot" with
   the beat path. Pinned in Task 6, `test_shot_anchors_resolving_out_of_order_fail_loudly`.

---

### Task 1: No silently ignored beat field (S11-1, S11-2, S11-3, S11-10; 2e camera check)

**Files:**
- Modify: `src/toon/scene.py` (constants, `Beat`, `_check_beat`, `_check_prop_use`, `scene_warnings`)
- Modify: `src/toon/timeline.py` (`_progress`, `move` bob, `show` pop)
- Test: `tests/unit/toon/test_scene.py`, `tests/unit/toon/test_bank.py`

**Interfaces:**
- Produces: `scene.BEAT_FIELDS: dict[str, frozenset[str]]`, `scene.BEAT_OPTIONAL: tuple[str, ...]`,
  `scene.PROP_BEAT_FLAGS`, `PROP_KINDS[kind]` = 4-tuple `(needs, draws, states, flags)`.
  `Beat.over: float | None`, `Beat.ease: Ease | None`, `Beat.bob: float | None` (None = not given).

- [ ] **Step 1: Write the failing tests** (append to `tests/unit/toon/test_scene.py`; add
  `from toon.timeline import state_at` to its imports)

```python
# -- Sprint 11 (spec §11.2 a): every field set on a beat is read by the timeline, or rejected --

def _hide_after_show(**hide_fields):
    d = mini(**{"at": 0.5, "show": {"anger": "tim"}})
    d["shots"][0]["beats"].append({"at": 1.0, "hide": "anger:tim", **hide_fields})
    return d


@pytest.mark.parametrize("data, path", [
    (mini(**{"at": 1.0, "show": {"anger": "tim"}, "ease": "out"}), r"beats\[0\]\.ease: a show beat pops in"),
    (_hide_after_show(over=0.5), r"beats\[1\]\.over: a hide beat is instant"),
    (_hide_after_show(ease="linear"), r"beats\[1\]\.ease: a hide beat is instant"),
    (mini(**{"at": 1.0, "camera": "two_shot", "over": 0.5}), r"beats\[0\]\.over: a camera beat is a cut"),
    (mini(**{"at": 1.0, "camera": "two_shot", "ease": "out"}), r"beats\[0\]\.ease: a camera beat is a cut"),
    (mini(**{"at": 1.0, "prop": "idea", "flicker": True, "over": 0.5}),
     r"beats\[0\]\.over: a prop beat times only a to: change"),
    (mini(**{"at": 1.0, "prop": "idea", "out": True, "ease": "linear"}),
     r"beats\[0\]\.ease: a prop beat times only a to: change"),
    (mini(**{"at": 1.0, "door": "open", "ease": "linear"}), r"beats\[0\]\.ease: does nothing without over"),
])
def test_beat_timing_fields_rejected_where_ignored(data, path):
    with pytest.raises(SceneError, match=path):
        load_scene(data, BANK)


# One shot where every verb has a valid base beat at 1.0 (a hide follows a show at 0.5).
_FENCE_SHOT = {"at": 0.0, "set": "office", "camera": "two_shot",
               "place": {"tim": {"spot": "desk_seat", "pose": "sit_typing"},
                         "lioness": {"spot": "doorway_out", "pose": "stand_point"}},
               "props": {"idea": {"kind": "idea_bulb", "on": "tim", "b": 1.0}}}
_FENCE_BASE = {
    "door": {"door": "open"},
    "move": {"move": "lioness", "to": "doorway"},
    "pose": {"pose": "tim", "to": "sit_shock"},
    "face": {"face": "tim", "to": "lioness"},
    "prop": {"prop": "idea", "to": {"b": 0.3}},
    "show": {"show": {"anger": "tim"}},
    "hide": {"hide": "anger:tim"},
    "camera": {"camera": "close_push"},
}
_FENCE_VALUE = {"over": 1.0, "ease": "back", "to": "doorway", "expr": "shocked", "bob": 0.3,
                "flicker": True, "blink": {"b": 0.35, "over": 0.4}, "out": True}


def _fence_scene(verb, **fields):
    shot = copy.deepcopy(_FENCE_SHOT)
    shot["beats"] = [{"at": 0.5, "show": {"anger": "tim"}}] if verb == "hide" else []
    shot["beats"].append({"at": 1.0, **_FENCE_BASE[verb], **fields})
    return {"id": "fence", "duration": 4.0, "cast": {"tim": "tim", "lioness": "lioness"}, "shots": [shot]}


def _changes_the_timeline(verb, field, extra):
    with_it = load_scene(_fence_scene(verb, **extra, **{field: _FENCE_VALUE[field]}), BANK)
    without = load_scene(_fence_scene(verb, **extra), BANK)
    return any(repr(state_at(with_it, BANK, t, t)) != repr(state_at(without, BANK, t, t))
               for t in (1.0, 1.1, 1.3, 1.6, 2.5))


def test_every_beat_field_is_read_or_rejected():
    # scene.BEAT_FIELDS is the one table of the optional beat fields the timeline reads per
    # verb. A field in it must load and change what state_at returns; any other must fail.
    from toon.scene import BEAT_FIELDS, BEAT_OPTIONAL, VERBS, Beat

    assert set(BEAT_FIELDS) == set(VERBS)
    assert set(BEAT_OPTIONAL) == set(Beat.model_fields) - {"at", *VERBS}
    for verb in VERBS:
        for field in BEAT_OPTIONAL:
            if field in _FENCE_BASE[verb]:
                continue  # the base beat already sets it (and loads)
            extra = {"over": 1.0} if field == "ease" and "over" in BEAT_FIELDS[verb] else {}
            data = _fence_scene(verb, **extra, **{field: _FENCE_VALUE[field]})
            if field in BEAT_FIELDS[verb]:
                load_scene(data, BANK)
                assert _changes_the_timeline(verb, field, extra), (verb, field)
            else:
                with pytest.raises(SceneError, match=rf"beats\[\d\]\.{field}: "):
                    load_scene(data, BANK)
    beat = load_scene(_fence_scene("door"), BANK).shots[0].beats[0]
    assert beat.over is None and beat.ease is None


@pytest.mark.parametrize("prop, use", [("p", {"kind": "plate", "held_by": "tim"}),
                                       ("s", {"kind": "plate_stack", "count": 6})])
@pytest.mark.parametrize("flag, value", [("flicker", True), ("blink", {"b": 0.35, "over": 0.2}), ("out", True)])
def test_prop_beat_flags_rejected_on_kinds_that_ignore_them(prop, use, flag, value):
    d = with_props(idea={"kind": "idea_bulb", "on": "tim"}, **{prop: use})
    d["shots"][0]["beats"].append({"at": 1.0, "prop": prop, flag: value})
    with pytest.raises(SceneError, match=rf"beats\[0\]\.{flag}: a {use['kind']} prop ignores {flag}"):
        load_scene(d, BANK)
    ok = with_props(idea={"kind": "idea_bulb", "on": "tim"})
    ok["shots"][0]["beats"].append({"at": 1.0, "prop": "idea", flag: value})
    assert load_scene(ok, BANK).shots[0].beats[0].verb == "prop"   # the idea_bulb honours it
```

Append to `tests/unit/toon/test_bank.py` (S11-10, a fence: green from the start):

```python
def test_prop_kinds_match_bank_prop_kinds():
    # scene.PROP_KINDS (what each prop kind takes and honours) must cover exactly the kinds the
    # bank can declare: a bank kind with no entry would fail every scene that uses it.
    from typing import get_args

    from toon.bank import PropDef
    from toon.scene import PROP_KINDS

    assert set(PROP_KINDS) == set(get_args(PropDef.model_fields["kind"].annotation))
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/toon/test_scene.py tests/unit/toon/test_bank.py -q -k "timing_fields or every_beat_field or prop_beat_flags or prop_kinds_match"`
Expected: S11-1 red on show-ease / hide / prop / door-ease cases (`DID NOT RAISE`; the two camera
cases are already green), S11-2 red (`ImportError: cannot import name 'BEAT_FIELDS'`), S11-3 red
(`DID NOT RAISE`) on all six plate/plate_stack cases, S11-10 green. Commit:
`test(toon): red — beat fields the timeline ignores still load (S11-1..3, S11-10 fence)`.

- [ ] **Step 3: Implement** — in `src/toon/scene.py` replace the `PROP_KINDS` block with:

```python
PROP_BEAT_FLAGS = ("flicker", "blink", "out")
# Per bank-prop kind: (use fields it needs, use fields it draws, states a `to:` beat animates,
# beat flags it honours). Anything else would load cleanly and be silently ignored by the
# renderer, so it is rejected.
PROP_KINDS: dict[str, tuple[frozenset[str], frozenset[str], frozenset[str], frozenset[str]]] = {
    "idea_bulb": (frozenset({"on"}), frozenset({"on", "b"}), frozenset({"b"}), frozenset(PROP_BEAT_FLAGS)),
    "plate": (frozenset({"held_by"}), frozenset({"held_by"}), frozenset(), frozenset()),
    "plate_stack": (frozenset({"count"}), frozenset({"count"}), frozenset({"count"}), frozenset()),
}
# Per verb: the optional beat fields timeline.state_at reads. Any other field set on a beat would
# load and be silently ignored, so it fails instead. On top of the table: `ease` only shapes a
# change that has an `over:`, and a prop beat's over/ease only time a `to:` change (its flags
# are per prop kind, PROP_KINDS).
BEAT_FIELDS: dict[str, frozenset[str]] = {
    "door": frozenset({"over", "ease"}),
    "move": frozenset({"over", "ease", "to", "bob"}),
    "pose": frozenset({"over", "ease", "to", "expr"}),
    "face": frozenset({"over", "ease", "to"}),
    "prop": frozenset({"over", "ease", "to", *PROP_BEAT_FLAGS}),
    "show": frozenset({"over"}),  # the pop length
    "hide": frozenset(),
    "camera": frozenset(),
}
# Why a verb takes no timing: the reason an over:/ease: on it fails with.
_UNTIMED = {"camera": "a camera beat is a cut to a new preset",
            "hide": "a hide beat is instant",
            "show": "a show beat pops in, and only over: (the pop length) times it"}
```

`Beat` fields become `over: float | None = None  # None: not given (instant; a show pops in
over 0.25 s)`, `ease: Ease | None = None  # None: not given (smooth)`, `bob: float | None = None`;
after the class: `BEAT_OPTIONAL = tuple(f for f in Beat.model_fields if f != "at" and f not in VERBS)`.
`_check_prop_use` unpacks `need, draws = PROP_KINDS[kind][:2]`. Add:

```python
def _unread(verb: str, field: str) -> str:
    if field in ("over", "ease") and verb in _UNTIMED:
        return f"{_UNTIMED[verb]}; {field} does not apply"
    users = [u for u, fields in BEAT_FIELDS.items() if field in fields]
    return f"only valid with {_a(users[0])} beat" if len(users) == 1 else f"not valid with {_a(verb)} beat"


def _check_beat_fields(b: Beat, bw: str, kind: str | None) -> list[str]:
    """Every optional field set on a beat must be one the timeline reads for its verb (and, on a
    prop beat, for its prop kind; `kind` is None when the prop doesn't resolve)."""
    p: list[str] = []
    v = b.verb
    for field in BEAT_OPTIONAL:
        if getattr(b, field) is None:
            continue
        if field not in BEAT_FIELDS[v]:
            p.append(f"{bw}.{field}: {_unread(v, field)}")
        elif v == "prop" and field in ("over", "ease") and b.to is None:
            p.append(f"{bw}.{field}: a prop beat times only a to: change; {field} does nothing without to:")
        elif field == "ease" and not (b.over or 0.0) > 0:
            p.append(f"{bw}.ease: does nothing without over: (the change is instant)")
        elif v == "prop" and field in PROP_BEAT_FLAGS and kind is not None and field not in PROP_KINDS[kind][3]:
            takers = sorted(k for k, spec in PROP_KINDS.items() if field in spec[3])
            p.append(f"{bw}.{field}: {_a(kind)} prop ignores {field} (only {', '.join(takers)} takes it)")
    return p
```

In `_check_beat`: delete the `to` check for door/show/hide/camera, the camera
`model_fields_set` loop and the trailing "verb-specific fields" block; compute the prop kind once
(`pu = shot.props.get(b.prop) if v == "prop" else None`;
`kind = bank.props[pu.kind].kind if pu is not None and pu.kind in bank.props else None`), use it
in the prop branch, and end with `p += _check_beat_fields(b, bw, kind)`. `scene_warnings` reads
`b.at + (b.over or 0.0)`. In `src/toon/timeline.py`: `_progress` uses `over = b.over or 0.0` and
`EASES[b.ease or "smooth"]`; `move` uses `(b.bob or 0.0)`; `show` uses
`dur = b.over if b.over is not None and b.over > 0 else POP`.

- [ ] **Step 4: Run the sprint command** — all green. Commit:
  `feat(toon): every beat field is read by the timeline or rejected (S11-1..3; 2e camera check)`.

### Task 2: Hair keys beside `layers:` fail (S11-4)

**Files:** Modify `src/toon/bank.py` (`_check_look`); Test `tests/unit/toon/test_bank.py`.

- [ ] **Step 1: Failing test**

```python
@pytest.mark.parametrize("key", ["fill: ink", "fringe: saw", "none: true"])
def test_hair_keys_beside_layers_rejected(tmp_path, key):
    # Beside `layers:` the layered drawing reads only `layers` and `bun`; a top-level per-layer
    # key (or `none`) would load and be silently ignored.
    root = tmp_path / "bank"
    shutil.copytree(default_root(), root)
    p = root / "characters" / "tim.yaml"
    text = p.read_text()
    assert "hair:\n  layers:\n" in text
    p.write_text(text.replace("hair:\n  layers:\n", f"hair:\n  {key}\n  layers:\n", 1))
    with pytest.raises(BankError, match=rf"tim\.yaml: hair\.{key.split(':')[0]}: ignored beside hair\.layers"):
        load_bank(root)


def test_a_bun_beside_layers_loads(tmp_path):
    root = tmp_path / "bank"
    shutil.copytree(default_root(), root)
    p = root / "characters" / "tim.yaml"
    p.write_text(p.read_text().replace("hair:\n  layers:\n", "hair:\n  bun: [0.0, 0.5, -0.6, 0.3]\n  layers:\n", 1))
    assert load_bank(root).characters["tim"].hair["bun"] == [0.0, 0.5, -0.6, 0.3]
```

- [ ] **Step 2: Verify red** (`DID NOT RAISE` ×3; the bun case is green). Commit
  `test(toon): red — hair keys beside layers load silently (S11-4)`.
- [ ] **Step 3: Implement** — in `_check_look`, after the per-layer loop:

```python
    beside = [f"{path}: hair.{k}: ignored beside hair.layers (only layers and bun are read there)"
              for k in ch.hair if layers is not None and (k in HAIR_LAYER_KEYS or k == "none")]
    if unknown or beside:
        raise BankError("; ".join([*(f"{path}: {where}: unknown key (known: {sorted(keys)})"
                                     for where, keys in unknown), *beside]))
```

- [ ] **Step 4: Green; commit** `fix(toon): hair keys beside layers fail with the file and key (S11-4)`.

### Task 3: Graphic keys — card `id:`, visible-key collisions (S11-5, S11-6)

**Files:** Modify `src/toon/scene.py` (`CARD_KINDS`, `Show.id`, `graphic_key`, `_check_graphics`,
`_check`, `_check_beat` show/hide branches); Test `tests/unit/toon/test_scene.py`,
`tests/unit/toon/test_timeline.py`.

**Interfaces:** Produces `CARD_KINDS = ("x_card", "check_pill")`; `graphic_key(show)` →
`<kind>:<id or icon>` for cards.

- [ ] **Step 1: Failing tests** — `test_scene.py`:

```python
def test_show_of_a_visible_graphic_key_is_rejected():
    card = {"x_card": "bulb", "at": [0.6, 0.3]}
    d = mini(**{"at": 0.5, "show": card})
    d["shots"][0]["beats"].append({"at": 1.0, "show": {**card, "at": [0.2, 0.3]}})
    with pytest.raises(SceneError, match=r"shots\[0\]\.beats\[1\]\.show: 'x_card:bulb' is still showing "
                                         r"from shots\[0\]\.beats\[0\]"):
        load_scene(d, BANK)
    bubble = mini(**{"at": 0.5, "show": {"bubble": ["dishes"], "from": "tim"}})
    bubble["shots"][0]["beats"].append({"at": 1.0, "show": {"bubble": ["bang"], "from": "tim"}})
    with pytest.raises(SceneError, match=r"beats\[1\]\.show: 'bubble:tim' is still showing from shots\[0\]\.beats\[0\]"):
        load_scene(bubble, BANK)
    twice = mini(**{"at": 0.5, "show": card})
    twice["shots"][0]["beats"] += [{"at": 1.0, "hide": "x_card:bulb"}, {"at": 1.5, "hide": "x_card:bulb"}]
    with pytest.raises(SceneError, match=r"beats\[2\]\.hide: 'x_card:bulb' is already hidden by shots\[0\]\.beats\[1\]"):
        load_scene(twice, BANK)
    again = mini(**{"at": 0.5, "show": card})
    again["shots"][0]["beats"] += [{"at": 1.0, "hide": "x_card:bulb"}, {"at": 1.5, "show": card}]
    assert [b.verb for b in load_scene(again, BANK).shots[0].beats] == ["show", "hide", "show"]
```

`test_timeline.py` (import `SceneError` too):

```python
def test_two_cards_one_icon_with_ids_both_show():
    d = copy.deepcopy(CUT)
    d["shots"][0]["beats"] = [
        {"at": 1.0, "show": {"x_card": "bulb", "id": "first", "at": [0.64, 0.30]}},
        {"at": 1.0, "show": {"x_card": "bulb", "id": "second", "at": [0.20, 0.30]}},
        {"at": 3.0, "hide": "x_card:first"},
    ]
    s = load_scene(d, BANK)
    assert sorted(g.key for g in state_at(s, BANK, 2.0).graphics) == ["x_card:first", "x_card:second"]
    assert [g.key for g in state_at(s, BANK, 3.5).graphics] == ["x_card:second"]
    two_shots = copy.deepcopy(d)  # keys are per shot: the same id in another shot is fine
    two_shots["shots"].append({**copy.deepcopy(d["shots"][0]), "at": 6.0})
    two_shots["duration"] = 12.0
    assert len(load_scene(two_shots, BANK).shots) == 2
    bad = copy.deepcopy(d)
    bad["shots"][0]["beats"][1]["show"]["id"] = "Second card"
    with pytest.raises(SceneError, match=r"show\.id"):
        load_scene(bad, BANK)
    not_a_card = copy.deepcopy(CUT)
    not_a_card["shots"][0]["beats"] = [{"at": 1.0, "show": {"anger": "tim", "id": "x"}}]
    with pytest.raises(SceneError, match=r"show\.id: only valid with an x_card or check_pill show"):
        load_scene(not_a_card, BANK)
```

- [ ] **Step 2: Verify red** (S11-5 `DID NOT RAISE`; S11-6 `Extra inputs are not permitted` on
  `id`). Commit `test(toon): red — a second card on one icon silently replaces the first (S11-5, S11-6)`.
- [ ] **Step 3: Implement** — `Show` gains
  `id: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]*$")  # a card's key; never drawn`.

```python
def graphic_key(show: Show) -> str:
    """`<kind>:<target>` — the name a `hide:` beat uses. Keyed on the show's own kind, so a
    stray field of another kind can never pick the target. A card's target is its `id:` when it
    has one, so two cards with one icon get two keys."""
    target = {"speed_lines": show.speed_lines, "bubble": show.from_, "anger": show.anger,
              "x_card": show.x_card, "check_pill": show.check_pill}[show.kind]
    if show.kind in CARD_KINDS and show.id is not None:
        target = show.id
    return f"{show.kind}:{target}"


def _check_graphics(shot: Shot, w: str) -> list[str]:
    """Shows and hides in the order the timeline plays them (by time, then as listed). A show
    whose key is still visible would silently replace that graphic; a hide must take one down."""
    p: list[str] = []
    beats = sorted(enumerate(shot.beats), key=lambda jb: float(jb[1].at))
    shows = {j: graphic_key(b.show) for j, b in beats if b.verb == "show"}
    visible: dict[str, int] = {}  # key -> the show beat that put it up
    gone: dict[str, int] = {}     # key -> the hide beat that took it down
    for j, b in beats:
        bw = f"{w}.beats[{j}]"
        if b.verb == "show":
            key = shows[j]
            if key in visible:
                hint = ", or give each card its own id:" if b.show.kind in CARD_KINDS else ""
                p.append(f"{bw}.show: {key!r} is still showing from {w}.beats[{visible[key]}]; "
                         f"hide it first{hint}")
            visible[key] = j
            gone.pop(key, None)
        elif b.verb == "hide":
            if b.hide in visible:
                del visible[b.hide]
                gone[b.hide] = j
            elif b.hide in gone:
                p.append(f"{bw}.hide: {b.hide!r} is already hidden by {w}.beats[{gone[b.hide]}]")
            elif b.hide in shows.values():
                first = min(float(shot.beats[k].at) for k, key in shows.items() if key == b.hide)
                p.append(f"{bw}.hide: {b.hide!r} was shown at {first:g}s, after this hide at {float(b.at):g}s")
            else:
                p.append(f"{bw}.hide: {b.hide!r} does not match a graphic shown earlier in this shot "
                         f"(shown: {sorted(set(shows.values()))})")
    return p
```

`_check` drops its `shown` dict and calls `p += _check_graphics(shot, w)`; `_check_beat` drops the
`shown` parameter and its `hide` branch, and its `show` branch adds
`if s.id is not None and s.kind not in CARD_KINDS: p.append(f"{bw}.show.id: only valid with an x_card or check_pill show")`.

- [ ] **Step 4: Green; commit** `feat(toon): cards take an id: key; a show over a visible key fails (S11-5, S11-6)`.

### Task 4: Sentence splitter — closers attach left, abbreviations (S11-7)

**Files:** Modify `src/toon/scene.py` (`split_sentences`); Test `tests/unit/toon/test_scene.py`.

- [ ] **Step 1: Failing test** — extend `test_sentences_count_real_breaks_only`'s cases with:

```python
    ("他說：「我走了。」然後離開。", ["他說：「我走了。」", "然後離開。"]),   # 。」 : the closer stays left
    ("「走吧！」「好。」", ["「走吧！」", "「好。」"]),
    ("「A。B。」", ["「A。", "B。」"]),                     # a quoted narration still splits inside
    ("她說：『好。』）然後走了。", ["她說：『好。』）", "然後走了。"]),  # a run of closers
    ('She said "Stop." Then she left.', ['She said "Stop."', "Then she left."]),
    ("The U.S. economy grew. Jobs rose.", ["The U.S. economy grew.", "Jobs rose."]),
    ("Dr. Lin said so. Then she left.", ["Dr. Lin said so.", "Then she left."]),
    ("Bring snacks, e.g. chips. Then go.", ["Bring snacks, e.g. chips.", "Then go."]),
    ("J. K. Rowling wrote it. Fans loved it.", ["J. K. Rowling wrote it.", "Fans loved it."]),
    ("We met at 9 a.m. sharp. It rained.", ["We met at 9 a.m. sharp.", "It rained."]),
    ("El Sr. Pérez llegó. Luego se fue.", ["El Sr. Pérez llegó.", "Luego se fue."]),
    ("Neither did I. We left.", ["Neither did I.", "We left."]),       # "I" is not an initial
    ("We left. Then we moved to the U.S.", ["We left.", "Then we moved to the U.S."]),  # ends the text
```

and add to the test body:

```python
    closers = "」』”’）)]】》〉\"'"
    assert not [s for s in split_sentences(narration) if s[0] in closers]
```

- [ ] **Step 2: Verify red** (the 。」 / 「」 / straight-quote / abbreviation cases). Commit
  `test(toon): red — a closing quote starts the next sentence; "U.S." splits (S11-7)`.
- [ ] **Step 3: Implement**

```python
# A terminator run, then any closing quotes or brackets right after it: they belong to the
# sentence they close (spec §11.2 b2), so no sentence starts with a closer.
_BREAK = re.compile(r"([.!?。！？…]+)([」』”’）)\]】》〉\"']*)")
# A "." after one of these words, or after a one-letter word (U.S., J. K., e.g., a.m.; not the
# pronoun "I"), is an abbreviation, not a break. en + es-419. The known cost: "…moved to the
# U.S. Then…" stays one sentence; `pipeline toon validate --narration` prints the split.
ABBREVIATIONS = frozenset({"mr", "mrs", "ms", "dr", "prof", "st", "vs", "etc", "sr", "sra", "srta"})
_WORD_BEFORE = re.compile(r"(?<![A-Za-z])[A-Za-z]+$")


def _abbreviation(before: str) -> bool:
    m = _WORD_BEFORE.search(before)
    return m is not None and ((len(m.group()) == 1 and m.group() != "I") or m.group().lower() in ABBREVIATIONS)


def split_sentences(narration: str) -> list[str]:
    """The narration's sentences, as `at: {sentence: n}` anchors count them.

    A run of terminators is one break ("What?!", "他走了。……"), and the closing quotes right
    after it stay with it (「我走了。」). A lone "." between digits is a decimal point ("3.5"), and
    one after an abbreviation ("U.S.", "Dr.") is no break. An ellipsis ("……", "...") followed
    directly by more text is a pause inside the sentence ("我……不知道。"); followed by a space or
    the end, it ends the sentence.
    """
    text = narration.strip()
    parts, start = [], 0
    for m in _BREAK.finditer(text):
        run, end = m.group(1), m.end()
        before, nxt = text[:m.start()], text[end:end + 1]
        if run == "." and before[-1:].isdigit() and nxt.isdigit():
            continue
        if set(run) <= {".", "…"} and run != "." and nxt and not nxt.isspace():
            continue
        if run == "." and _abbreviation(before):
            continue
        parts.append(text[start:end])
        start = end
    parts.append(text[start:])
    return [s.strip() for s in parts if s.strip()]
```

- [ ] **Step 4: Green; commit** `feat(toon): sentence splitter keeps closing quotes left and skips abbreviations (S11-7)`.

### Task 5: `SceneError` names its source (S11-8)

**Files:** Modify `src/toon/scene.py` (`SceneError`, `SceneData`, `source_name`, `scene_path`,
`read_scene`, `scene_data_from_visual`, `load_scene`), `src/pipeline/storyboard.py`
(`Storyboard.path`), `src/pipeline/director/storyboard_validator.py`, `src/pipeline/composer/toon.py`,
`src/pipeline/composer/base.py` (`render_scene(storyboard_file=)`), `src/pipeline/stages/compose.py`
(passes `ctx.storyboard_path`). Test `tests/unit/toon/test_scene.py`,
`tests/unit/test_composer_toon.py`.

**Interfaces:**
- `SceneError(problems: list[str], source: str | None = None)`; `.problems`, `.source`.
- `SceneData(dict[str, Any])` with `.source: str | None`; `read_scene(ref) -> SceneData`.
- `scene_path(ref) -> Path`; `source_name(path) -> str` (repo-relative inside the repo).
- `scene_data_from_visual(visual, origin: str | None = None) -> SceneData`.
- `load_scene(data, bank, narration=None, duration=None, source=None)`; `source` defaults to
  `data.source`.
- `Storyboard.path: Path | None` (set by `load`/`save`; not serialised, not compared).
- `render_scene(..., storyboard_file: Path | None = None)`,
  `render_toon_scene(..., storyboard_file=None)`, `_validate_scene(..., storyboard_file=None)`.

- [ ] **Step 1: Failing tests** — `test_scene.py`:

```python
def test_scene_error_names_its_source(tmp_path):
    import yaml

    from toon.scene import scene_data_from_visual

    bad = mini()
    bad["shots"][0]["camera"] = "nope"
    f = tmp_path / "bad.yaml"
    f.write_text(yaml.safe_dump(bad))
    with pytest.raises(SceneError) as e:                     # a scene file: its path
        load_scene(read_scene(str(f)), BANK)
    assert e.value.source == str(f)
    assert str(e.value).startswith(f"{f}: shots[0].camera: unknown camera 'nope'")
    data = read_scene("001-lioness-dishes")                  # in the repo: repo-relative
    data["shots"][0]["camera"] = "nope"
    with pytest.raises(SceneError, match=r"^assets/toon/scenes/001-lioness-dishes\.yaml: shots\[0\]\.camera"):
        load_scene(data, BANK)
    origin = "output/projects/p/storyboard.json scene s2"   # an inline visual: storyboard + scene id
    with pytest.raises(SceneError) as e:
        load_scene(scene_data_from_visual({"type": "toon", **bad}, origin), BANK)
    assert str(e.value).startswith(f"{origin}: shots[0].camera: unknown camera")
    ref = {"type": "toon", "scene": str(f)}                  # a reference: the file, from the scene
    with pytest.raises(SceneError, match=rf"^{re.escape(str(f))} \(from {origin}\): shots\[0\]\.camera"):
        load_scene(scene_data_from_visual(ref, origin), BANK)
    with pytest.raises(SceneError, match=r"^x\.yaml: shots\[0\]\.camera"):   # explicit source=
        load_scene(bad, BANK, source="x.yaml")
```

(add `import re` at the top of `test_scene.py`). `test_composer_toon.py`:

```python
def test_render_error_and_validator_name_the_scene_source(tmp_path):
    words = {"type": "toon", "cast": {"tim": "tim"}, "shots": [{
        "at": 0.0, "set": "office", "camera": "two_shot",
        "place": {"tim": {"spot": "desk_seat", "pose": "sit_typing"}},
        "beats": [{"at": 1.0, "show": {"bubble": ["Dishes. Now."], "from": "tim"}}]}]}
    sb_file = tmp_path / "storyboard_zh-TW.json"
    Storyboard(scenes=[Scene(id="s2", section="content", narration="One.", narration_est_sec=5.0,
                             visual=words)]).save(sb_file)
    (issue,) = validation_errors(validate_storyboard(Storyboard.load(sb_file), tmp_path))
    assert f"{sb_file} scene s2: shots[0].beats[0].show" in issue.issue
    with pytest.raises(SceneRenderError) as e:
        base.render_scene({"id": "s2", "narration": "One.", "visual": words}, 5.0, "16:9", tmp_path,
                          storyboard_file=sb_file)
    assert f"{sb_file} scene s2: shots[0].beats[0].show" in e.value.reason
    missing = tmp_path / "gone.yaml"
    with pytest.raises(SceneRenderError) as e:
        base.render_scene({"id": "s3", "visual": {"type": "toon", "scene": str(missing)}}, 5.0, "16:9",
                          tmp_path, storyboard_file=sb_file)
    assert f"{missing} (from {sb_file} scene s3): scene file not found" in e.value.reason
```

- [ ] **Step 2: Verify red** (`AttributeError: 'SceneError' object has no attribute 'source'`;
  `TypeError: render_scene() got an unexpected keyword argument 'storyboard_file'` / the issue
  lacks the file). Commit `test(toon): red — SceneError never names the scene file (S11-8)`.
- [ ] **Step 3: Implement** (scene.py):

```python
class SceneError(ValueError):
    """Problems with a scene, each `<path>: <message>`. `source` names where the scene came
    from (a scene file, or a storyboard scene) and prefixes every problem."""

    def __init__(self, problems: list[str], source: str | None = None):
        self.problems, self.source = problems, source
        super().__init__("; ".join(f"{source}: {p}" if source else p for p in problems))


class SceneData(dict[str, Any]):
    """Scene data plus where it came from, which `load_scene` names in every error."""

    def __init__(self, data: dict, source: str | None):
        super().__init__(data)
        self.source = source


_REPO = Path(__file__).resolve().parents[2]


def source_name(path: Path) -> str:
    """A file as errors name it: repo-relative inside the repo, else as given."""
    try:
        return str(Path(path).resolve().relative_to(_REPO))
    except ValueError:
        return str(path)


def scene_path(ref: str) -> Path:
    """A scene id (`001-lioness-dishes` → assets/toon/scenes/<id>.yaml) or a path to a YAML file."""
    path = Path(ref)
    return path if path.suffix in (".yaml", ".yml") else scenes_root() / f"{ref}.yaml"
```

`read_scene` raises `SceneError([...], source=source_name(path))` with problems
`"scene file not found"`, `f"not valid YAML: …"`, `f"expected a scene mapping …"`, and returns
`SceneData(data, source_name(path))`. `scene_data_from_visual(visual, origin=None)`:
a reference's source is `f"{source_name(scene_path(ref))} (from {origin})"` when `origin` is
given (else the file's own); a `read_scene` failure is re-raised with that source; key errors
and "needs scene or inline" carry `source=origin`; an inline scene returns
`SceneData({"id": "inline", "cast": {}, **own}, origin)`. `load_scene` gains `source=None`,
defaults it to `getattr(data, "source", None)`, and re-raises any source-less `SceneError` from
its body as `type(exc)(exc.problems, source=source)`. Pipeline: `Storyboard.path` field
(`field(default=None, compare=False, repr=False)`) set in `load` and `save`;
`validate_storyboard` passes `storyboard_file=sb.path` down to `_validate_toon_scene`, which
builds `origin = f"{source_name(f) if f else 'storyboard'} scene {scene.id}"`; `render_scene`
forwards `storyboard_file` to `render_toon_scene`, which builds the same origin; compose passes
`storyboard_file=ctx.storyboard_path`.

- [ ] **Step 4: Green; commit** `feat(toon): SceneError names the scene file or storyboard scene it came from (S11-8)`.

### Task 6: Shot starts follow the narration (S11-12, S11-13)

**Files:** Modify `src/toon/scene.py` (`SentenceAnchor.plus`, `Shot.at`, `anchor_text`,
`_resolve_anchors`, `_shot_order`, `_check`, `shot_length`, `scene_warnings`),
`src/toon/timeline.py`, `src/toon/render.py` (`float(shot.at)`); Test `tests/unit/toon/test_scene.py`.

**Interfaces:** `SentenceAnchor(sentence: int ≥ 1, plus: float ≥ 0 = 0.0)`;
`Shot.at: float | SentenceAnchor`; `anchor_text(at) -> str` (`"{sentence: 3, plus: 2}"` or `"3.5s"`).
Test helpers `N3` and `anchored_001(plus=2.0)` in `test_scene.py` (imported by later tasks).

- [ ] **Step 1: Failing tests**

```python
# Spec §11.3's demo narration (s2 of the Sprint 9 smoke; edge-tts 13.44 s): three sentences.
N3 = "提姆靈光一閃，想到一個好點子。獅子太太氣沖沖衝進來，要他馬上去洗碗。提姆只好站到水槽前，看著靈感一點點熄滅。"


def anchored_001(plus=2.0):
    """Scene 001 with shots 2–4 on N3's sentences: 2 → sentence 2, 3 → 3, 4 → 3 + plus."""
    d = read_scene("001-lioness-dishes")
    d["shots"][1]["at"] = {"sentence": 2}
    d["shots"][2]["at"] = {"sentence": 3}
    d["shots"][3]["at"] = {"sentence": 3, "plus": plus}
    return d


def test_shot_sentence_anchor_follows_the_narration():
    authored = [[b["at"] for b in sh.get("beats", [])] for sh in read_scene("001-lioness-dishes")["shots"]]
    for duration in (13.44, 16.0):
        starts = sentence_starts(N3, duration)
        s = load_scene(anchored_001(), BANK, narration=N3, duration=duration)
        assert [sh.at for sh in s.shots] == pytest.approx([0.0, starts[1], starts[2], starts[2] + 2.0])
        assert [[b.at for b in sh.beats] for sh in s.shots] == authored   # seconds beats: no stretch
    fast = load_scene(anchored_001(), BANK, narration=N3, duration=9.0)   # a much faster take
    assert fast.shots[3].at == pytest.approx(sentence_starts(N3, 9.0)[2] + 2.0)
    assert "cut" in scene_warnings(fast, 9.0)[0]
    d = anchored_001()  # a beat anchor resolves relative to its shot's resolved start, plus included
    d["shots"][2]["beats"].append({"at": {"sentence": 3, "plus": 0.5}, "prop": "idea",
                                   "blink": {"b": 0.35, "over": 0.15}})
    assert load_scene(d, BANK, narration=N3, duration=13.44).shots[2].beats[-1].at == pytest.approx(0.5)


def test_shot_anchors_resolving_out_of_order_fail_loudly():
    two = anchored_001()
    two["shots"][2]["at"] = {"sentence": 2}
    with pytest.raises(SceneError, match=r"shots\[2\]\.at: \{sentence: 2\} → 3\.73s is not after "
                                         r"shots\[1\] at \{sentence: 2\} → 3\.73s"):
        load_scene(two, BANK, narration=N3, duration=13.44)
    overtaken = anchored_001()
    overtaken["shots"][2]["at"] = 8.0
    assert load_scene(overtaken, BANK, narration=N3, duration=13.44).shots[2].at == 8.0
    with pytest.raises(SceneError, match=r"shots\[2\]\.at: 8s is not after shots\[1\] at \{sentence: 2\} → 9\.33s"):
        load_scene(overtaken, BANK, narration=N3, duration=33.6)
    first = anchored_001()
    first["shots"][0]["at"] = {"sentence": 2}
    with pytest.raises(SceneError, match=r"shots\[0\]\.at: \{sentence: 2\} → 3\.73s; the first shot must start at 0"):
        load_scene(first, BANK, narration=N3, duration=13.44)
    past = anchored_001()
    past["shots"][1]["at"] = {"sentence": 4}
    with pytest.raises(SceneError, match=r"shots\[1\]\.at: sentence 4, but narration has 3"):
        load_scene(past, BANK, narration=N3, duration=13.44)
    with pytest.raises(SceneError, match=r"shots\[1\]\.at: sentence anchors need the scene's narration"):
        load_scene(anchored_001(), BANK)
    beyond = anchored_001()  # a beat's plus: past its shot's end
    beyond["shots"][1]["beats"].append({"at": {"sentence": 2, "plus": 9.0}, "door": "close"})
    with pytest.raises(SceneError, match=r"shots\[1\]\.beats\[7\]\.at: 9s is outside the shot"):
        load_scene(beyond, BANK, narration=N3, duration=13.44)
```

- [ ] **Step 2: Verify red** (`shots.1.at: Input should be a valid number`). Commit
  `test(toon): red — shot starts can't follow the narration (S11-12, S11-13)`.
- [ ] **Step 3: Implement**

```python
class SentenceAnchor(_Strict):
    sentence: int = Field(ge=1)
    plus: float = Field(default=0.0, ge=0.0)  # seconds after the sentence starts


def anchor_text(at: float | SentenceAnchor) -> str:
    """An `at:` as the author wrote it, for messages and `toon validate`."""
    if isinstance(at, SentenceAnchor):
        return f"{{sentence: {at.sentence}" + (f", plus: {at.plus:g}" if at.plus else "") + "}"
    return f"{at:g}s"


def _shot_order(shots: list[Shot], starts: list[float]) -> list[str]:
    """After anchors resolve, the first shot starts at 0 and shot starts strictly increase.
    Each problem names the shot, its anchor as authored and its resolved time."""
    def label(i: int) -> str:
        at = shots[i].at
        return f"{anchor_text(at)} → {starts[i]:.2f}s" if isinstance(at, SentenceAnchor) else anchor_text(at)

    p = [f"shots[0].at: {label(0)}; the first shot must start at 0"] if starts[0] != 0 else []
    p += [f"shots[{i}].at: {label(i)} is not after shots[{i - 1}] at {label(i - 1)}; "
          f"shots must start in increasing order"
          for i in range(1, len(starts)) if starts[i] <= starts[i - 1]]
    return p


def _resolve_anchors(scene: ToonScene, narration: str | None) -> ToonScene:
    """Sentence anchors → seconds: shots first (sentence start + plus), then each beat relative
    to its shot's resolved start. Every anchor resolves through sentence_starts(), the seam where
    measured word timings (E9 item 3) plug in later. Seconds stay as written: nothing stretches."""
    anchored = [f"shots[{i}].at" for i, sh in enumerate(scene.shots) if isinstance(sh.at, SentenceAnchor)]
    anchored += [f"shots[{i}].beats[{j}].at" for i, sh in enumerate(scene.shots)
                 for j, b in enumerate(sh.beats) if isinstance(b.at, SentenceAnchor)]
    if anchored and (not narration or scene.duration is None):
        raise SceneError([f"{a}: sentence anchors need the scene's narration and duration" for a in anchored])
    starts = sentence_starts(narration, scene.duration) if anchored else []
    problems: list[str] = []

    def resolve(at: float | SentenceAnchor, where: str) -> float:
        if not isinstance(at, SentenceAnchor):
            return at
        if at.sentence > len(starts):
            problems.append(f"{where}: sentence {at.sentence}, but narration has {len(starts)}")
            return math.nan
        return starts[at.sentence - 1] + at.plus

    shot_at = [resolve(sh.at, f"shots[{i}].at") for i, sh in enumerate(scene.shots)]
    if problems:
        raise SceneError(problems)
    problems += _shot_order(scene.shots, shot_at)
    if problems:
        raise SceneError(problems)
    if not anchored:
        return scene
    shots = []
    for i, sh in enumerate(scene.shots):
        beats = [b if not isinstance(b.at, SentenceAnchor) else
                 b.model_copy(update={"at": resolve(b.at, f"shots[{i}].beats[{j}].at") - shot_at[i]})
                 for j, b in enumerate(sh.beats)]
        shots.append(sh.model_copy(update={"at": shot_at[i], "beats": beats}))
    if problems:
        raise SceneError(problems)
    return scene.model_copy(update={"shots": shots})
```

`Shot.at: float | SentenceAnchor`. `_check` drops its own first-shot / increasing checks (now in
`_shot_order`). `shot_length` and `scene_warnings` wrap shot starts in `float(...)`; timeline's
`shot_index` / `state_at` and render's `frame` use `float(shot.at)` (resolved before they run, as
`_progress` already assumes for beats).

- [ ] **Step 4: Green; commit** `feat(toon): shots take sentence anchors with plus:, resolved in order or loudly (S11-12, S11-13)`.

### Task 7: Drift warning for seconds-timed shots (S11-14)

**Files:** Modify `src/toon/scene.py` (`ToonScene` private attrs + properties, `load_scene`,
`drift_warnings`), `src/pipeline/director/storyboard_validator.py`, `src/pipeline/composer/toon.py`;
Test `tests/unit/test_composer_toon.py`.

**Interfaces:** `ToonScene.authored_duration: float | None`,
`ToonScene.authored_shot_starts: tuple[float | SentenceAnchor, ...]` (set by `load_scene`);
`DRIFT_TOLERANCE = 0.5`; `drift_warnings(scene, duration) -> list[str]`.

- [ ] **Step 1: Failing test**

```python
def test_validator_warns_when_seconds_timed_shots_drift_from_narration(tmp_path):
    from tests.unit.toon.test_scene import N3, anchored_001

    def drift(visual, est):
        return [i for i in _validate_scene(_scene(visual, narration=N3, est=est), tmp_path)
                if "won't follow the narration" in i.issue]

    ref = {"type": "toon", "scene": "001-lioness-dishes"}   # authored 13.0 s; shots 2–4 in seconds
    (w,) = drift(ref, 16.2)
    assert w.severity == "warn"
    assert ("shots 2–4 are in seconds and won't follow the narration (authored 13.0 s, narration 16.2 s); "
            "anchor them with `at: {sentence: n}`") in w.issue
    assert drift(ref, 13.5) == [] and drift(ref, 12.5) == []        # within 0.5 s
    assert drift({"type": "toon", **anchored_001()}, 16.2) == []    # anchored shots follow it
    partly = anchored_001()
    partly["shots"][2]["at"], partly["shots"][3]["at"] = 6.2, 9.7
    (w,) = drift({"type": "toon", **partly}, 16.2)
    assert "shots 3–4 are in seconds" in w.issue
```

- [ ] **Step 2: Verify red** (`ValueError: not enough values to unpack (expected 1, got 0)`).
  Commit `test(toon): red — seconds-timed shots drift from a new narration silently (S11-14)`.
- [ ] **Step 3: Implement** — on `ToonScene`:

```python
    # Set by load_scene, never authored or serialised (so never in the clip's cache key): the
    # authored duration and each shot's authored start, for the drift warning and `toon validate`.
    _authored_duration: float | None = PrivateAttr(default=None)
    _shot_starts: tuple[float | SentenceAnchor, ...] = PrivateAttr(default=())

    @property
    def authored_duration(self) -> float | None:
        return self._authored_duration

    @property
    def authored_shot_starts(self) -> tuple[float | SentenceAnchor, ...]:
        return self._shot_starts
```

`load_scene` sets both on the scene it returns (`scene._authored_duration = authored_duration`;
`scene._shot_starts = tuple(sh.at for sh in raw.shots)`). Then:

```python
DRIFT_TOLERANCE = 0.5  # seconds


def _numbers(ns: list[int]) -> str:
    return f"{ns[0]}–{ns[-1]}" if len(ns) > 2 and ns == list(range(ns[0], ns[-1] + 1)) else ", ".join(map(str, ns))


def drift_warnings(scene: ToonScene, duration: float) -> list[str]:
    """Shots timed in seconds stay put when the narration's length changes. A warning, not an
    error (a scene timed in seconds is legitimate): it fires when the scene has an authored
    duration, a later shot starts at an absolute time, and the narration is more than
    DRIFT_TOLERANCE off the authored duration."""
    fixed = [i + 1 for i, at in enumerate(scene.authored_shot_starts)
             if i > 0 and not isinstance(at, SentenceAnchor)]
    authored = scene.authored_duration
    if authored is None or not fixed or abs(duration - authored) <= DRIFT_TOLERANCE:
        return []
    which = f"shots {_numbers(fixed)} are" if len(fixed) > 1 else f"shot {fixed[0]} is"
    return [f"scene {scene.id}: {which} in seconds and won't follow the narration (authored "
            f"{authored:.1f} s, narration {duration:.1f} s); anchor them with `at: {{sentence: n}}`"]
```

The validator returns the cut warnings (fix "Lengthen the narration or tighten the beats.") plus
the drift warnings (fix "Anchor the shots to sentences, `at: {sentence: n}`; check the split with
`uv run pipeline toon validate <scene> --narration …`."). Compose logs each drift warning as
`toon.scene.drift`. Update `test_validator_warns_when_narration_is_shorter_than_the_scene` (find
the cut issue among the two warnings) and `test_toon_warning_is_picked_up_by_the_warn_severity_collector`
("Validation warnings: 2") in the fix commit (Ruling 6).

- [ ] **Step 4: Green; commit** `feat(toon): drift warning when seconds-timed shots won't follow the narration (S11-14)`.

### Task 8: `pipeline toon validate --narration --duration` (S11-9)

**Files:** Modify `src/toon/cli.py`, `src/toon/scene.py` (`NeedsNarration`); Test
`tests/unit/toon/test_cli.py`.

**Interfaces:** `class NeedsNarration(SceneError)` raised by `_resolve_anchors` when anchors
have no narration or duration.

- [ ] **Step 1: Failing tests**

```python
def _anchored_file(tmp_path):
    import yaml

    from tests.unit.toon.test_scene import anchored_001

    path = tmp_path / "anchored.yaml"
    path.write_text(yaml.safe_dump(dict(anchored_001()), allow_unicode=True))
    return path


def test_validate_with_narration_prints_the_sentence_table(tmp_path):
    from tests.unit.toon.test_scene import N3
    from toon.scene import sentence_starts, split_sentences

    path = _anchored_file(tmp_path)
    res = runner.invoke(app, ["toon", "validate", str(path), "--narration", N3, "--duration", "13.44"])
    assert res.exit_code == 0, res.stdout
    starts = sentence_starts(N3, 13.44)
    for n, (t, sentence) in enumerate(zip(starts, split_sentences(N3), strict=True), 1):
        assert f"{n:>3}  {t:6.2f}s  {sentence}" in res.stdout
    assert f"{starts[1]:6.2f}s  {{sentence: 2}}" in res.stdout              # each shot's start
    assert f"{starts[2] + 2:6.2f}s  {{sentence: 3, plus: 2}}" in res.stdout
    assert "WARN" not in res.stdout
    warn = runner.invoke(app, ["toon", "validate", "001-lioness-dishes", "--duration", "16.2"])
    assert warn.exit_code == 0, warn.stdout                                 # warnings: still 0
    assert "WARN  scene 001-lioness-dishes: shots 2–4 are in seconds" in warn.stdout
    bad = runner.invoke(app, ["toon", "validate", str(path), "--narration", "只有一句。", "--duration", "13.44"])
    assert bad.exit_code == 1 and "ERROR" in bad.stdout and "sentence 2, but narration has 1" in bad.stdout


def test_validate_anchored_scene_without_narration_names_the_flag(tmp_path):
    res = runner.invoke(app, ["toon", "validate", str(_anchored_file(tmp_path))])
    assert res.exit_code == 1 and isinstance(res.exception, SystemExit), res.exception
    assert "--narration" in res.stdout
```

- [ ] **Step 2: Verify red** (exit 2, `No such option: --narration`; exit 1 without the flag
  named). Commit `test(toon): red — toon validate can't show how anchors resolve (S11-9)`.
- [ ] **Step 3: Implement** — `class NeedsNarration(SceneError): """Sentence anchors with no
  narration (or duration) to resolve them against."""`; `_resolve_anchors` raises it. `cli.py`:

```python
def _load(scene: str, narration: str | None, duration: float | None):
    """Bank + validated scene, or ERROR lines and exit 1 — never a traceback."""
    from toon.bank import load_bank
    from toon.scene import NeedsNarration, load_scene, read_scene

    try:
        bank = load_bank()
        return bank, load_scene(read_scene(scene), bank, narration=narration, duration=duration)
    except (ValueError, yaml.YAMLError) as exc:  # SceneError and BankError are ValueErrors
        for line in str(exc).split("; "):
            typer.echo(f"ERROR  {line}")
        if isinstance(exc, NeedsNarration):
            typer.echo("ERROR  this scene is anchored to sentences: pass --narration TEXT "
                       "(and --duration SEC when the scene has no duration)")
        raise typer.Exit(code=1) from exc


@toon_app.command("validate")
def validate(scene: str = typer.Argument(..., help="scene id or path to a scene YAML"),
             narration: str = typer.Option(None, help="the narration: resolves sentence anchors, prints the split"),
             duration: float = typer.Option(None, help="narration length in seconds (default: the scene's duration)")) -> None:
    from toon.scene import anchor_text, drift_warnings, scene_warnings, sentence_starts, split_sentences

    _, s = _load(scene, narration, duration)
    typer.echo(f"ok  {s.id}: {len(s.shots)} shots, {sum(len(sh.beats) for sh in s.shots)} beats")
    if narration and s.duration is not None:
        typer.echo(f"sentences (narration {s.duration:.2f} s):")
        for n, (t, text) in enumerate(zip(sentence_starts(narration, s.duration), split_sentences(narration),
                                          strict=True), 1):
            typer.echo(f"  {n:>3}  {t:6.2f}s  {text}")
    typer.echo("shots:")
    for i, (sh, at) in enumerate(zip(s.shots, s.authored_shot_starts, strict=True), 1):
        typer.echo(f"  {i:>3}  {float(sh.at):6.2f}s  {anchor_text(at):<24}  {sh.set} / {sh.camera}")
    if s.duration is not None:
        for w in scene_warnings(s, s.duration) + drift_warnings(s, s.duration):
            typer.echo(f"WARN  {w}")
```

- [ ] **Step 4: Green; commit** `feat(toon): toon validate --narration/--duration prints sentences, shot starts, WARN lines (S11-9)`.

### Task 9: Render workers use the caller's bank (S11-11)

**Files:** Modify `src/toon/render.py` (`_init_worker`, `render_frames`); Test
`tests/unit/toon/test_render.py`.

- [ ] **Step 1: Failing test**

```python
def test_workers_use_the_callers_bank(tmp_path):
    # Frames must come from the bank the caller validated (and keyed the cache on), not from
    # whatever is on disk by the time a worker starts.
    root = tmp_path / "bank"
    shutil.copytree(default_root(), root)
    bank = load_bank(root)
    cams = root / "cameras.yaml"
    cams.write_text(cams.read_text().replace("focal: 3050", "focal: 1500", 1))  # two_shot: SCENE's shot 0
    assert load_bank(root).cameras["two_shot"].focal == 1500
    times = [0.5, 1.4]
    parallel = list(R.render_frames(SCENE, bank, times, 320, 180, workers=2))
    assert parallel == [R.frame(SCENE, bank, t, 320, 180).tobytes() for t in times]
```

- [ ] **Step 2: Verify red** (`assert [b'...'] == [b'...']`: the workers drew the edited
  focal). Commit `test(toon): red — render workers reload the bank from disk (S11-11)`.
- [ ] **Step 3: Implement** — `_init_worker(scene_json, bank_json, width, height)` builds
  `Bank.model_validate_json(bank_json)`; `render_frames` passes `bank.model_dump_json()`; drop the
  now-unused `load_bank` import.
- [ ] **Step 4: Green; commit** `fix(toon): render workers draw from the caller's bank, not a disk reload (S11-11)`.

### Task 10: Docs, regression evidence, hub pass (S11-15, S11-16)

**Files:** Modify spec §5/§11 (Tim's decisions as §11.5; §5's "still ignored silently" sentence,
the timing bullet, the show/hide rows), `README.md` (toon validate flags), this plan's ledger.

- [ ] **Step 1: Scene 001 byte-identity (Mac).** Export master `a2e9b55` to a scratch dir and
  render scene 001 at t ∈ {0, 1.5, 3.6, 4.0, 4.7, 6.3, 8.0, 9.8, 10.45, 11.5, 12.2} (960×540)
  with master's code and the branch's; compare SHA-256 of each frame. Expected: all equal.
- [ ] **Step 2: Gates.** `uv run pytest -q`, `uv run ruff check src/ tests/`, `uv run mypy src/`.
- [ ] **Step 3: Docs commit** `docs(toon): spec §11 records Tim's decisions; §5 and README match Sprint 11`.
- [ ] **Step 4: Hub pass (isolated).** Bundle the branch, clone it in a scratch dir on the hub
  (never the hub's own checkout), `uv sync`, run
  `uv run pytest --integration tests/integration/toon tests/unit/toon -q` with `UPDATE_GOLDENS`
  unset, and `git status --porcelain tests/fixtures` (no churn). S11-16's real-scene demo runs
  there too if time allows; otherwise it is left for the EM, stated plainly.

## Red-run ledger

"Expected red" is predicted from this plan's code. Fill in the other columns as you go: observed
red at each "verify it fails" step; the red commit at the fix step; the fix commit at the next
task's red step (a commit can't record its own SHA).

| ID | Test | Task | Expected red | Observed red | Red commit | Fix commit |
|----|------|------|--------------|--------------|------------|------------|
| S11-1 | `test_scene.py::test_beat_timing_fields_rejected_where_ignored` | 1 | `DID NOT RAISE` (6 of 8 cases; camera ×2 green) | `DID NOT RAISE` on 6 of 8 (show-ease, hide over/ease, prop over/ease without to, door ease without over); camera ×2 green | `ee11844` | `1e2cc36` |
| S11-2 | `test_scene.py::test_every_beat_field_is_read_or_rejected` | 1 | `ImportError: cannot import name 'BEAT_FIELDS'` | `ImportError: cannot import name 'BEAT_FIELDS' from 'toon.scene'` | `ee11844` | `1e2cc36` |
| S11-3 | `test_scene.py::test_prop_beat_flags_rejected_on_kinds_that_ignore_them` | 1 | `DID NOT RAISE` (6 of 6) | `DID NOT RAISE` on 6 of 6 | `ee11844` | `1e2cc36` |
| S11-10 | `test_bank.py::test_prop_kinds_match_bank_prop_kinds` | 1 | green (fence) | green (fence; passes on master) | `ee11844` | `1e2cc36` |
| S11-4 | `test_bank.py::test_hair_keys_beside_layers_rejected` | 2 | `DID NOT RAISE` (3 of 3) | `DID NOT RAISE <class 'toon.bank.BankError'>` on 3 of 3 (fill, fringe, none); the bun case green | | |
| S11-5 | `test_scene.py::test_show_of_a_visible_graphic_key_is_rejected` | 3 | `DID NOT RAISE` | | | |
| S11-6 | `test_timeline.py::test_two_cards_one_icon_with_ids_both_show` | 3 | `SceneError: …show.id: Extra inputs are not permitted` | | | |
| S11-7 | `test_scene.py::test_sentences_count_real_breaks_only` | 4 | 「」/straight-quote/abbreviation cases differ | | | |
| S11-8 | `test_scene.py::test_scene_error_names_its_source` + `test_composer_toon.py::test_render_error_and_validator_name_the_scene_source` | 5 | `AttributeError: … 'source'`; `TypeError: … 'storyboard_file'` | | | |
| S11-12 | `test_scene.py::test_shot_sentence_anchor_follows_the_narration` | 6 | `shots.1.at: Input should be a valid number` | | | |
| S11-13 | `test_scene.py::test_shot_anchors_resolving_out_of_order_fail_loudly` | 6 | `shots.2.at: Input should be a valid number` | | | |
| S11-14 | `test_composer_toon.py::test_validator_warns_when_seconds_timed_shots_drift_from_narration` | 7 | `ValueError: not enough values to unpack` | | | |
| S11-9 | `test_cli.py::test_validate_with_narration_prints_the_sentence_table` + `::test_validate_anchored_scene_without_narration_names_the_flag` | 8 | exit 2 `No such option: --narration`; flag not named | | | |
| S11-11 | `test_render.py::test_workers_use_the_callers_bank` | 9 | frames differ (workers drew the edited focal) | | | |
