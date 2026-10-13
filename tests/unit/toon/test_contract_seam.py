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
