"""E11 S12-11 (Layer A) and P2-R1…R6: `toy3d.acting.resolve` folds the worked scene's beats over the
bank and reproduces the frozen snapshot's own animation on every frame (`snapshot_oracle`, a
verbatim transcription of its scene.js). Plus each accent type pinned to its snapshot formula and
the capabilities the worked scene doesn't exercise (flicker, blink, a closing door, hide, a camera
cut, `loop: false`, `face` on a figure, a glide)."""
import math
from pathlib import Path

import pytest

from . import snapshot_oracle as snap

REPO = Path(__file__).resolve().parents[3]
WORKED = REPO / "assets" / "toy3d" / "scenes" / "001-beat2-break-in.yaml"
DESIGN_VIEW = REPO / "tests" / "fixtures" / "toy3d" / "sheet" / "guo_design_view.yaml"
FRAMES = [i / 30 for i in range(240)]
TOL = 1e-9


@pytest.fixture(scope="module")
def bank():
    from toy3d.bank import load_bank

    return load_bank()


@pytest.fixture(scope="module")
def worked(bank):
    from toon.scene import load_scene, read_scene

    return load_scene(read_scene(str(WORKED)), bank.catalog)


@pytest.fixture(scope="module")
def specs(worked, bank):
    from toy3d.acting import resolve

    return {t: resolve(worked, bank, t) for t in FRAMES}


def _diff(got, want, path="", tol=TOL, out=None):
    """Every place `got` differs from `want` (numbers within `tol`); `want`'s keys only."""
    out = [] if out is None else out
    if isinstance(want, dict):
        if not isinstance(got, dict):
            out.append(f"{path}: {got!r} is not a mapping")
            return out
        for k, v in want.items():
            if k not in got:
                out.append(f"{path}.{k}: missing")
            else:
                _diff(got[k], v, f"{path}.{k}", tol, out)
    elif isinstance(want, (list, tuple)):
        if not isinstance(got, (list, tuple)) or len(got) != len(want):
            out.append(f"{path}: {got!r} != {want!r}")
        else:
            for i, (g, w) in enumerate(zip(got, want, strict=True)):
                _diff(g, w, f"{path}[{i}]", tol, out)
    elif isinstance(want, bool) or want is None or isinstance(want, str):
        if got != want:
            out.append(f"{path}: {got!r} != {want!r}")
    elif not isinstance(got, (int, float)) or isinstance(got, bool) or abs(got - want) > tol:
        out.append(f"{path}: {got!r} != {want!r}")
    return out


def _every_frame(specs, pick, want, tol=lambda t: TOL):
    bad = []
    for t in FRAMES:
        bad += [f"t={t:.4f} {d}" for d in _diff(pick(specs[t]), want(t), tol=tol(t))]
    assert not bad, f"{len(bad)} mismatches, first: " + "\n".join(bad[:12])


def test_tim_matches_the_snapshot_every_frame(specs):
    _every_frame(specs, lambda s: s["actors"]["tim"], snap.tim)
    assert set(specs[0.0]["actors"]["tim"]["joints"]) == set(snap.tim(0.0)["joints"])


def test_lioness_matches_the_snapshot_every_frame(specs):
    def want(t):
        w = snap.lion(t)
        return {"root": w["root"], "joints": w["joints"], "face": w["face"]}
    _every_frame(specs, lambda s: s["actors"]["lioness"], want)
    assert set(specs[0.0]["actors"]["lioness"]["joints"]) == set(snap.lion(0.0)["joints"])
    for t in FRAMES:                                         # the finger: on once the point is 5% in
        assert ("finger" in specs[t]["actors"]["lioness"]["flags"]) == snap.lion(t)["finger"], t


def test_guoguo_matches_the_snapshot_every_frame(specs):
    # The snapshot's anticipation squash is a Gaussian centred 0.06 s after the door, so it starts
    # rising before the door beat that carries it here: 9e-6 of body scale at t = 2.167, sub-pixel.
    def tol(t):
        return 1e-5 if t < snap.T["door"] else TOL
    _every_frame(specs, lambda s: s["actors"]["guoguo"], snap.guo, tol)


def test_door_and_dust_match_the_snapshot_every_frame(specs):
    def want(t):
        return snap.door(t) if t >= snap.T["door"] else {"angle": 0.0, "dust": None}
    _every_frame(specs, lambda s: s["door"], want)


