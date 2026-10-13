"""E11 S12-4: the engine-neutral symbolic timeline, and the 2.5D state_at built on it."""
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
    # A move, then a face aimed at the mover's *current* position, and two overlapping poses fold
    # exactly as the pre-split loop did (values measured on the sprint base 5d0f9b3).
    from toon.timeline import state_at

    d = copy.deepcopy(BASE)
    d["shots"][0]["beats"] += [{"at": 1.2, "face": "tim", "to": "lioness", "over": 0.5},
                               {"at": 1.4, "pose": "tim", "to": "sit_typing", "over": 0.5, "ease": "linear"}]
    fs = state_at(load_scene(d, BANK), BANK, 1.6)
    assert (fs.chars["tim"].yaw, fs.chars["tim"].pose.lean) == (-103.38238005032606, 6.000000000000004)


# -- S12-22 (EM ruling D2): the only new authored field is the inout ease; time since start is
# internal beats_at data --

def test_inout_ease_is_the_tryouts_cubic_in_out():
    from toon.engine.mathx import EASES
    from toon.timeline import beats_at

    for x in (0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0):    # the snapshot's `ease` (scene.js line 22)
        assert EASES["inout"](x) == (4 * x * x * x if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2)
    d = copy.deepcopy(MINI)
    d["shots"][0]["beats"] = [{"at": 1.0, "door": "open", "over": 1.0, "ease": "inout"}]
    assert beats_at(load_scene(d, BANK), 1.25).door == pytest.approx(EASES["inout"](0.25))


def test_beats_at_carries_time_since_start():
    from toon.timeline import DoorAt, beats_at

    sym = beats_at(load_scene(copy.deepcopy(BASE), BANK), 1.5)
    assert [(c.since, c.over) for c in sym.changes] == [(0.5, 1.0), (0.5, 1.0)]
    assert sym.door_at == DoorAt(value=0.5, to="open", since=0.5, over=1.0)
    later = beats_at(load_scene(copy.deepcopy(BASE), BANK), 5.2)            # shot 2, rel 1.2
    idea = next(p for p in later.props if p.name == "idea")
    assert idea.since == pytest.approx(0.2)                                  # its out beat at 1.0
    assert beats_at(load_scene(copy.deepcopy(MINI), BANK), 0.5).door_at is None


def test_state_at_folds_a_face_before_a_later_move():
    # A3 I2: a face that starts *before* a move aims where the fold has the mover so far ("faces
    # fold last" would aim at the final position). Values measured at 5d0f9b3 (045e47e: the same).
    from toon.timeline import state_at

    d = {"id": "t", "duration": 8.0, "cast": {"tim": "tim", "lioness": "lioness"},
         "shots": [{"at": 0.0, "set": "office", "camera": "two_shot",
                    "place": {"tim": {"spot": "desk_seat", "pose": "sit_typing"},
                              "lioness": {"spot": "doorway_out", "pose": "stand_point"}},
                    "beats": [{"at": 0.5, "face": "tim", "to": "lioness", "over": 1.0, "ease": "linear"},
                              {"at": 1.0, "move": "lioness", "to": "doorway", "over": 1.0, "ease": "linear"},
                              {"at": 1.2, "face": "lioness", "to": "tim", "over": 0.5},
                              {"at": 1.4, "move": "lioness", "to": "doorway_out", "over": 1.0}]}]}
    s = load_scene(d, BANK)
    want = {1.3: (-97.79397427129865, 40.369455209482545), 1.8: (-122.24246783912331, 57.295511437773015),
            2.6: (-122.24246783912331, 38.0)}
    for t, (tim, lioness) in want.items():
        fs = state_at(s, BANK, t)
        assert (fs.chars["tim"].yaw, fs.chars["lioness"].yaw) == (pytest.approx(tim, rel=1e-12),
                                                                    pytest.approx(lioness, rel=1e-12)), t
