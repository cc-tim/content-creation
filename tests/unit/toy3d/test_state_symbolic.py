"""E11 S12-11 Layer A and S12-23 (Python half): the worked scene's frame specs at the key times are
pinned as JSON, and every entry in the toy3d capability table changes the frame spec: an engine
that would accept a field and ignore it fails here (Ruling 3)."""
import json
import os
from pathlib import Path

import pytest

from .test_acting import _diff

REPO = Path(__file__).resolve().parents[3]
WORKED = REPO / "assets" / "toy3d" / "scenes" / "001-beat2-break-in.yaml"
DESIGN_VIEW = REPO / "tests" / "fixtures" / "toy3d" / "sheet" / "guo_design_view.yaml"
GOLDEN = REPO / "tests" / "fixtures" / "toy3d" / "state" / "frame_specs.json"
KEY_TIMES = (0.6, 2.4, 3.3, 4.0, 5.3, 7.0)


@pytest.fixture(scope="module")
def bank():
    from toy3d.bank import load_bank

    return load_bank()


def _specs(bank):
    from toon.scene import load_scene, read_scene
    from toy3d.acting import resolve

    worked = load_scene(read_scene(str(WORKED)), bank.catalog)
    design = load_scene(read_scene(str(DESIGN_VIEW)), bank.catalog)
    out = {f"worked@{t}": resolve(worked, bank, t) for t in KEY_TIMES}
    out["guo_design_view@0.714"] = resolve(design, bank, 0.714)
    return json.loads(json.dumps(out))


def test_worked_scene_frame_specs_match_golden(bank):
    """Pure Python, so the same on both machines (to 1e-9: libm may differ in the last bit)."""
    got = _specs(bank)
    if os.environ.get("UPDATE_GOLDENS") == "1":
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps(got, indent=1, sort_keys=True) + "\n")
        pytest.skip(f"minted {GOLDEN.relative_to(REPO)}")
    want = json.loads(GOLDEN.read_text())
    assert set(got) == set(want)
    bad = _diff(got, want) + _diff(want, got)                         # no key added or dropped
    assert not bad, bad[:12]


# -- Ruling 3: every capability-table entry is rendered --

BASE_PLACE = {"tim": {"spot": "desk_seat", "pose": "typing", "expr": "neutral"},
              "lioness": {"spot": "doorway_in", "pose": "stand", "expr": "stern"},
              "guoguo": {"spot": "shelf_top", "pose": "seated", "expr": "neutral"}}
BASE_PROPS = {"idea": {"kind": "idea_bulb", "on": "tim", "b": 1.0}}
SHOW = {"at": 0.5, "show": {"bubble": ["dishes", "bang"], "from": "lioness"}}

