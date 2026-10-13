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
