"""E11 Sprint 12 phase 1: one scene contract, checked against any engine's catalog."""
import copy

import pytest

from tests.unit.toon.catalogs import TOY3D_TEST
from tests.unit.toon.test_scene import BANK, MINI
from toon.scene import SceneError, load_scene


def test_load_scene_takes_any_catalog():
    from toon.catalog import SceneCatalog

    assert isinstance(BANK, SceneCatalog) and isinstance(TOY3D_TEST, SceneCatalog)
    assert load_scene(copy.deepcopy(MINI), BANK).engine == "toon2d"          # the 2.5D bank adapts
    assert load_scene({**copy.deepcopy(MINI), "engine": "toy3d"}, TOY3D_TEST).engine == "toy3d"
    bad = {**copy.deepcopy(MINI), "engine": "toy3d"}
    bad["shots"][0]["place"]["tim"]["pose"] = "moonwalk"                     # names come from it
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


_FENCED = ("toon.bank", "toon.kit", "toon.engine", "toon.render", "toon.timeline", "toon.cairo_compat",
           "cairo", "cairocffi", "numpy")


def test_the_contract_and_the_symbolic_timeline_load_no_2d_engine_code():
    # The contract (scene) and the engine-neutral timeline (beats) must not pull in one engine's
    # bank, kit or drawing stack (spec §4.1; A3 m2): checked in a fresh interpreter.
    import subprocess
    import sys

    code = ("import sys, toon.scene, toon.beats; "
            f"print(sorted(m for m in sys.modules if m.startswith({_FENCED!r})))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]", out.stdout


# -- S12-2: "means what it renders" is engine-relative --

# What toy3d (v0) doesn't render but toon2d does: each must fail on toy3d, naming the engine.
_TOY3D_GAPS = [
    ({"boil": "still"}, None, r"^boil: toy3d doesn't render boil \(toon2d does\)"),
    (None, {"place": {"tim": {"spot": "desk_seat", "pose": "sit_typing", "layer": "split"}}},
     r"shots\[0\]\.place\.tim\.layer: toy3d doesn't render layer \(toon2d does\)"),
    (None, {"fx": [{"glow": {"at": [0, 2, 0], "radius": 1, "color": "warm", "alpha": 0.3}}]},
     r"shots\[0\]\.fx\[0\]\.glow: toy3d doesn't render glow fx \(toon2d does\)"),
    (None, {"beats": [{"at": 1.0, "show": {"anger": "tim"}}]},
     r"shots\[0\]\.beats\[0\]\.show\.anger: toy3d doesn't render anger shows \(toon2d does\)"),
    (None, {"beats": [{"at": 1.0, "move": "tim", "to": "doorway", "over": 1.0, "bob": 0.1}]},
     r"shots\[0\]\.beats\[0\]\.bob: toy3d doesn't render bob on a move beat \(toon2d does\)"),
]


@pytest.mark.parametrize("scene_change, shot_change, path", _TOY3D_GAPS)
def test_field_the_engine_does_not_render_fails_naming_the_engine(scene_change, shot_change, path):
    d = {**copy.deepcopy(MINI), **(scene_change or {})}
    d["shots"][0].update(copy.deepcopy(shot_change or {}))
    load_scene(copy.deepcopy(d), BANK)                                   # toon2d renders it
    with pytest.raises(SceneError, match=path):
        load_scene({**d, "engine": "toy3d"}, TOY3D_TEST)


@pytest.mark.parametrize("engine", ["toon2d", "toy3d"])
def test_a_verb_or_prop_kind_the_engine_lacks_fails_naming_the_engine(engine):
    # Both v0 engines render every verb and the idea bulb, so narrowed copies of each engine's
    # real table prove the check per engine.
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



# -- A3 I3: names are checked per character (the cast name is not the character) --

def _wife(place=None, beats=()):
    d = copy.deepcopy(MINI)
    d["engine"] = "toy3d"
    d["cast"] = {"tim": "tim", "wife": "lioness"}
    d["shots"][0]["place"]["wife"] = place or {"spot": "doorway_out", "pose": "stand_point", "expr": "angry"}
    d["shots"][0]["beats"] = list(beats)
    return d


def test_a_cast_name_is_checked_as_its_character():
    load_scene(_wife(), TOY3D_TEST)                                        # the lioness's pose and face
    bad = _wife()
    bad["shots"][0]["place"]["tim"]["expr"] = "angry"                      # the lioness's, not Tim's
    with pytest.raises(SceneError, match=r"place\.tim\.expr: unknown expression 'angry'"):
        load_scene(bad, TOY3D_TEST)
    with pytest.raises(SceneError, match=r"place\.wife\.pose: unknown pose 'sit_typing'"):
        load_scene(_wife({"spot": "doorway_out", "pose": "sit_typing", "expr": "angry"}), TOY3D_TEST)


def test_a_pose_beat_is_checked_as_its_character():
    load_scene(_wife(beats=[{"at": 1.0, "pose": "wife", "expr": "neutral"}]), TOY3D_TEST)
    with pytest.raises(SceneError, match=r"beats\[0\]\.to: unknown pose 'sit_typing'"):
        load_scene(_wife(beats=[{"at": 1.0, "pose": "wife", "to": "sit_typing"}]), TOY3D_TEST)
    with pytest.raises(SceneError, match=r"beats\[0\]\.expr: unknown expression 'angry'"):
        load_scene(_wife(beats=[{"at": 1.0, "pose": "tim", "expr": "angry"}]), TOY3D_TEST)


def test_an_unknown_character_is_one_problem_not_a_cascade():
    # A3 m4: the per-character checks are skipped when the character itself is unknown.
    d = _wife(beats=[{"at": 1.0, "pose": "wife", "to": "stand_point"}])
    d["cast"]["wife"] = "tigress"
    with pytest.raises(SceneError) as e:
        load_scene(d, TOY3D_TEST)
    assert e.value.problems == ["cast.wife: unknown character 'tigress' (bank has ['lioness', 'tim'])"]


def test_a_field_no_engine_reads_on_that_verb_says_which_verb_does():
    # A3 m4: bob on a pose beat isn't fixed by switching engines; say who reads bob, and on what.
    d = copy.deepcopy(MINI)
    d["engine"] = "toy3d"
    d["shots"][0]["beats"] = [{"at": 1.0, "pose": "tim", "to": "sit_shock", "over": 0.5, "bob": 0.1}]
    with pytest.raises(SceneError) as e:
        load_scene(d, TOY3D_TEST)
    assert "shots[0].beats[0].bob: toy3d doesn't render bob (toon2d reads it on a move beat)" in e.value.problems


def test_toy3d_takes_the_place_fields_its_table_lists():
    # A3 m3: loop is in toy3d's place_fields; a loop: false placement loads and reaches beats_at.
    from toon.timeline import beats_at

    d = copy.deepcopy(MINI)
    d["engine"] = "toy3d"
    d["shots"][0]["place"]["tim"]["loop"] = False
    (tim,) = beats_at(load_scene(d, TOY3D_TEST), 1.0).actors
    assert tim.loop is False


def test_the_render_field_lists_are_the_models_optional_render_fields():
    # A3 m6: a new optional render field can't skip the engine check.
    from toon.scene import PLACE_RENDER_FIELDS, SCENE_RENDER_FIELDS, Place, ToonScene

    optional = {f for f, info in ToonScene.model_fields.items() if info.default is None} - {"duration"}
    assert set(SCENE_RENDER_FIELDS) == optional
    assert set(PLACE_RENDER_FIELDS) == {f for f, info in Place.model_fields.items() if info.default is None}


def test_the_2d_renderer_refuses_a_toy3d_scene(tmp_path):
    # A3 m1: the 2.5D engine never draws a toy3d scene, whoever calls it.
    from toon import render, timeline

    toy = load_scene({**copy.deepcopy(MINI), "engine": "toy3d"}, TOY3D_TEST)
    for call in (lambda: render.frame(toy, BANK, 1.0, 64, 36),
                 lambda: render.render_clip(toy, BANK, tmp_path / "x.mp4", 1.0, 64, 36),
                 lambda: timeline.state_at(toy, BANK, 1.0)):
        with pytest.raises(render.ToonRenderError, match="a toy3d scene; the 2.5D engine draws toon2d scenes"):
            call()
