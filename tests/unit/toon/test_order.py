"""Draw-order unit tests (design spec sec8 engine row, sec9 top risk: "the draw order is
heuristic"). Previously covered only by an --integration parity test against a tryout file
that isn't in git; these pin the three rules directly.

Each test is written so it FAILS when its rule is disabled in the source (see the EM
rework report for the RED/GREEN evidence -- the disabling edits themselves are never
committed).
"""
from __future__ import annotations

import pytest

import toon.engine.order as order
import toon.kit.sets as sets_mod
from toon.bank import load_bank
from toon.cairo_compat import cairo
from toon.engine.camera import orbit
from toon.engine.mathx import V
from toon.engine.order import character_parts, run
from toon.engine.rig import HIP_SIT
from toon.render import draw_frame
from toon.scene import load_scene
from toon.timeline import pose_of, state_at

BANK = load_bank()
# Same framing as the bank's "two_shot" preset (scene 001, beat 2): a plain frontal office
# view, not tuned to any one test.
CAM = orbit(az=-14, el=9, dist=26, target=V(-1.0, 2.7, -0.2), focal=3050)


# ---- (a) arm tuck: a hand near the face pulls its arm behind the (oversized) head ----
# src/toon/engine/order.py:32-33


def test_tucked_arm_draws_behind_the_head_when_the_hand_is_near_the_face(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(order, "draw_head", lambda *a, **k: calls.append("head"))
    monkeypatch.setattr(order, "draw_arm", lambda pen, cam, rg, side: calls.append(f"arm_{side}"))

    pose = pose_of(BANK, "sit_shock", "shocked")  # hand_l/hand_r y=3.3: at/above the face
    parts, _rg = character_parts(None, CAM, None, pose, HIP_SIT, 0.0, 0.0, HIP_SIT)
    run(parts.high)

    # run() paints large-depth (far) items first: a tucked arm is pushed to
    # depth >= head_depth + 0.02, so it is drawn BEFORE draw_head, which then paints over it.
    assert calls.index("arm_l") < calls.index("head")
    assert calls.index("arm_r") < calls.index("head")


def test_untucked_arm_keeps_its_own_depth_when_the_hand_is_low():
    pose = pose_of(BANK, "sit_typing", "focused")  # hand_l/hand_r y~2.25-2.28: well below the face
    parts, rg = character_parts(None, CAM, None, pose, HIP_SIT, 0.0, 0.0, HIP_SIT)
    head_depth = parts.high[0][0]
    arm_l_depth, arm_r_depth = parts.high[1][0], parts.high[2][0]
    sh_l, _, h_l = rg["arms"]["l"]
    sh_r, _, h_r = rg["arms"]["r"]
    # the tuck condition is false for this pose: the registered depth is exactly the raw
    # shoulder/hand midpoint depth, never clamped to head_depth + 0.02.
    assert arm_l_depth == pytest.approx(CAM.depth((sh_l + h_l) / 2))
    assert arm_r_depth == pytest.approx(CAM.depth((sh_r + h_r) / 2))
    assert arm_l_depth != pytest.approx(head_depth + 0.02)
    assert arm_r_depth != pytest.approx(head_depth + 0.02)


# ---- (b) desk mid-layer sandwich: the desk top draws over a seated character's legs/torso,
# under its head/arms -- render.draw_frame runs "low" (legs+torso, + the set's low layer),
# then unconditionally draws the set's "mid" layer (the desk top), then runs "high"
# (head+arms, + the set's high layer). src/toon/render.py:85-96, src/toon/kit/sets.py:156 ----


def _office_scene(cast_name, character, spot, pose, expr, layer=None):
    place = {"spot": spot, "pose": pose, "expr": expr}
    if layer is not None:
        place["layer"] = layer
    data = {"id": "order-test", "cast": {cast_name: character},
            "shots": [{"at": 0.0, "set": "office", "camera": "two_shot", "place": {cast_name: place}}]}
    return load_scene(data, BANK)


def _draw_calls(scene, monkeypatch, width=160, height=90):
    calls: list[str] = []
    monkeypatch.setattr(order, "draw_leg", lambda pen, cam, rg, side: calls.append("leg"))
    monkeypatch.setattr(order, "draw_torso", lambda pen, cam, rg, look: calls.append("torso"))
    monkeypatch.setattr(order, "draw_head", lambda *a, **k: calls.append("head"))
    monkeypatch.setattr(order, "draw_arm", lambda pen, cam, rg, side: calls.append("arm"))
    monkeypatch.setattr(sets_mod, "draw_desk_top", lambda pen, cam: calls.append("desk_top"))
    fs = state_at(scene, BANK, 0.0)
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    draw_frame(cairo.Context(surf), scene, BANK, fs, 0.0, width, height, boil=0)
    return calls


def test_desk_top_draws_over_seated_legs_and_torso_but_under_head_and_arms(monkeypatch):
    scene = _office_scene("tim", "tim", "desk_seat", "sit_typing", "focused")
    calls = _draw_calls(scene, monkeypatch)

    leg_torso_idx = [i for i, c in enumerate(calls) if c in ("leg", "torso")]
    head_arm_idx = [i for i, c in enumerate(calls) if c in ("head", "arm")]
    desk_idx = calls.index("desk_top")
    assert leg_torso_idx and head_arm_idx
    assert max(leg_torso_idx) < desk_idx < min(head_arm_idx)


# ---- (c) per-shot layer:low override: place: {who: {..., layer: low}} pushes the whole
# character (legs/torso AND head/arms) into the "low" run, so it draws entirely before the
# set's mid layer instead of straddling it. Scene 001 uses this for the lioness in the
# doorway. src/toon/render.py:85-89 ----


def test_layer_low_override_moves_the_whole_character_behind_the_desk(monkeypatch):
    low_scene = _office_scene("lioness", "lioness", "doorway_out", "stand_point", "angry", layer="low")
    split_scene = _office_scene("lioness", "lioness", "doorway_out", "stand_point", "angry")  # default "split"

    low_calls = _draw_calls(low_scene, monkeypatch)
    split_calls = _draw_calls(split_scene, monkeypatch)

    assert low_calls.index("head") < low_calls.index("desk_top")      # layer: low -> in the "low" run
    assert split_calls.index("desk_top") < split_calls.index("head")  # default -> in the "high" run
