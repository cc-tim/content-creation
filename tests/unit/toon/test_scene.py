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


@pytest.mark.parametrize("narration, sentences", [
    ("我……不知道。好。", ["我……不知道。", "好。"]),        # zh-TW ellipsis is a pause, not a break
    ("Wait... what?", ["Wait...", "what?"]),               # a run of terminators is one break
    ("3.5 hours.", ["3.5 hours."]),                        # a decimal point is not a break
    ("One two. Three four five six.", ["One two.", "Three four five six."]),
    ("他走了。……好。", ["他走了。……", "好。"]),              # a run holding 。 still breaks
    ("What?! No.", ["What?!", "No."]),
])
def test_sentences_count_real_breaks_only(narration, sentences):
    from toon.scene import split_sentences

    assert split_sentences(narration) == sentences
    assert len(sentence_starts(narration, 10.0)) == len(sentences)


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


def with_props(**props):
    d = mini()
    d["shots"][0]["props"] = props
    return d


# -- props: per-kind requirements (a prop the renderer can't draw must fail at load) --

def test_idea_bulb_needs_on():
    with pytest.raises(SceneError, match=r"shots\[0\]\.props\.idea\.on: an idea_bulb prop needs on:"):
        load_scene(with_props(idea={"kind": "idea_bulb", "b": 1.0}), BANK)


def test_idea_bulb_rejects_held_by():
    with pytest.raises(SceneError, match=r"shots\[0\]\.props\.idea\.held_by: not valid on an idea_bulb prop"):
        load_scene(with_props(idea={"kind": "idea_bulb", "on": "tim", "held_by": "tim"}), BANK)


def test_plate_needs_held_by():
    with pytest.raises(SceneError, match=r"shots\[0\]\.props\.p\.held_by: a plate prop needs held_by:"):
        load_scene(with_props(p={"kind": "plate"}), BANK)


def test_plate_rejects_fields_it_cannot_draw():
    with pytest.raises(SceneError, match=r"shots\[0\]\.props\.p\.on: not valid on a plate prop"):
        load_scene(with_props(p={"kind": "plate", "held_by": "tim", "on": "tim"}), BANK)
    with pytest.raises(SceneError, match=r"shots\[0\]\.props\.p\.b: not valid on a plate prop"):
        load_scene(with_props(p={"kind": "plate", "held_by": "tim", "b": 0.5}), BANK)


def test_plate_stack_needs_count():
    with pytest.raises(SceneError, match=r"shots\[0\]\.props\.s\.count: a plate_stack prop needs count:"):
        load_scene(with_props(s={"kind": "plate_stack"}), BANK)


def test_plate_stack_rejects_on():
    with pytest.raises(SceneError, match=r"shots\[0\]\.props\.s\.on: not valid on a plate_stack prop"):
        load_scene(with_props(s={"kind": "plate_stack", "count": 3, "on": "tim"}), BANK)


def test_prop_reference_to_an_unplaced_character_names_the_field():
    with pytest.raises(SceneError, match=r"shots\[0\]\.props\.idea\.on: 'lioness' is not placed"):
        load_scene(with_props(idea={"kind": "idea_bulb", "on": "lioness"}), BANK)


# -- prop beats: `to:` keys must be a state that prop kind animates --

def test_prop_beat_to_key_unknown_for_the_kind_is_rejected():
    with pytest.raises(SceneError, match=r"shots\[0\]\.beats\[0\]\.to\.bb: an idea_bulb prop has no 'bb' state"):
        load_scene(mini(**{"at": 1.0, "prop": "idea", "to": {"bb": 0.3}}), BANK)
    d = with_props(idea={"kind": "idea_bulb", "on": "tim"}, s={"kind": "plate_stack", "count": 6})
    d["shots"][0]["beats"].append({"at": 1.0, "prop": "s", "to": {"b": 0.3}})
    with pytest.raises(SceneError, match=r"shots\[0\]\.beats\[0\]\.to\.b: a plate_stack prop has no 'b' state"):
        load_scene(d, BANK)


def test_a_plate_has_no_animatable_state():
    d = with_props(p={"kind": "plate", "held_by": "tim"})
    d["shots"][0]["beats"].append({"at": 1.0, "prop": "p", "to": {"count": 2}})
    with pytest.raises(SceneError, match=r"shots\[0\]\.beats\[0\]\.to\.count: a plate prop has no 'count' state"):
        load_scene(d, BANK)


def test_prop_beat_known_to_keys_load():
    d = with_props(idea={"kind": "idea_bulb", "on": "tim"}, s={"kind": "plate_stack", "count": 6})
    d["shots"][0]["beats"] += [{"at": 1.0, "prop": "idea", "to": {"b": 0.3}},
                               {"at": 1.0, "prop": "s", "to": {"count": 3}}]
    assert len(load_scene(d, BANK).shots[0].beats) == 2


