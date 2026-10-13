"""E11 S12-7 (runtime) and P2-R9: the look is bank data, and the page reads it. Changing the
exposure, one palette colour or the bloom strength changes the pixels; a bad colour, a missing key
or a key the engine never reads fails init loudly, with the bank path in the error."""
import copy
import io
import json

import numpy as np
import pytest
from PIL import Image

pytestmark = pytest.mark.integration

W, H = 480, 270


def _render(payload, spec):
    from toy3d import runtime

    with runtime.open_page(W, H, "render") as page:
        page.init(payload, W, H, "render")
        return np.asarray(Image.open(io.BytesIO(page.render_state(spec))).convert("RGB")).astype(int)


@pytest.fixture(scope="module")
def spec(worked, bank):
    from toy3d.acting import resolve

    return json.loads(json.dumps(resolve(worked, bank, 4.0)))      # the bulb is lit: bloom shows


@pytest.fixture(scope="module")
def payload(bank):
    from toy3d.runtime import bank_payload

    return bank_payload(bank)


@pytest.fixture(scope="module")
def base(payload, spec):
    return _render(payload, spec)


def _with(payload, path, value):
    p = copy.deepcopy(payload)
    node = p
    for k in path[:-1]:
        node = node[k]
    node[path[-1]] = value
    return p


@pytest.mark.parametrize(("path", "value"), [
    (("style", "tone", "exposure"), 1.3),
    (("sets", "office", "palette", "wall"), "#4060a0"),
    (("style", "post", "bloom", "strength"), 2.0),
], ids=["exposure", "palette colour", "bloom strength"])
def test_style_values_change_pixels(payload, spec, base, path, value):
    got = _render(_with(payload, path, value), spec)
    assert np.abs(got - base).max(axis=2).mean() > 0.5, f"{'.'.join(path)} changed nothing"


def test_the_same_bank_renders_the_same_pixels(payload, spec, base):
    assert np.array_equal(_render(payload, spec), base)


@pytest.mark.parametrize(("path", "value", "message"), [
    (("sets", "office", "palette", "wall"), "#zzzzzz", "sets/office.yaml palette.wall: not a colour '#zzzzzz'"),
    (("characters", "tim", "palette", "skin"), None, "characters/tim.yaml palette.skin is missing"),
    (("props", "idea_bulb", "params", "spare"), 1.0, "the engine never reads props/idea_bulb.yaml params.spare"),
], ids=["bad colour", "missing key", "unread key"])
def test_a_bad_bank_value_fails_init_loudly(payload, path, value, message):
    from toy3d import runtime

    p = _with(payload, path, value)
    if value is None:
        node = p
        for k in path[:-1]:
            node = node[k]
        del node[path[-1]]
    with runtime.open_page(W, H, "render") as page, pytest.raises(runtime.Toy3DRenderError) as e:
        page.init(p, W, H, "render")
    assert message in str(e.value)