def test_bulb_matches_the_snapshot_every_frame(specs):
    _every_frame(specs, lambda s: s["props"]["idea"], snap.bulb)


def test_bubble_matches_the_snapshot_every_frame(specs):
    def want(t):
        b = snap.bubble(t)
        return [] if b is None else [b]
    _every_frame(specs, lambda s: s["bubbles"], want)


def test_laptop_matches_the_snapshot_every_frame(specs):
    _every_frame(specs, lambda s: s["laptop"], snap.laptop)


def test_camera_matches_the_snapshot_every_frame(specs):
    _every_frame(specs, lambda s: s["camera"], lambda t: {**snap.cam(t), "up": [0, 1, 0]})


def test_the_spec_names_its_frame_and_set(specs):
    s = specs[FRAMES[97]]
    assert s["frame"] == 97 and s["set"] == "office" and s["t"] == FRAMES[97]


def test_design_view_matches_the_snapshot(bank):
    from toon.scene import load_scene, read_scene
    from toy3d.acting import resolve

    scene = load_scene(read_scene(str(DESIGN_VIEW)), bank.catalog)
    s = resolve(scene, bank, 0.714)
    bad = (_diff(s["actors"]["guoguo"], snap.guo(0.714, neutral=True))
           + _diff(s["camera"], {**snap.GUO_VIEW, "up": [0, 1, 0]})
           + _diff(s["actors"]["tim"], snap.tim(0.714))
           + _diff(s["actors"]["lioness"]["joints"], snap.lion(0.714)["joints"]))
    assert not bad, bad


# -- each accent type: the snapshot's own formula, at sample times --

def _acc(data):
    from pydantic import TypeAdapter

    from toy3d.bank import Accent

    return TypeAdapter(Accent).validate_python(data)


def test_half_sine_accent():
    from toy3d.acting import accent_values

    a = _acc({"type": "half_sine", "channel": "hips.py", "amp": 0.07, "span": [0.0, 0.28]})
    assert accent_values(a, 0.14, 5.0) == {"hips.py": pytest.approx(0.07)}
    assert accent_values(a, 0.07, 5.0)["hips.py"] == pytest.approx(0.07 * math.sin(math.pi * 0.25))
    assert accent_values(a, 0.4, 5.0)["hips.py"] == pytest.approx(0.0, abs=1e-15)
    assert accent_values(a, -0.1, 5.0)["hips.py"] == 0.0


def test_bump_accent_sums_its_gaussians_on_every_channel():
    from toy3d.acting import accent_values

    a = _acc({"type": "bump", "channels": {"arm_r.j1.rx": -0.16, "body.rx": 0.064}, "at": [0.42, 0.66],
              "width": 0.06})
    v = accent_values(a, 0.5, 3.5)
    g = math.exp(-((0.5 - 0.42) / 0.06) ** 2) + math.exp(-((0.5 - 0.66) / 0.06) ** 2)
    assert v == {"arm_r.j1.rx": pytest.approx(-0.16 * g), "body.rx": pytest.approx(0.064 * g)}


def test_decay_sine_accent_starts_at_its_start():
    from toy3d.acting import accent_values

    a = _acc({"type": "decay_sine", "channel": "wob", "amp": 1.0, "start": 0.53, "decay": 6.0, "freq": 30.0})
    assert accent_values(a, 0.53, 0)["wob"] == 0.0
    assert accent_values(a, 0.6, 0)["wob"] == pytest.approx(math.exp(-0.07 * 6) * math.sin(0.07 * 30))


def test_flap_accent_ramps_in_and_out():
    from toy3d.acting import accent_values

    a = _acc({"type": "flap", "channel": "flap", "amp": 0.7, "start": 0.02, "end": 0.45, "hz": 7.0})
    for since in (0.0, 0.05, 0.3, 0.4, 0.5):
        want = 0.7 * math.sin((since - 0.02) * math.pi * 2 * 7) * snap.seg(since, 0.02, 0.08) * (
            1 - snap.seg(since, 0.2, 0.45))
        assert accent_values(a, since, 0)["flap"] == pytest.approx(want, abs=1e-15), since


