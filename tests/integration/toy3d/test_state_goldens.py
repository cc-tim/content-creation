"""E11 S12-7 (runtime), S12-11 Layer B, S12-23 (JS half): the page applies frame specs to its
scene graph exactly as the frozen snapshot poses its own. The goldens are the snapshot's named node
world matrices and render states at the key times (`python -m tests.toy3d_snapshot nodes`), so a
wrong joint, pivot, seat, decal, bulb or bubble mapping fails here without a pixel. State mode
builds no WebGL context."""
import json
from pathlib import Path

import pytest

from tests.unit.toy3d.test_state_symbolic import PROBES, _probe_scene

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[3]
GOLDEN = REPO / "tests" / "fixtures" / "toy3d" / "state" / "node_matrices.json"
TOL = 1e-6
COUNT_CONTEXTS = """
window.__contexts = [];
const _getContext = HTMLCanvasElement.prototype.getContext;
HTMLCanvasElement.prototype.getContext = function (kind, ...rest) {
  window.__contexts.push(kind);
  return _getContext.call(this, kind, ...rest);
};
"""


@pytest.fixture(scope="module")
def state_page(bank):
    from toy3d import runtime

    with runtime.open_page(1920, 1080, "state", init_script=COUNT_CONTEXTS) as page:
        page.init(runtime.bank_payload(bank), 1920, 1080, "state")
        yield page


def _spec(scene, bank, t):
    from toy3d.acting import resolve

    return json.loads(json.dumps(resolve(scene, bank, t)))


def test_apply_state_creates_no_webgl_context_in_state_mode(state_page, worked, bank):
    state_page.apply_state(_spec(worked, bank, 4.0))
    kinds = state_page.evaluate("() => window.__contexts")
    assert kinds and set(kinds) == {"2d"}, kinds                  # the canvases only, never webgl
    assert state_page.info()["renderer"] is None


def _diff(got, want, where):
    bad = []
    if set(got) != set(want):
        bad.append(f"{where}: keys differ: extra {sorted(set(got) - set(want))}, missing {sorted(set(want) - set(got))}")
    for k in sorted(set(got) & set(want)):
        g, w = got[k], want[k]
        if isinstance(w, list):
            err = max(abs(a - b) for a, b in zip(g, w, strict=True))
            if err > TOL:
                bad.append(f"{where} {k}: off by {err:.3g}")
        elif isinstance(w, float) and not isinstance(w, bool):
            if abs(g - w) > TOL:
                bad.append(f"{where} {k}: {g} != {w}")
        elif g != w:
            bad.append(f"{where} {k}: {g!r} != {w!r}")
    return bad


def test_applied_world_matrices_match_goldens(state_page, worked, design, bank):
    want = json.loads(GOLDEN.read_text())
    bad = []
    for key, nodes in want.items():
        name, t = key.split("@")
        scene = design if name == "guo" else worked
        bad += _diff(state_page.apply_state(_spec(scene, bank, float(t))), nodes, key)
    assert not bad, "\n".join(bad[:20])


@pytest.mark.parametrize("entry", sorted(PROBES, key=str), ids=lambda e: ".".join(e))
def test_every_toy3d_capability_is_rendered(state_page, bank, entry):
    base, variant, patch, t = PROBES[entry]
    a = state_page.apply_state(_spec(_probe_scene(bank, base, {}), bank, t))
    b = state_page.apply_state(_spec(_probe_scene(bank, variant, patch), bank, t))
    assert a != b, f"{entry}: the page applied the same world"
