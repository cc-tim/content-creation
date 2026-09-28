import copy

import pytest

from toon.bank import load_bank
from toon.scene import load_scene, read_scene
from toon.timeline import state_at

BANK = load_bank()
BASE = {
    "id": "t", "duration": 8.0, "cast": {"tim": "tim", "lioness": "lioness"},
    "shots": [
        {"at": 0.0, "set": "office", "camera": "two_shot",
         "place": {"tim": {"spot": "desk_seat", "pose": "sit_typing", "expr": "focused"},
                   "lioness": {"spot": "doorway_out", "pose": "stand_point", "expr": "angry", "layer": "low"}},
         "props": {"idea": {"kind": "idea_bulb", "on": "tim", "b": 1.0}},
         "beats": [
             {"at": 1.0, "door": "open", "over": 1.0, "ease": "linear"},
             {"at": 1.0, "move": "lioness", "to": "doorway", "over": 1.0, "ease": "linear"},
             {"at": 1.0, "pose": "tim", "to": "sit_shock", "expr": "shocked", "over": 1.0, "ease": "linear"},
             {"at": 2.0, "prop": "idea", "flicker": {"every": 4, "low": 0.35, "high": 0.85}},
             {"at": 1.0, "show": {"bubble": ["dishes", "bang"], "from": "lioness"}},
         ]},
        {"at": 4.0, "set": "kitchen", "camera": "close_push",
         "place": {"tim": {"spot": "sink", "pose": "stand_wash", "expr": "glum", "loop": False}},
         "props": {"idea": {"kind": "idea_bulb", "on": "tim", "b": 0.3},
                   "stack": {"kind": "plate_stack", "count": 6}},
         "beats": [
             {"at": 0.0, "prop": "stack", "to": {"count": 3}, "over": 2.0, "ease": "linear"},
             {"at": 0.0, "prop": "idea", "to": {"b": 0.05}, "over": 1.0, "ease": "linear"},
             {"at": 0.5, "prop": "idea", "blink": {"b": 0.35, "over": 0.2}},
             {"at": 1.0, "prop": "idea", "out": True},
         ]},
    ],
}
SCENE = load_scene(copy.deepcopy(BASE), BANK)


def test_pose_blends_and_expression_switches_after_half():
    tim = state_at(SCENE, BANK, 1.5).chars["tim"]
    assert tim.pose.lean == pytest.approx((15 + -10) / 2)
    assert tim.pose.eyes == "dot"                   # discrete fields switch only once k > 0.5
    assert state_at(SCENE, BANK, 1.75).chars["tim"].pose.eyes == "wide"


def test_door_and_move_progress():
    fs = state_at(SCENE, BANK, 1.5)
    assert fs.door == pytest.approx(0.5)
    assert fs.chars["lioness"].root[0] == pytest.approx((-3.25 + -2.4) / 2, abs=1e-9)


def test_flicker_dims_every_fourth_drawing():
    lows = [state_at(SCENE, BANK, i / 12).props["idea"].b for i in range(24, 36)]
    assert lows.count(0.35) == 3 and set(lows) == {0.35, 0.85}


def test_counts_step_toward_zero_and_blink_then_out():
    fs = state_at(SCENE, BANK, 5.0)                 # rel 1.0 in shot 2: stack k=0.5 → 6 - 1 = 5
    assert fs.props["stack"].count == 5
    assert state_at(SCENE, BANK, 4.6).props["idea"].b == 0.35   # inside the blink
    out = state_at(SCENE, BANK, 5.5).props["idea"]
    assert out.mode == "out" and out.smoke == pytest.approx(0.5)


def test_bubble_pops_in():
    assert state_at(SCENE, BANK, 0.9).graphics == []
    (g,) = state_at(SCENE, BANK, 1.125).graphics
    assert g.key == "bubble:lioness" and g.k == pytest.approx(0.5)