# -- R6 completion: every remaining ignored field is rejected, naming the path --

@pytest.mark.parametrize("beat, path", [
    ({"at": 1.0, "door": "open", "to": "doorway"}, r"beats\[0\]\.to: not valid with a door beat"),
    ({"at": 1.0, "show": {"anger": "tim"}, "to": "tim"}, r"beats\[0\]\.to: not valid with a show beat"),
    ({"at": 1.0, "camera": "two_shot", "to": "front34_push"}, r"beats\[0\]\.to: not valid with a camera beat"),
])
def test_to_is_rejected_on_verbs_that_ignore_it(beat, path):
    with pytest.raises(SceneError, match=path):
        load_scene(mini(**beat), BANK)


def test_to_is_rejected_on_a_hide_beat():
    d = mini(**{"at": 0.5, "show": {"anger": "tim"}})
    d["shots"][0]["beats"].append({"at": 1.0, "hide": "anger:tim", "to": "x"})
    with pytest.raises(SceneError, match=r"beats\[1\]\.to: not valid with a hide beat"):
        load_scene(d, BANK)


@pytest.mark.parametrize("field, value", [("over", 0.5), ("ease", "linear")])
def test_a_camera_beat_is_a_cut_so_over_and_ease_are_rejected(field, value):
    with pytest.raises(SceneError, match=rf"beats\[0\]\.{field}: a camera beat is a cut"):
        load_scene(mini(**{"at": 1.0, "camera": "two_shot", field: value}), BANK)


def test_a_bare_camera_beat_loads():
    assert load_scene(mini(**{"at": 1.0, "camera": "two_shot"}), BANK).shots[0].beats[0].verb == "camera"


def test_from_is_only_for_bubbles():
    with pytest.raises(SceneError, match=r"beats\[0\]\.show\.from: only valid with a bubble show"):
        load_scene(mini(**{"at": 1.0, "show": {"anger": "tim", "from": "tim"}}), BANK)


def test_at_is_only_for_cards():
    with pytest.raises(SceneError, match=r"beats\[0\]\.show\.at: only valid with an x_card or check_pill"):
        load_scene(mini(**{"at": 1.0, "show": {"speed_lines": "tim", "at": [0.5, 0.5]}}), BANK)


def test_graphic_key_is_per_kind():
    from toon.scene import Show, graphic_key

    assert graphic_key(Show(anger="lioness")) == "anger:lioness"
    assert graphic_key(Show(bubble=["dishes"], **{"from": "tim"})) == "bubble:tim"
    assert graphic_key(Show(x_card="bulb", at=(0.5, 0.5))) == "x_card:bulb"


def test_an_empty_bubble_is_rejected():
    with pytest.raises(SceneError, match=r"show\.bubble"):
        load_scene(mini(**{"at": 1.0, "show": {"bubble": [], "from": "tim"}}), BANK)


# -- storyboard visuals: inline scenes pass every scene key through; references take boil only --

def inline_visual(**extra):
    return {"type": "toon", "cast": {"tim": "tim"}, "shots": copy.deepcopy(MINI["shots"]), **extra}


def test_inline_visual_boil_is_honoured():
    from toon.scene import scene_data_from_visual

    assert load_scene(scene_data_from_visual(inline_visual(boil="full")), BANK).boil == "full"


def test_inline_visual_typo_is_rejected():
    from toon.scene import scene_data_from_visual

    with pytest.raises(SceneError, match=r"cats: Extra inputs are not permitted"):
        load_scene(scene_data_from_visual(inline_visual(cats={"tim": "tim"})), BANK)


def test_inline_visual_ignores_pipeline_owned_keys():
    from toon.scene import scene_data_from_visual

    v = inline_visual(confidence="high", rationale="the lioness bursts in", edit_mode=False)
    assert load_scene(scene_data_from_visual(v), BANK).id == "inline"


def test_scene_reference_takes_a_boil_override():
    from toon.scene import scene_data_from_visual

    v = {"type": "toon", "scene": "001-lioness-dishes", "boil": "still", "confidence": "high"}
    assert load_scene(scene_data_from_visual(v), BANK).boil == "still"


def test_scene_reference_rejects_any_other_key():
    from toon.scene import scene_data_from_visual

    with pytest.raises(SceneError, match=r"visual\.bogus: a scene reference takes only"):
        scene_data_from_visual({"type": "toon", "scene": "001-lioness-dishes", "bogus": 1})


def test_boil_override_defaults_to_none():
    assert load_scene(mini(), BANK).boil is None


def test_boil_override_accepts_a_known_mode():
    assert load_scene({**mini(), "boil": "still"}, BANK).boil == "still"


def test_boil_override_rejects_an_unknown_mode():
    with pytest.raises(SceneError, match="boil"):
        load_scene({**mini(), "boil": "wobbly"}, BANK)