# Each probe: (base beats, variant beats, variant place/props patch, probe time). The variant differs
# from the base only by the capability, so the spec must differ.
PROBES = {
    ("verb", "door"): ([], [{"at": 0.5, "door": "open"}], {}, 1.0),
    ("verb", "move"): ([], [{"at": 0.5, "move": "lioness", "to": "doorway_out"}], {}, 1.0),
    ("verb", "pose"): ([], [{"at": 0.5, "pose": "lioness", "to": "point"}], {}, 1.0),
    ("verb", "face"): ([], [{"at": 0.5, "face": "lioness", "to": "tim"}], {}, 1.0),
    ("verb", "prop"): ([], [{"at": 0.5, "prop": "idea", "to": {"b": 0.3}}], {}, 1.0),
    ("verb", "show"): ([], [SHOW], {}, 1.0),
    ("verb", "hide"): ([SHOW], [SHOW, {"at": 0.8, "hide": "bubble:lioness"}], {}, 1.0),
    ("verb", "camera"): ([], [{"at": 0.5, "camera": "closeup"}], {}, 1.0),
    ("field", "door", "over"): ([{"at": 0.5, "door": "open"}], [{"at": 0.5, "door": "open", "over": 1.0}], {}, 1.0),
    ("field", "door", "ease"): ([{"at": 0.5, "door": "open", "over": 1.0}],
                                [{"at": 0.5, "door": "open", "over": 1.0, "ease": "linear"}], {}, 0.8),
    ("field", "move", "to"): ([{"at": 0.5, "move": "lioness", "to": "doorway_out"}],
                              [{"at": 0.5, "move": "lioness", "to": "turntable"}], {}, 1.0),
    ("field", "move", "over"): ([{"at": 0.5, "move": "lioness", "to": "turntable"}],
                                [{"at": 0.5, "move": "lioness", "to": "turntable", "over": 1.0}], {}, 1.0),
    ("field", "move", "ease"): ([{"at": 0.5, "move": "lioness", "to": "turntable", "over": 1.0}],
                                [{"at": 0.5, "move": "lioness", "to": "turntable", "over": 1.0, "ease": "linear"}],
                                {}, 0.8),
    ("field", "pose", "to"): ([{"at": 0.5, "pose": "lioness", "to": "point"}],
                              [{"at": 0.5, "pose": "lioness", "to": "akimbo"}], {}, 1.0),
    ("field", "pose", "expr"): ([{"at": 0.5, "pose": "tim", "to": "typing"}],
                                [{"at": 0.5, "pose": "tim", "to": "typing", "expr": "shock"}], {}, 1.0),
    ("field", "pose", "over"): ([{"at": 0.5, "pose": "lioness", "to": "point"}],
                                [{"at": 0.5, "pose": "lioness", "to": "point", "over": 1.0}], {}, 1.0),
    ("field", "pose", "ease"): ([{"at": 0.5, "pose": "lioness", "to": "point", "over": 1.0}],
                                [{"at": 0.5, "pose": "lioness", "to": "point", "over": 1.0, "ease": "linear"}],
                                {}, 0.8),
    ("field", "face", "to"): ([{"at": 0.5, "face": "lioness", "to": "tim"}],
                              [{"at": 0.5, "face": "lioness", "to": "guoguo"}], {}, 1.0),
    ("field", "face", "over"): ([{"at": 0.5, "face": "lioness", "to": "tim"}],
                                [{"at": 0.5, "face": "lioness", "to": "tim", "over": 1.0}], {}, 1.0),
    ("field", "face", "ease"): ([{"at": 0.5, "face": "lioness", "to": "tim", "over": 1.0}],
                                [{"at": 0.5, "face": "lioness", "to": "tim", "over": 1.0, "ease": "linear"}], {}, 0.8),
    ("field", "prop", "to"): ([{"at": 0.5, "prop": "idea", "to": {"b": 0.3}}],
                              [{"at": 0.5, "prop": "idea", "to": {"b": 0.6}}], {}, 1.0),
    ("field", "prop", "over"): ([{"at": 0.5, "prop": "idea", "to": {"b": 0.3}}],
                                [{"at": 0.5, "prop": "idea", "to": {"b": 0.3}, "over": 1.0}], {}, 1.0),
    ("field", "prop", "ease"): ([{"at": 0.5, "prop": "idea", "to": {"b": 0.3}, "over": 1.0}],
                                [{"at": 0.5, "prop": "idea", "to": {"b": 0.3}, "over": 1.0, "ease": "linear"}],
                                {}, 0.8),
    ("field", "prop", "flicker"): ([], [{"at": 0.5, "prop": "idea", "flicker": True}], {}, 1.0),
    ("field", "prop", "blink"): ([], [{"at": 0.5, "prop": "idea", "blink": {"b": 0.1, "over": 1.0}}], {}, 1.0),
    ("field", "prop", "out"): ([], [{"at": 0.5, "prop": "idea", "out": True}], {}, 1.0),
    ("field", "show", "over"): ([SHOW], [{**SHOW, "over": 1.0}], {}, 0.6),
    ("prop_kind", "idea_bulb", "draws", "on"): ([], [], {"props": {"idea": {**BASE_PROPS["idea"], "on": "lioness"}}},
                                                1.0),
    ("prop_kind", "idea_bulb", "draws", "b"): ([], [], {"props": {"idea": {**BASE_PROPS["idea"], "b": 0.5}}}, 1.0),
    ("prop_kind", "idea_bulb", "states", "b"): ([], [{"at": 0.5, "prop": "idea", "to": {"b": 0.3}}], {}, 1.0),
    ("show_kind", "bubble"): ([], [SHOW], {}, 1.0),
    ("place", "loop"): ([], [], {"place": {**BASE_PLACE, "tim": {**BASE_PLACE["tim"], "loop": False}}}, 1.0),
}
for _flag in ("flicker", "blink", "out"):
    PROBES[("prop_kind", "idea_bulb", "flags", _flag)] = PROBES[("field", "prop", _flag)]


def _capability_entries():
    from toon.catalog import TOY3D

    keys = {("verb", v) for v in TOY3D.verbs}
    keys |= {("field", verb, f) for verb, fields in TOY3D.beat_fields.items() for f in fields}
    for kind, spec in TOY3D.prop_kinds.items():
        keys |= {("prop_kind", kind, "draws", f) for f in spec.draws}
        keys |= {("prop_kind", kind, "states", f) for f in spec.states}
        keys |= {("prop_kind", kind, "flags", f) for f in spec.flags}
    keys |= {("show_kind", k) for k in TOY3D.show_kinds}
    keys |= {("place", f) for f in TOY3D.place_fields}
    keys |= {("fx", f) for f in TOY3D.fx_kinds} | {("scene", f) for f in TOY3D.scene_fields}
    return keys


def test_every_toy3d_capability_has_a_probe():
    missing = _capability_entries() - set(PROBES)
    assert not missing, f"toy3d's capability table has entries no probe renders: {sorted(missing)}"


def _probe_scene(bank, beats, patch):
    from toon.scene import load_scene

    shot = {"at": 0.0, "set": "office", "camera": "beat2", "place": patch.get("place", BASE_PLACE),
            "props": patch.get("props", BASE_PROPS), "beats": beats}
    return load_scene({"id": "probe", "engine": "toy3d", "duration": 3.0,
                       "cast": {"tim": "tim", "lioness": "lioness", "guoguo": "guoguo"}, "shots": [shot]},
                      bank.catalog)


@pytest.mark.parametrize("entry", sorted(PROBES, key=str), ids=lambda e: ".".join(e))
def test_every_toy3d_capability_changes_the_frame_spec(bank, entry):
    from toy3d.acting import resolve

    base, variant, patch, t = PROBES[entry]
    a = resolve(_probe_scene(bank, base, {}), bank, t)
    b = resolve(_probe_scene(bank, variant, patch), bank, t)
    assert json.dumps(a, sort_keys=True) != json.dumps(b, sort_keys=True), f"{entry} changes nothing at t={t}"
