"""Schema: Scene.music_mood + Theme.music_default_mood (music audio axis)."""
from pipeline.storyboard import Scene, Theme


def test_scene_music_mood_defaults_empty_and_roundtrips():
    sc = Scene(id="s1", section="rising", narration="x", narration_est_sec=1.0)
    assert sc.music_mood == ""
    sc.music_mood = "tense"
    assert Scene.from_dict(sc.to_dict()).music_mood == "tense"


def test_scene_music_mood_omitted_when_empty():
    sc = Scene(id="s1", section="rising", narration="x", narration_est_sec=1.0)
    assert "music_mood" not in sc.to_dict()  # untagged scenes stay clean


def test_theme_music_default_mood_roundtrips():
    t = Theme(music_default_mood="hopeful")
    assert Theme.from_dict(t.to_dict()).music_default_mood == "hopeful"
    assert Theme().music_default_mood == "none"  # default