def test_hold_accent_is_on_after_its_after_and_fades():
    from toy3d.acting import accent_values

    a = _acc({"type": "hold", "channel": "raise", "amp": 1.0, "after": 0.03, "fade": [1.23, 1.83]})
    assert accent_values(a, 0.03, 0)["raise"] == 0.0                     # strictly after
    assert accent_values(a, 0.04, 0)["raise"] == 1.0
    assert accent_values(a, 1.53, 0)["raise"] == pytest.approx(0.5)
    assert accent_values(a, 2.0, 0)["raise"] == 0.0


def test_osc_accent_runs_on_scene_time_with_its_envelope():
    from toy3d.acting import accent_values

    a = _acc({"type": "osc", "channel": "hips.px", "wave": "sin", "amp": 0.006, "rate": 61.0, "after": 0.15,
              "fade": [1.5, 2.3]})
    assert accent_values(a, 0.15, 4.05)["hips.px"] == 0.0
    assert accent_values(a, 0.2, 4.1)["hips.px"] == pytest.approx(0.006 * math.sin(4.1 * 61))
    assert accent_values(a, 1.9, 5.8)["hips.px"] == pytest.approx(0.5 * 0.006 * math.sin(5.8 * 61))
    b = _acc({"type": "osc", "channel": "bob", "wave": "abs_sin", "amp": 0.006, "rate": 3.2})
    assert accent_values(b, 1.0, 1.0)["bob"] == pytest.approx(0.006 * abs(math.sin(3.2)))


# -- the capabilities the worked scene doesn't exercise --

def _scene(bank, beats=(), place=None, props=None, camera="beat2"):
    from toon.scene import load_scene

    shot = {"at": 0.0, "set": "office", "camera": camera,
            "place": place or {"tim": {"spot": "desk_seat", "pose": "typing", "expr": "neutral"},
                               "lioness": {"spot": "doorway_in", "pose": "stand", "expr": "stern"},
                               "guoguo": {"spot": "shelf_top", "pose": "seated", "expr": "neutral"}},
            "props": {"idea": {"kind": "idea_bulb", "on": "tim", "b": 1.0}} if props is None else props,
            "beats": list(beats)}
    return load_scene({"id": "probe", "engine": "toy3d", "duration": 4.0,
                       "cast": {"tim": "tim", "lioness": "lioness", "guoguo": "guoguo"}, "shots": [shot]},
                      bank.catalog)


def test_flicker_alternates_low_and_high_by_frame(bank):
    from toy3d.acting import resolve

    sc = _scene(bank, [{"at": 1.0, "prop": "idea", "flicker": {"every": 3, "low": 0.2, "high": 0.9}}])
    assert resolve(sc, bank, 0.9)["props"]["idea"]["level"] == 1.0
    levels = [resolve(sc, bank, i / 30)["props"]["idea"]["level"] for i in range(30, 36)]
    assert levels == [0.2, 0.9, 0.9, 0.2, 0.9, 0.9]


def test_blink_holds_its_level_while_it_lasts(bank):
    from toy3d.acting import resolve

    sc = _scene(bank, [{"at": 1.0, "prop": "idea", "blink": {"b": 0.1, "over": 0.2}}])
    assert [resolve(sc, bank, t)["props"]["idea"]["level"] for t in (0.9, 1.1, 1.3)] == [1.0, 0.1, 1.0]


def test_a_closing_door_swings_shut_from_its_rest(bank):
    from toy3d.acting import resolve

    sc = _scene(bank, [{"at": 0.5, "door": "open", "over": 0.14, "ease": "out"},
                       {"at": 2.0, "door": "close", "over": 0.5, "ease": "linear"}])
    door = bank.sets["office"].door
    assert resolve(sc, bank, 2.25)["door"]["angle"] == pytest.approx(door.rest * 0.5)
    assert resolve(sc, bank, 2.6)["door"]["angle"] == 0.0
    assert resolve(sc, bank, 2.6)["door"]["dust"]["k"] == 1.0          # the dust is the open's


def test_hide_takes_the_bubble_down(bank):
    from toy3d.acting import resolve

    sc = _scene(bank, [{"at": 0.5, "show": {"bubble": ["dishes"], "from": "lioness"}, "over": 0.2},
                       {"at": 1.0, "hide": "bubble:lioness"}])
    assert [b["icons"] for b in resolve(sc, bank, 0.9)["bubbles"]] == [["dishes"]]
    assert resolve(sc, bank, 1.0)["bubbles"] == []


