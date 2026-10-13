"""E11 S12-5: one scene contract. Sprint 11's contract cases fail the same way against both
engines' catalogs where the field is engine-neutral, and each engine's own tables (S11-2, S11-3)
hold against the symbolic timeline. TOY3D_TEST stands in for the toy3d bank until phase 2."""
import copy
import re

import pytest

from tests.unit.toon.catalogs import TOY3D_TEST
from tests.unit.toon.test_scene import BANK, MINI, N3
from toon.scene import NeedsNarration, SceneData, SceneError, drift_warnings, load_scene
from toon.timeline import beats_at

CATALOGS = {"toon2d": BANK, "toy3d": TOY3D_TEST}
ENGINES = pytest.mark.parametrize("engine", sorted(CATALOGS))
BUBBLE = {"bubble": ["dishes"], "from": "tim"}


def scene(engine, *beats):
    d = copy.deepcopy(MINI)
    d["engine"] = engine
    d["shots"][0]["beats"] = [copy.deepcopy(b) for b in beats]
    return d


def problems(engine, data, **kw):
    with pytest.raises(SceneError) as e:
        load_scene(data, CATALOGS[engine], **kw)
    return e.value.problems


# Sprint 11 cases whose fields every engine reads the same way: the problems must be identical.
NEUTRAL = {
    "S11-1 ease on a show": [{"at": 1.0, "show": BUBBLE, "ease": "out"}],
    "S11-1 over on a hide": [{"at": 0.5, "show": BUBBLE}, {"at": 1.0, "hide": "bubble:tim", "over": 0.5}],
    "S11-1 ease on a hide": [{"at": 0.5, "show": BUBBLE}, {"at": 1.0, "hide": "bubble:tim", "ease": "linear"}],
    "S11-1 over on a camera cut": [{"at": 1.0, "camera": "two_shot", "over": 0.5}],
    "S11-1 ease on a camera cut": [{"at": 1.0, "camera": "two_shot", "ease": "out"}],
    "S11-1 prop over without to": [{"at": 1.0, "prop": "idea", "flicker": True, "over": 0.5}],
    "S11-1 prop ease without to": [{"at": 1.0, "prop": "idea", "out": True, "ease": "linear"}],
    "S11-1 ease without over": [{"at": 1.0, "door": "open", "ease": "linear"}],
    "S11-5 a bubble over a visible bubble": [{"at": 0.5, "show": BUBBLE}, {"at": 1.0, "show": BUBBLE}],
    "S11-5 a second hide": [{"at": 0.5, "show": BUBBLE}, {"at": 1.0, "hide": "bubble:tim"},
                            {"at": 1.5, "hide": "bubble:tim"}],
    "S11-5 a hide before its show": [{"at": 1.0, "hide": "bubble:tim"}, {"at": 2.0, "show": BUBBLE}],
    "S11-17 a negative over": [{"at": 1.0, "door": "open", "over": -1}],
    "S11-17 a blink of 0 s": [{"at": 1.0, "prop": "idea", "blink": {"b": 0.35, "over": 0}}],
    "R1 out: false": [{"at": 1.0, "prop": "idea", "to": {"b": 0.3}, "out": False}],
    "R1 an empty prop to:": [{"at": 1.0, "prop": "idea", "to": {}}],
    "a beat outside its shot": [{"at": 9.0, "door": "open"}],
    "words in a bubble": [{"at": 1.0, "show": {"bubble": ["Dishes. Now."], "from": "tim"}}],
}


def _names_dropped(found: list[str]) -> list[str]:
    """Problems without the catalog's own name lists ("use one of [...]", "bank has [...]"):
    those differ per engine by design; the path and the reason must not."""
    return [re.sub(r"(; use one of| \(bank has) \[[^]]*\]\)?", "", p) for p in found]


@pytest.mark.parametrize("case", sorted(NEUTRAL))
def test_contract_cases_fail_the_same_on_both_engines(case):
    toon2d = problems("toon2d", scene("toon2d", *NEUTRAL[case]))
    assert _names_dropped(toon2d) == _names_dropped(problems("toy3d", scene("toy3d", *NEUTRAL[case])))


def anchored(engine):
    """MINI in three shots on N3's sentences: 2 → sentence 2 (with a beat 0.5 s in), 3 → 3."""
    d = scene(engine)
    d["duration"] = 13.0
    first = d["shots"][0]
    second = {**copy.deepcopy(first), "at": {"sentence": 2},
              "beats": [{"at": {"sentence": 2, "plus": 0.5}, "door": "open"}]}
    third = {**copy.deepcopy(first), "at": {"sentence": 3}}
    d["shots"] = [first, second, third]
    return d


@pytest.mark.parametrize("duration", [9.0, 13.44, 16.0])
def test_anchors_resolve_the_same_on_both_engines(duration):
    # S11-7 (the split) and S11-12 (shot anchors) are engine-neutral: same cuts, same beats.
    def timing(engine):
        s = load_scene(anchored(engine), CATALOGS[engine], narration=N3, duration=duration)
        return [(sh.at, [b.at for b in sh.beats]) for sh in s.shots]

    assert timing("toon2d") == timing("toy3d")


