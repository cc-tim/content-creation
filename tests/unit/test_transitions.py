from __future__ import annotations

import pytest

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


# --- Storyboard transitions field ---

import json
from pathlib import Path

from pipeline.storyboard import Storyboard


def _minimal_scene_dict(scene_id: str) -> dict:
    return {
        "id": scene_id,
        "section": "content",
        "narration": f"narration for {scene_id}",
        "narration_est_sec": 1.0,
    }


def test_storyboard_defaults_transitions_to_empty_list():
    sb = Storyboard()
    assert sb.transitions == []


def test_storyboard_from_dict_without_transitions_key():
    """Existing storyboards (no transitions key) still parse and produce []."""
    data = {
        "version": 1,
        "format": "standard",
        "target_duration_sec": 720,
        "aspect_ratio": "16:9",
        "scenes": [_minimal_scene_dict("s1"), _minimal_scene_dict("s2")],
    }
    sb = Storyboard.from_dict(data)
    assert sb.transitions == []


def test_storyboard_from_dict_with_transitions():
    data = {
        "version": 1,
        "scenes": [_minimal_scene_dict("s1"), _minimal_scene_dict("s2")],
        "transitions": [
            {"from": "s1", "to": "s2", "style": "page-turn", "duration_sec": 0.5},
        ],
    }
    sb = Storyboard.from_dict(data)
    assert len(sb.transitions) == 1
    assert sb.transitions[0].from_scene == "s1"
    assert sb.transitions[0].style == "page-turn"


def test_storyboard_to_dict_omits_transitions_key_when_empty():
    """Don't emit an empty transitions: [] for backwards-compatible storyboards."""
    sb = Storyboard(scenes=[])
    out = sb.to_dict()
    assert "transitions" not in out


def test_storyboard_to_dict_includes_transitions_when_set():
    from pipeline.storyboard import Transition
    sb = Storyboard(
        scenes=[],
        transitions=[Transition("s1", "s2", "fade", 0.3, None)],
    )
    out = sb.to_dict()
    assert out["transitions"] == [{"from": "s1", "to": "s2", "style": "fade", "duration_sec": 0.3}]


def test_storyboard_round_trip_with_transitions(tmp_path: Path):
    from pipeline.storyboard import Transition
    sb = Storyboard(
        scenes=[],
        transitions=[
            Transition("s1", "s2", "page-turn", 0.5, "assets/sfx/page_flip.mp3"),
            Transition("s5", "s6", "fade", 0.3, None),
        ],
    )
    p = tmp_path / "sb.json"
    sb.save(p)
    loaded = Storyboard.load(p)
    assert len(loaded.transitions) == 2
    assert loaded.transitions[0].sfx == "assets/sfx/page_flip.mp3"
    assert loaded.transitions[1].sfx is None


# --- TransitionConfig + style validation ---

from pipeline.composer.transitions import (
    SUPPORTED_STYLES,
    TransitionConfig,
    HardCutRenderer,
)


def test_transition_config_constructs_with_valid_style():
    cfg = TransitionConfig(style="fade", duration_sec=0.5, sfx=None)
    assert cfg.style == "fade"


def test_transition_config_rejects_unknown_style():
    with pytest.raises(ValueError, match="Unknown transition style"):
        TransitionConfig(style="ribbon", duration_sec=0.5, sfx=None)


def test_supported_styles_set_matches_spec():
    assert SUPPORTED_STYLES == {"none", "fade", "page-turn", "slide", "wipe"}


def test_transition_config_from_storyboard_transition():
    from pipeline.storyboard import Transition
    t = Transition("s1", "s2", "page-turn", 0.5, "assets/sfx/page_flip.mp3")
    cfg = TransitionConfig.from_transition(t)
    assert cfg.style == "page-turn"
    assert cfg.duration_sec == 0.5
    assert cfg.sfx == "assets/sfx/page_flip.mp3"


def test_hard_cut_renderer_returns_none(tmp_path: Path):
    """HardCutRenderer emits no clip — concat just stitches scenes directly."""
    renderer = HardCutRenderer()
    cfg = TransitionConfig(style="none", duration_sec=0.0, sfx=None)
    a = tmp_path / "a.mp4"
    b = tmp_path / "b.mp4"
    out = tmp_path / "t.mp4"
    a.write_bytes(b"")  # input files don't need to be real for HardCut
    b.write_bytes(b"")
    result = renderer.render(a, b, cfg, out, width=1280, height=720, fps=30)
    assert result is None
    assert not out.exists()
