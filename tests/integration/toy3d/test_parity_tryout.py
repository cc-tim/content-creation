"""E11 S12-18 (EM ruling D1, D3): the worked scene, rendered by the toy3d engine from the bank, matches
the frozen r7-3d snapshot's own renders at the 6 key times, and standing GuoGuo matches its design
view. The references were rendered by the snapshot's own code (hash-checked) on the pinned browser
on the Mac (Metal) and downscaled to 960×540 (`python -m tests.toy3d_snapshot refs`); PROVENANCE.md
records the build, the renderer and the tolerance's calibration. They are Mac-Metal references:
on another renderer the comparison is skipped, by name."""
import io
import json
import re
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from tests.toy3d_snapshot import DESIGN_VIEW, KEY_TIMES, downscale, ref_name

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[3]
REFS = REPO / "tests" / "fixtures" / "toy3d" / "tryout_ref"
EVIDENCE = REPO / "tmp" / "toy3d-v0" / "parity"
# The tolerance (PROVENANCE.md has the calibration): far below a 5° shoulder or a swapped decal.
MEAN, P999, FRAC8 = 0.1, 4.0, 0.0005


def _provenance():
    text = (REFS / "PROVENANCE.md").read_text()
    renderer = re.search(r"^- renderer: `(.+)`$", text, re.M).group(1)
    build = re.search(r"^- browser: Chrome for Testing `(.+)`", text, re.M).group(1)
    return renderer, build


@pytest.fixture(scope="module")
def page(bank):
    from toy3d import runtime

    renderer, build = _provenance()
    with runtime.open_page(1920, 1080, "render") as p:
        p.init(runtime.bank_payload(bank), 1920, 1080, "render")
        info = p.info()
        if info["renderer"] != renderer or info["build"] != build:
            pytest.skip(f"the references are {renderer} on {build}; this is {info['renderer']} on {info['build']}")
        yield p


def _compare(got: bytes, name: str) -> dict:
    a = np.asarray(Image.open(io.BytesIO(got)).convert("RGB")).astype(int)
    b = np.asarray(Image.open(REFS / name).convert("RGB")).astype(int)
    d = np.abs(a - b).max(axis=2)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / f"engine_{name}").write_bytes(got)
    return {"mean": float(d.mean()), "p999": float(np.percentile(d, 99.9)), "frac8": float((d > 8).mean()),
            "max": int(d.max())}


def _check(stats: dict, name: str) -> None:
    (EVIDENCE / f"{name}.json").write_text(json.dumps(stats))
    assert stats["mean"] <= MEAN and stats["p999"] <= P999 and stats["frac8"] <= FRAC8, f"{name}: {stats}"


@pytest.mark.parametrize("t", KEY_TIMES)
def test_worked_scene_matches_the_frozen_tryout(page, worked, bank, t):
    from toy3d.acting import resolve

    got = downscale(page.render_state(json.loads(json.dumps(resolve(worked, bank, t)))))
    _check(_compare(got, ref_name(t)), ref_name(t))


def test_standing_guoguo_matches_the_design_view(page, design, bank):
    from toy3d.acting import resolve

    shot, t = DESIGN_VIEW
    got = downscale(page.render_state(json.loads(json.dumps(resolve(design, bank, t)))))
    _check(_compare(got, ref_name(t, shot)), ref_name(t, shot))


def test_the_references_are_the_snapshots_key_frames():
    names = sorted(p.name for p in REFS.glob("*.png"))
    assert names == sorted([ref_name(t) for t in KEY_TIMES] + [ref_name(DESIGN_VIEW[1], DESIGN_VIEW[0])])
    for p in REFS.glob("*.png"):
        assert Image.open(p).size == (960, 540), p.name