def test_camera_punch_and_push():
    assert state_at(SCENE, BANK, 0.0).cam.focal == pytest.approx(3050)
    assert state_at(SCENE, BANK, 0.25, 0.25).cam.focal == pytest.approx(3200)
    assert state_at(SCENE, BANK, 4.0).cam.focal == pytest.approx(5000)
    assert state_at(SCENE, BANK, 7.99, 7.99).cam.focal == pytest.approx(5500, abs=1)


def test_the_cut_follows_camera_time_and_clamps_drawing_time():
    fs = state_at(SCENE, BANK, 3.95, 4.0)
    assert fs.shot == 1 and fs.set_id == "kitchen"


def test_a_cut_duration_never_reaches_a_shot_that_starts_after_it():
    # R15: 001-lioness-dishes's last shot (index 3, "kitchen") starts at 9.7s. Cut to 8.0s of
    # narration, render_clip only ever asks state_at() for t in [0, 8.0) — it must resolve to
    # the last shot that actually starts in range (index 2, also "kitchen"), never shot 3.
    scene = load_scene(read_scene("001-lioness-dishes"), BANK, duration=8.0)
    fs = state_at(scene, BANK, 7.99)
    assert fs.shot == 2 and fs.set_id == "kitchen"


# A camera beat is a cut to another preset (spec §5): front34_push (3300→3700 over the shot),
# cut at 4.0s of an 8s shot to close_push (5000→5500), whose push runs over the 4s left.
CUT = {"id": "cut", "duration": 8.0, "cast": {"tim": "tim"},
       "shots": [{"at": 0.0, "set": "office", "camera": "front34_push",
                  "place": {"tim": {"spot": "desk_seat", "pose": "sit_typing"}},
                  "beats": [{"at": 4.0, "camera": "close_push"}]}]}


def test_camera_beat_cuts_and_the_new_push_starts_at_the_beat():
    s = load_scene(copy.deepcopy(CUT), BANK)
    assert state_at(s, BANK, 2.0, 2.0).cam.focal == pytest.approx(3300 + 400 * 0.15625)  # smooth(.25)
    assert state_at(s, BANK, 4.0, 4.0).cam.focal == pytest.approx(5000)  # not mid-push
    assert state_at(s, BANK, 6.0, 6.0).cam.focal == pytest.approx(5250)
    assert state_at(s, BANK, 8.0, 8.0).cam.focal == pytest.approx(5500)


def test_camera_beat_restarts_the_new_presets_punch():
    d = copy.deepcopy(CUT)
    d["shots"][0]["beats"][0]["camera"] = "two_shot"  # 3050, punch → 3200 at 0.1 over 0.15
    s = load_scene(d, BANK)
    assert state_at(s, BANK, 4.0, 4.0).cam.focal == pytest.approx(3050)
    assert state_at(s, BANK, 4.25, 4.25).cam.focal == pytest.approx(3200)


def test_camera_beat_cuts_on_camera_time_not_drawing_time():
    s = load_scene(copy.deepcopy(CUT), BANK)
    assert state_at(s, BANK, 3.95, 4.0).cam.focal == pytest.approx(5000)  # camera on ones


def test_gesture_loop_rides_on_the_pose():
    d = copy.deepcopy(BASE)
    d["shots"][1]["place"]["tim"]["loop"] = True
    s = load_scene(d, BANK)
    base = BANK.poses["stand_wash"].hand_r              # (-0.24, 1.82, 1.0), loop r: radius (0.07, 0.04) @ 2.5 Hz
    a = state_at(s, BANK, 4.0).chars["tim"].pose.hand_r  # phase 4.0*2π*2.5 = 20π → cos 1, sin 0
    assert a[0] == pytest.approx(base[0] + 0.07)
    assert a[1] == pytest.approx(base[1])
    b = state_at(s, BANK, 4.1).chars["tim"].pose.hand_r  # phase 20.5π → cos 0, sin 1
    assert b[0] == pytest.approx(base[0]) and b[1] == pytest.approx(base[1] + 0.04)
    assert tuple(state_at(SCENE, BANK, 4.0).chars["tim"].pose.hand_r) == tuple(base)  # loop off: exact pose
