"""Cue planning: effective moods + scenes.json spans -> contiguous cues."""
from pipeline.composer.music import plan_cues
from pipeline.storyboard import Scene, Storyboard, Theme


def _sb(*ids_sections_moods):
    return Storyboard(
        theme=Theme(music_default_mood="none"),
        scenes=[
            Scene(id=i, section=s, narration="x", narration_est_sec=1.0, music_mood=m)
            for i, s, m in ids_sections_moods
        ],
    )


def test_plan_cues_two_contiguous_cues_with_boundary():
    # baby-walker arc: tense s19-s20 -> hopeful s22-s23 -> none s24
    sb = _sb(
        ("s19", "rising", "tense"), ("s20", "rising", ""),
        ("s22", "climax", "hopeful"), ("s23", "climax", ""), ("s24", "climax", "none"),
    )
    scenes = [
        {"id": "s19", "start_sec": 211.5, "duration_sec": 11.6},
        {"id": "s20", "start_sec": 223.1, "duration_sec": 11.4},
        {"id": "s22", "start_sec": 234.5, "duration_sec": 15.6},
        {"id": "s23", "start_sec": 250.1, "duration_sec": 11.8},
        {"id": "s24", "start_sec": 261.9, "duration_sec": 16.0},
    ]
    cues = plan_cues(sb, scenes)
    assert [(c.mood, round(c.start_sec, 1), round(c.end_sec, 1)) for c in cues] == [
        ("tense", 211.5, 234.5),   # s19+s20 merged
        ("hopeful", 234.5, 261.9),  # s22+s23 merged; boundary at 234.5
    ]


def test_plan_cues_empty_when_all_none():
    sb = _sb(("s1", "hook", ""))
    assert plan_cues(sb, [{"id": "s1", "start_sec": 0.0, "duration_sec": 5.0}]) == []


def test_plan_cues_separate_when_gap_between_same_mood():
    # same mood either side of a none scene -> two cues (not merged across the gap)
    sb = _sb(("s1", "rising", "tense"), ("s2", "rising", "none"), ("s3", "rising", "tense"))
    scenes = [
        {"id": "s1", "start_sec": 0.0, "duration_sec": 5.0},
        {"id": "s2", "start_sec": 5.0, "duration_sec": 5.0},
        {"id": "s3", "start_sec": 10.0, "duration_sec": 5.0},
    ]
    cues = plan_cues(sb, scenes)
    assert [(c.mood, c.start_sec, c.end_sec) for c in cues] == [
        ("tense", 0.0, 5.0), ("tense", 10.0, 15.0)
    ]
