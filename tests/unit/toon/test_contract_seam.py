"""E11 Sprint 12 phase 1: one scene contract, checked against any engine's catalog."""
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


_FENCED = ("toon.bank", "toon.kit", "toon.engine", "toon.render", "toon.timeline", "cairo", "cairocffi")


def test_scene_module_does_not_import_the_2d_bank():
    # The contract must not depend on one engine's bank or kit (spec §4.1); function-level
    # imports (e.g. scenes_root) are allowed.
    tree = ast.parse((Path(toon.__file__).parent / "scene.py").read_text())
    names = [a.name for n in tree.body if isinstance(n, ast.Import) for a in n.names]
    names += [n.module or "" for n in tree.body if isinstance(n, ast.ImportFrom)]
    assert not [m for m in names if m.startswith(_FENCED)]


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
