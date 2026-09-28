import copy

import pytest

from toon.bank import load_bank
from toon.scene import SceneError, load_scene, scene_warnings, sentence_starts

BANK = load_bank()
MINI = {
    "id": "t", "duration": 4.0, "cast": {"tim": "tim"},
    "shots": [{"at": 0.0, "set": "office", "camera": "front34_push",
               "place": {"tim": {"spot": "desk_seat", "pose": "sit_typing", "expr": "focused"}},
               "props": {"idea": {"kind": "idea_bulb", "on": "tim", "b": 1.0}},
               "beats": []}],
}


def mini(**beat):
    d = copy.deepcopy(MINI)
    if beat:
        d["shots"][0]["beats"].append(beat)
    return d


def test_minimal_scene_loads():
    s = load_scene(mini(**{"at": 1.0, "prop": "idea", "to": {"b": 0.3}, "over": 1.0}), BANK)
    assert s.shots[0].beats[0].verb == "prop"


def test_unknown_pose_names_the_path():
    d = mini()
    d["shots"][0]["place"]["tim"]["pose"] = "moonwalk"
    with pytest.raises(SceneError, match=r"shots\[0\]\.place\.tim\.pose: unknown pose 'moonwalk'"):
        load_scene(d, BANK)


def test_words_in_a_bubble_are_rejected():
    with pytest.raises(SceneError, match="not an icon — animation is wordless"):
        load_scene(mini(**{"at": 1.0, "show": {"bubble": ["Dishes. Now."], "from": "tim"}}), BANK)


def test_free_text_field_is_rejected():
    d = mini()
    d["shots"][0]["place"]["tim"]["text"] = "hi"
    with pytest.raises(SceneError, match="Extra inputs are not permitted"):
        load_scene(d, BANK)


def test_beat_outside_its_shot():
    with pytest.raises(SceneError, match="outside the shot"):
        load_scene(mini(**{"at": 9.0, "door": "open"}), BANK)


def test_shots_must_increase():
    d = mini()
    d["shots"].append(copy.deepcopy(d["shots"][0]))
    with pytest.raises(SceneError, match="increasing"):
        load_scene(d, BANK)


def test_a_beat_has_exactly_one_verb():
    with pytest.raises(SceneError, match="exactly one verb"):
        load_scene(mini(**{"at": 1.0, "door": "open", "move": "tim", "to": "doorway"}), BANK)


def test_pose_beat_cannot_switch_sit_and_stand():
    with pytest.raises(SceneError, match="hip"):
        load_scene(mini(**{"at": 1.0, "pose": "tim", "to": "stand_point"}), BANK)


def test_sentence_anchor_resolves_by_character_share():
    assert sentence_starts("One two. Three four five six.", 10.0) == [0.0, 10.0 * 8 / 28]
    s = load_scene(mini(**{"at": {"sentence": 2}, "door": "open"}), BANK,
                   narration="One two. Three four five six.", duration=10.0)
    assert abs(s.shots[0].beats[0].at - 80 / 28) < 1e-9


def test_sentence_anchor_needs_narration():
    with pytest.raises(SceneError, match="need the scene's narration"):
        load_scene(mini(**{"at": {"sentence": 1}, "door": "open"}), BANK)


def test_warns_when_a_beat_lands_after_the_narration():
    s = load_scene(mini(**{"at": 3.0, "door": "open"}), BANK)
    (w,) = scene_warnings(s, 2.0)
    assert "cut" in w


def test_hide_must_name_a_graphic_shown_earlier():
    with pytest.raises(SceneError, match="does not match a graphic shown earlier"):
        load_scene(mini(**{"at": 1.0, "hide": "Dishes. Now."}), BANK)
    d = mini(**{"at": 0.5, "show": {"bubble": ["dishes"], "from": "tim"}})
    d["shots"][0]["beats"].append({"at": 1.0, "hide": "bubble:tim"})
    assert load_scene(d, BANK).shots[0].beats[1].verb == "hide"


def test_verb_specific_fields_are_rejected_on_other_verbs():
    with pytest.raises(SceneError, match=r"expr: only valid with a pose beat"):
        load_scene(mini(**{"at": 1.0, "door": "open", "expr": "Dishes. Now."}), BANK)
    with pytest.raises(SceneError, match=r"out: only valid with a prop beat"):
        load_scene(mini(**{"at": 1.0, "door": "open", "out": True}), BANK)


def test_boil_override_defaults_to_none():
    assert load_scene(mini(), BANK).boil is None


def test_boil_override_accepts_a_known_mode():
    assert load_scene({**mini(), "boil": "still"}, BANK).boil == "still"


def test_boil_override_rejects_an_unknown_mode():
    with pytest.raises(SceneError, match="boil"):
        load_scene({**mini(), "boil": "wobbly"}, BANK)
