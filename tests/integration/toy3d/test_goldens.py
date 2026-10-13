"""E11 S12-12, Layer C: pixel goldens of the worked scene's key frames and the cast model sheet,
960×540, hub-canonical, compared on both machines with the tolerant helper. PROVENANCE.md records
the build, both renderer strings, the noise floor and how the limits sit between it and the
sensitivity set below, which must fail on either machine."""
import copy
import io
import json
from contextlib import contextmanager
from pathlib import Path

import pytest
from PIL import Image

from tests.golden_policy import assert_close_to_golden
from tests.toy3d_snapshot import KEY_TIMES, downscale

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[3]
GOLDENS = REPO / "tests" / "fixtures" / "toy3d" / "goldens"
# Per view (the calibration is in PROVENANCE.md). GuoGuo's fur shells differ most between GPUs, so
# his design view has its own, wider limits; it is also where halving the shells shows.
FRAME = {"mean": 0.6, "p999": 16.0, "max_frac": 0.0013, "tile": 15.0}
GUO = {"mean": 0.6, "p999": 48.0, "max_frac": 0.004, "tile": 15.0}


def _png(page, spec) -> Image.Image:
    return Image.open(io.BytesIO(downscale(page.render_state(json.loads(json.dumps(spec))))))


def _views(worked, design):
    from toy3d.sheet import sheet_views

    out = {f"worked@{t:.3f}": (worked, t, FRAME) for t in KEY_TIMES}
    for name, scene, t in sheet_views(worked, design):
        out[f"sheet_{name}"] = (scene, t, GUO if name == "guo_34" else FRAME)
    return out


@contextmanager
def _page(payload):
    from toy3d import runtime

    with runtime.open_page(1920, 1080, "render") as p:
        p.init(payload, 1920, 1080, "render")
        yield p


@pytest.fixture
def page(bank):
    """Per test: a bank-variant test opens its own page, and two sync Playwrights can't overlap."""
    from toy3d.runtime import bank_payload

    with _page(bank_payload(bank)) as p:
        yield p


def test_layer_c_goldens(page, worked, design, bank):
    from toy3d.acting import resolve

    for name, (scene, t, limits) in _views(worked, design).items():
        assert_close_to_golden(_png(page, resolve(scene, bank, t)), GOLDENS / f"{name}.png", **limits)


def _sensitive(img, name, limits):
    with pytest.raises(AssertionError, match="beyond tolerance"):
        assert_close_to_golden(img, GOLDENS / f"{name}.png", **limits)


def test_a_swapped_decal_on_the_close_up_fails(page, worked, design, bank):
    from toy3d.acting import resolve

    scene, t, limits = _views(worked, design)["sheet_closeup"]
    s = resolve(scene, bank, t)
    assert s["actors"]["tim"]["face"] == "tim_shock"
    s["actors"]["tim"]["face"] = "tim_neutral"
    _sensitive(_png(page, s), "sheet_closeup", limits)


def test_a_five_degree_shoulder_fails(page, worked, bank):
    from toy3d.acting import resolve

    s = resolve(worked, bank, 4.0)
    s["actors"]["tim"]["joints"]["arm_r.j1.rz"] += 0.0872665
    _sensitive(_png(page, s), "worked@4.000", FRAME)


def test_guoguo_hidden_fails(page, worked, bank):
    from toy3d.acting import resolve

    s = resolve(worked, bank, 2.4)
    del s["actors"]["guoguo"]
    _sensitive(_png(page, s), "worked@2.400", FRAME)


def test_one_material_colour_fails(worked, bank):
    from toy3d.acting import resolve
    from toy3d.runtime import bank_payload

    p = copy.deepcopy(bank_payload(bank))
    p["characters"]["lioness"]["palette"]["dress"] = "#b4a8c6"            # lavender, a touch warmer
    with _page(p) as page:
        _sensitive(_png(page, resolve(worked, bank, 4.0)), "worked@4.000", FRAME)


def test_the_fur_shells_halved_fails(worked, design, bank):
    from toy3d.acting import resolve
    from toy3d.runtime import bank_payload

    p = copy.deepcopy(bank_payload(bank))
    p["characters"]["guoguo"]["params"]["fur"]["shells"] //= 2
    scene, t, limits = _views(worked, design)["sheet_guo_34"]
    with _page(p) as page:
        _sensitive(_png(page, resolve(scene, bank, t)), "sheet_guo_34", limits)