def test_anchor_failures_and_drift_are_the_same_on_both_engines():
    out_of_order = {e: anchored(e) for e in CATALOGS}                     # S11-13
    for d in out_of_order.values():
        d["shots"][2]["at"] = {"sentence": 2}
    assert problems("toon2d", out_of_order["toon2d"], narration=N3, duration=13.44) == \
        problems("toy3d", out_of_order["toy3d"], narration=N3, duration=13.44)
    needs = {}
    for engine in CATALOGS:                                                 # S11-9
        with pytest.raises(NeedsNarration) as e:
            load_scene(anchored(engine), CATALOGS[engine])
        needs[engine] = e.value.problems
    assert needs["toon2d"] == needs["toy3d"]
    drift = {}
    for engine in CATALOGS:                                                 # S11-14
        d = anchored(engine)
        d["shots"][2]["at"] = 9.0
        drift[engine] = drift_warnings(load_scene(d, CATALOGS[engine], narration=N3, duration=16.2), 16.2)
    assert drift["toon2d"] == drift["toy3d"] and len(drift["toon2d"]) == 1


def test_errors_name_their_source_the_same_on_both_engines():
    # S11-8
    errors = {}
    for engine in CATALOGS:
        d = scene(engine)
        d["shots"][0]["camera"] = "nope"
        with pytest.raises(SceneError) as e:
            load_scene(SceneData(d, "output/projects/p/storyboard.json scene s2"), CATALOGS[engine])
        errors[engine] = str(e.value)
    # the bank's camera list differs per engine; the source and the path don't
    head = {e: msg.split(" (bank has")[0] for e, msg in errors.items()}
    assert head["toon2d"] == head["toy3d"] == \
        "output/projects/p/storyboard.json scene s2: shots[0].camera: unknown camera 'nope'"


@ENGINES
def test_over_0_on_a_show_appears_at_once(engine):
    # S11-17, through the symbolic timeline every engine reads
    s = load_scene(scene(engine, {"at": 1.0, "show": BUBBLE, "over": 0}), CATALOGS[engine])
    assert beats_at(s, 1.0).graphics[0].k == 1.0


# -- each engine's own tables (S11-2, S11-3), read by the symbolic timeline --

_BASE = {
    "door": {"door": "open"},
    "move": {"move": "lioness", "to": "doorway"},
    "pose": {"pose": "tim", "to": "sit_shock"},
    "face": {"face": "tim", "to": "lioness"},
    "prop": {"prop": "idea", "to": {"b": 0.3}},
    "show": {"show": BUBBLE},
    "hide": {"hide": "bubble:tim"},
    "camera": {"camera": "close_push"},
}
_VALUE = {"over": 1.0, "ease": "back", "to": "doorway", "expr": "shocked", "bob": 0.3,
          "flicker": True, "blink": {"b": 0.35, "over": 0.4}, "out": True}


def _fence(engine, verb, **fields):
    d = scene(engine)
    d["cast"] = {"tim": "tim", "lioness": "lioness"}
    shot = d["shots"][0]
    shot["camera"] = "two_shot"
    shot["place"]["lioness"] = {"spot": "doorway_out", "pose": "stand_point"}
    shot["beats"] = [{"at": 0.5, "show": BUBBLE}] if verb == "hide" else []
    shot["beats"].append({"at": 1.0, **_BASE[verb], **fields})
    return d


@ENGINES
def test_every_beat_field_is_read_or_rejected_per_engine(engine):
    from toon.scene import BEAT_OPTIONAL, VERBS

    caps = CATALOGS[engine].capabilities
    for verb in VERBS:
        for field in BEAT_OPTIONAL:
            if field in _BASE[verb]:
                continue
            extra = {"over": 1.0} if field in ("ease", "bob") and "over" in caps.beat_fields[verb] else {}
            data = _fence(engine, verb, **extra, **{field: _VALUE[field]})
            if field in caps.beat_fields[verb]:
                with_it = load_scene(data, CATALOGS[engine])
                without = load_scene(_fence(engine, verb, **extra), CATALOGS[engine])
                assert any(beats_at(with_it, t) != beats_at(without, t) for t in (1.0, 1.1, 1.3, 1.6, 2.5)), \
                    (engine, verb, field)
            else:
                with pytest.raises(SceneError, match=rf"beats\[\d\]\.{field}: "):
                    load_scene(data, CATALOGS[engine])


@ENGINES
def test_prop_flags_a_kind_ignores_are_rejected_per_engine(engine):
    catalog = CATALOGS[engine]
    caps = catalog.capabilities
    checked = 0
    for item in catalog.props:
        kind = catalog.prop_kind(item)
        uses = {"idea_bulb": {"on": "tim"}, "plate": {"held_by": "tim"}, "plate_stack": {"count": 6}}[kind]
        for flag, value in (("flicker", True), ("blink", {"b": 0.35, "over": 0.2}), ("out", True)):
            d = scene(engine, {"at": 1.0, "prop": "p", flag: value})
            d["shots"][0]["props"] = {"p": {"kind": item, **uses}}
            if flag in caps.prop_kinds[kind].flags:
                load_scene(d, catalog)
            else:
                with pytest.raises(SceneError, match=rf"beats\[0\]\.{flag}: an? {kind} prop ignores {flag}"):
                    load_scene(d, catalog)
            checked += 1
    assert checked == 3 * len(catalog.props)


@ENGINES
def test_inout_is_read_on_both_engines(engine):
    # S12-22: the inout ease is engine-neutral (beats_at computes it), so both engines take it.
    from toon.engine.mathx import EASES

    s = load_scene(scene(engine, {"at": 1.0, "door": "open", "over": 1.0, "ease": "inout"}), CATALOGS[engine])
    assert beats_at(s, 1.25).door == pytest.approx(EASES["inout"](0.25))
