from __future__ import annotations

from pipeline.storyboard import Transition


def test_transition_from_dict_minimal():
    """A minimal transition entry parses; sfx is optional."""
    t = Transition.from_dict({"from": "s1", "to": "s2", "style": "fade", "duration_sec": 0.5})
    assert t.from_scene == "s1"
    assert t.to_scene == "s2"
    assert t.style == "fade"
    assert t.duration_sec == 0.5
    assert t.sfx is None


def test_transition_from_dict_with_sfx():
    """sfx field is preserved when present."""
    t = Transition.from_dict({
        "from": "s9",
        "to": "s10",
        "style": "page-turn",
        "duration_sec": 0.5,
        "sfx": "assets/sfx/page_flip.mp3",
    })
    assert t.sfx == "assets/sfx/page_flip.mp3"


def test_transition_to_dict_uses_from_to_keys():
    """Round-trip: to_dict emits 'from' and 'to' (not from_scene/to_scene)."""
    t = Transition(from_scene="s1", to_scene="s2", style="fade", duration_sec=0.3, sfx=None)
    out = t.to_dict()
    assert out["from"] == "s1"
    assert out["to"] == "s2"
    assert "from_scene" not in out
    assert "to_scene" not in out


def test_transition_to_dict_omits_sfx_when_none():
    """sfx is omitted from output dict when None to keep storyboards lean."""
    t = Transition(from_scene="s1", to_scene="s2", style="fade", duration_sec=0.3, sfx=None)
    out = t.to_dict()
    assert "sfx" not in out
