import copy

import pytest

from toon.bank import load_bank
from toon.scene import SceneError, load_scene, read_scene, scene_warnings, sentence_starts

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


def test_beat_outside_the_max_of_authored_and_override_still_raises():
    # R15b superseded R15's stricter claim ("always check the authored duration, ignoring the
    # override") — a longer override now legitimately stretches the last shot's window (the
    # last shot "holds"), so a beat within the override but past authored no longer raises
    # (see test_a_longer_narration_lets_a_sentence_anchor_land_past_the_authored_end). An
    # override must still not mask a beat that's genuinely out of range of BOTH: _check()
    # validates against max(authored, override) = max(4.0, 20.0) = 20.0 here, and a beat past
    # that (25.0) is still a real structural error.
    with pytest.raises(SceneError, match="outside the shot"):
        load_scene(mini(**{"at": 25.0, "door": "open"}), BANK, duration=20.0)


def test_a_shorter_narration_cuts_the_scene_instead_of_failing_to_load():
    # R15 / design spec §5 ("Duration"): a narration shorter than a scene's last shot start
    # (001-lioness-dishes's last shot starts at 9.7s) must load successfully — shot windows
    # are checked against the scene's AUTHORED duration, not the override — and the mismatch
    # surfaces only as a scene_warnings() "cut" warning, computed against the override.
    s = load_scene(read_scene("001-lioness-dishes"), BANK, duration=8.0)
    (w,) = scene_warnings(s, 8.0)
    assert "cut" in w


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


def test_a_longer_narration_lets_a_sentence_anchor_land_past_the_authored_end():
    # R15b: MINI's authored duration is 4.0s. A much longer narration + override (20.0s)
    # resolves the second-sentence anchor at 20.0 * 8/28 ~= 5.71s — past the authored end.
    # _check() must validate against max(authored, override) = 20.0, not 4.0 alone, so the
    # last (only) shot's window stretches to cover it: "if the narration is longer, the last
    # shot holds, still boiling" (design spec §5). This must load without error.
    assert MINI["duration"] == 4.0
    s = load_scene(mini(**{"at": {"sentence": 2}, "door": "open"}), BANK,
                   narration="One two. Three four five six.", duration=20.0)
    resolved_at = s.shots[0].beats[0].at
    assert resolved_at == pytest.approx(20.0 * 8 / 28)
    assert resolved_at > MINI["duration"]


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
