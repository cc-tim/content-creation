"""Phase 2 review I2 and M6: toy3d refuses, at load (so `pipeline validate` and the CLI do too), what
it would draw wrong: a seated character moved out of (or into) a seat, a seat taken by someone with
no seat_height, sitting where there's no seat, and a partial pose as a placement."""
import copy

import pytest

from toon.scene import SceneError, load_scene

PLACE = {"tim": {"spot": "desk_seat", "pose": "typing", "expr": "neutral"},
         "lioness": {"spot": "doorway_in", "pose": "stand", "expr": "stern"}}


@pytest.fixture(scope="module")
def bank():
    from toy3d.bank import load_bank

    return load_bank()


def _load(bank, place=None, beats=()):
    shot = {"at": 0.0, "set": "office", "camera": "beat2", "place": copy.deepcopy(place or PLACE), "beats": list(beats)}
    return load_scene({"id": "seat", "engine": "toy3d", "duration": 4.0, "cast": {"tim": "tim", "lioness": "lioness"},
                       "shots": [shot]}, bank)


def _problems(bank, **kw):
    with pytest.raises(SceneError) as e:
        _load(bank, **kw)
    return e.value.problems


def test_the_worked_placements_load(bank):
    _load(bank)


def test_a_seated_character_does_not_move(bank):
    (p,) = _problems(bank, beats=[{"at": 1.0, "move": "tim", "to": "turntable", "over": 1.0}])
    assert p == ("shots[0].beats[0].move: tim sits at 'desk_seat'; a move would leave them sitting on air "
                 "(cut to a new shot to change where they are)")


def test_nobody_moves_into_a_seat(bank):
    (p,) = _problems(bank, beats=[{"at": 1.0, "move": "lioness", "to": "desk_seat", "over": 1.0}])
    assert p == "shots[0].beats[0].to: 'desk_seat' is a seat; place a character in it instead of moving there"


def test_a_seat_needs_a_seat_height(bank):
    place = {**PLACE, "lioness": {"spot": "desk_seat", "pose": "stand", "expr": "stern"},
             "tim": {"spot": "turntable", "pose": "typing", "expr": "neutral"}}
    problems = _problems(bank, place=place)
    assert "shots[0].place.lioness.spot: 'desk_seat' is a seat, and lioness has no seat_height" in problems


def test_sitting_needs_a_seat(bank):
    place = {**PLACE, "tim": {"spot": "turntable", "pose": "typing", "expr": "neutral"}}
    (p,) = _problems(bank, place=place)
    assert p == "shots[0].place.tim.pose: 'typing' sits, and 'turntable' has no seat"


def test_a_placement_is_a_full_pose(bank):
    place = {**PLACE, "tim": {"spot": "desk_seat", "pose": "turned", "expr": "neutral"}}
    (p,) = _problems(bank, place=place)
    assert p == ("shots[0].place.tim.pose: 'turned' is a partial pose (it sets only ['seat.ry']); "
                 "place tim in a full pose")


def test_the_validator_refuses_a_seat_mismatch(tmp_path):
    from pipeline.director.storyboard_validator import validate_storyboard
    from pipeline.storyboard import Scene, Storyboard

    visual = {"type": "toon", "engine": "toy3d", "id": "inline", "cast": {"tim": "tim"},
              "shots": [{"at": 0.0, "set": "office", "camera": "beat2",
                         "place": {"tim": {"spot": "turntable", "pose": "typing"}}}]}
    sb = Storyboard(scenes=[Scene(id="s1", section="hook", narration="One.", narration_est_sec=4, visual=visual)])
    (issue,) = [i for i in validate_storyboard(sb, tmp_path) if i.severity == "error"]
    assert "'typing' sits, and 'turntable' has no seat" in issue.issue
