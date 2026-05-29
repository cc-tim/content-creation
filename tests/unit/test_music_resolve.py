"""Mood resolution: inherit-on-blank, none-propagation, theme-default head."""
import pytest

from pipeline.composer.music import resolve_effective_moods
from pipeline.storyboard import Scene, Storyboard, Theme


def _sb(theme_default, *mood_by_id):
    scenes = [
        Scene(id=i, section="rising", narration="x", narration_est_sec=1.0, music_mood=m)
        for i, m in mood_by_id
    ]
    return Storyboard(theme=Theme(music_default_mood=theme_default), scenes=scenes)


def test_inherit_and_none_propagation():
    sb = _sb(
        "none",
        ("s1", ""), ("s2", "tense"), ("s3", ""), ("s4", "hopeful"),
        ("s5", ""), ("s6", "none"), ("s7", ""),
    )
    assert dict(resolve_effective_moods(sb)) == {
        "s1": "none", "s2": "tense", "s3": "tense", "s4": "hopeful",
        "s5": "hopeful", "s6": "none", "s7": "none",
    }


def test_theme_default_heads_the_video():
    sb = _sb("reflective", ("s1", ""), ("s2", ""))
    assert dict(resolve_effective_moods(sb)) == {"s1": "reflective", "s2": "reflective"}


def test_invalid_mood_raises():
    with pytest.raises(ValueError):
        resolve_effective_moods(_sb("none", ("s1", "banana")))