def test_a_camera_beat_cuts_and_restarts_the_preset(bank):
    from toy3d.acting import resolve

    sc = _scene(bank, [{"at": 1.0, "camera": "closeup"}, {"at": 2.0, "camera": "beat2"}])
    assert resolve(sc, bank, 1.5)["camera"]["pos"] == list(bank.cameras["closeup"].pos)
    assert resolve(sc, bank, 2.0)["camera"]["pos"] == pytest.approx(snap.cam(0.0)["pos"])
    assert resolve(sc, bank, 2.5)["camera"]["pos"] == pytest.approx(snap.cam(0.5)["pos"])


def test_loop_false_stops_the_pose_loops(bank):
    from toy3d.acting import resolve

    place = {"tim": {"spot": "desk_seat", "pose": "typing", "expr": "neutral", "loop": False}}
    joints = resolve(_scene(bank, place=place, props={}), bank, 1.0)["actors"]["tim"]["joints"]
    assert joints["torso.rx"] == 0.13 and joints["arm_l.j1.rx"] == -1.25 and joints["neck.ry"] == 0.0


def test_face_turns_a_figure_toward_its_target(bank):
    from toy3d.acting import resolve

    sc = _scene(bank, [{"at": 1.0, "face": "lioness", "to": "tim", "over": 0.5, "ease": "linear"}])
    me, tim = bank.sets["office"].spots["doorway_in"].pos, bank.sets["office"].spots["desk_seat"].pos
    aim = math.atan2(tim[0] - me[0], tim[2] - me[2])
    assert resolve(sc, bank, 1.25)["actors"]["lioness"]["root"]["yaw"] == pytest.approx(
        math.radians(90) + 0.5 * (aim - math.radians(90)))


def test_a_move_without_a_walk_glides(bank):
    from toy3d.acting import resolve

    sc = _scene(bank, [{"at": 1.0, "move": "guoguo", "to": "turntable", "over": 1.0, "ease": "linear"}])
    a, b = bank.sets["office"].spots["shelf_top"].pos, bank.sets["office"].spots["turntable"].pos
    assert resolve(sc, bank, 1.5)["actors"]["guoguo"]["root"]["pos"] == pytest.approx(
        [(a[i] + b[i]) / 2 for i in range(3)])


def test_standing_guoguo_turns_his_whole_body(bank):
    from toy3d.acting import resolve

    place = {"guoguo": {"spot": "turntable", "pose": "standing", "expr": "neutral"},
             "tim": {"spot": "desk_seat", "pose": "typing", "expr": "neutral"}}
    s = resolve(_scene(bank, [{"at": 0.0, "face": "guoguo", "to": "tim"}], place=place, props={}), bank, 1.0)
    me, tim = bank.sets["office"].spots["turntable"].pos, bank.sets["office"].spots["desk_seat"].pos
    g = s["actors"]["guoguo"]
    assert g["build"] == "guoguo_standing"
    assert g["root"]["yaw"] == pytest.approx(math.atan2(tim[0] - me[0], tim[2] - me[2]))
    assert g["guo"]["head_yaw"] == 0.0


def test_unplaced_cast_is_not_in_the_frame(bank):
    from toy3d.acting import resolve

    place = {"tim": {"spot": "desk_seat", "pose": "typing", "expr": "neutral"}}
    assert set(resolve(_scene(bank, place=place, props={}), bank, 0.5)["actors"]) == {"tim"}


def test_a_flag_turns_on_once_its_pose_is_five_percent_in(bank):
    from toy3d.acting import resolve

    sc = _scene(bank, [{"at": 1.0, "pose": "lioness", "to": "point", "over": 1.0, "ease": "linear"}])
    assert "finger" not in resolve(sc, bank, 1.04)["actors"]["lioness"]["flags"]
    assert "finger" in resolve(sc, bank, 1.1)["actors"]["lioness"]["flags"]
    assert "finger" in resolve(sc, bank, 3.5)["actors"]["lioness"]["flags"]          # and stays on


def test_the_laptop_stops_filling_when_the_typist_stops(bank):
    from toy3d.acting import resolve

    sc = _scene(bank, [{"at": 1.0, "pose": "tim", "to": "shock"}])
    laptop = bank.sets["office"].laptop
    assert resolve(sc, bank, 0.5)["laptop"]["lines"] == laptop.lines + math.floor(0.5 * laptop.rate)
    assert resolve(sc, bank, 3.0)["laptop"]["lines"] == laptop.lines + math.floor(1.0 * laptop.rate)
