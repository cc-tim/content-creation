from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from pipeline.composer.transitions import (
    REGISTRY,
    SUPPORTED_STYLES,
    HardCutRenderer,
    TransitionConfig,
    XfadeRenderer,
    render_transition,
    transition_cache_key,
)
from pipeline.storyboard import Storyboard, Transition


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


def test_transition_config_constructs_with_valid_style():
    cfg = TransitionConfig(style="fade", duration_sec=0.5, sfx=None)
    assert cfg.style == "fade"


def test_transition_config_rejects_unknown_style():
    with pytest.raises(ValueError, match="Unknown transition style"):
        TransitionConfig(style="ribbon", duration_sec=0.5, sfx=None)


def test_supported_styles_set_matches_spec():
    assert {"none", "fade", "page-turn", "slide", "wipe"} == SUPPORTED_STYLES


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


def _make_test_clip(path: Path, *, duration: float, color: str, width: int = 320, height: int = 180, fps: int = 30) -> Path:
    """Helper: create a small solid-color test clip with silent audio."""
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", f"color=c={color}:s={width}x{height}:r={fps}:d={duration}",
            "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
            "-t", str(duration),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "48000", "-b:a", "128k",
            "-shortest", str(path),
        ],
        check=True,
    )
    return path


def test_xfade_renderer_emits_clip_of_expected_duration(tmp_path: Path):
    a = _make_test_clip(tmp_path / "a.mp4", duration=1.0, color="red")
    b = _make_test_clip(tmp_path / "b.mp4", duration=1.0, color="blue")
    out = tmp_path / "t.mp4"
    cfg = TransitionConfig(style="fade", duration_sec=0.5, sfx=None)

    renderer = XfadeRenderer(xfade_name="fade")
    result = renderer.render(a, b, cfg, out, width=320, height=180, fps=30)

    assert result == out
    assert out.exists() and out.stat().st_size > 0
    # ffprobe duration should be ~0.5s (allow ±0.1s for encoding rounding)
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(out)],
        capture_output=True, text=True, check=True,
    )
    duration = float(probe.stdout.strip())
    assert 0.4 <= duration <= 0.6, f"Expected ~0.5s, got {duration}s"


def test_xfade_renderer_with_sfx_mixes_audio(tmp_path: Path):
    """sfx file is mixed into the transition's audio track."""
    a = _make_test_clip(tmp_path / "a.mp4", duration=1.0, color="red")
    b = _make_test_clip(tmp_path / "b.mp4", duration=1.0, color="blue")
    sfx = tmp_path / "sfx.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=0.5",
         "-c:a", "pcm_s16le", str(sfx)],
        check=True,
    )
    out = tmp_path / "t.mp4"
    cfg = TransitionConfig(style="fade", duration_sec=0.5, sfx=str(sfx))

    renderer = XfadeRenderer(xfade_name="fade")
    result = renderer.render(a, b, cfg, out, width=320, height=180, fps=30)

    assert result == out
    # Verify the output has an audio stream
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=codec_name",
         "-of", "default=noprint_wrappers=1:nokey=1", str(out)],
        capture_output=True, text=True, check=True,
    )
    assert probe.stdout.strip() == "aac"


def test_registry_covers_all_supported_styles():
    assert set(REGISTRY.keys()) == SUPPORTED_STYLES


def test_registry_page_turn_is_xfade_slideleft_in_v1():
    """v1 ships page-turn as XfadeRenderer(slideleft); document the alias."""
    page_turn = REGISTRY["page-turn"]
    assert isinstance(page_turn, XfadeRenderer)
    assert page_turn.xfade_name == "slideleft"


def test_registry_none_is_hard_cut():
    assert isinstance(REGISTRY["none"], HardCutRenderer)


def test_cache_key_deterministic(tmp_path: Path):
    a = _make_test_clip(tmp_path / "a.mp4", duration=0.5, color="red")
    b = _make_test_clip(tmp_path / "b.mp4", duration=0.5, color="blue")
    cfg = TransitionConfig(style="fade", duration_sec=0.5, sfx=None)
    k1 = transition_cache_key(a, b, cfg)
    k2 = transition_cache_key(a, b, cfg)
    assert k1 == k2
    assert len(k1) == 40  # sha1 hex digest


def test_cache_key_differs_with_style(tmp_path: Path):
    a = _make_test_clip(tmp_path / "a.mp4", duration=0.5, color="red")
    b = _make_test_clip(tmp_path / "b.mp4", duration=0.5, color="blue")
    cfg1 = TransitionConfig(style="fade", duration_sec=0.5, sfx=None)
    cfg2 = TransitionConfig(style="slide", duration_sec=0.5, sfx=None)
    assert transition_cache_key(a, b, cfg1) != transition_cache_key(a, b, cfg2)


def test_cache_key_differs_with_sfx(tmp_path: Path):
    a = _make_test_clip(tmp_path / "a.mp4", duration=0.5, color="red")
    b = _make_test_clip(tmp_path / "b.mp4", duration=0.5, color="blue")
    cfg1 = TransitionConfig(style="fade", duration_sec=0.5, sfx=None)
    cfg2 = TransitionConfig(style="fade", duration_sec=0.5, sfx="assets/sfx/whoosh.mp3")
    assert transition_cache_key(a, b, cfg1) != transition_cache_key(a, b, cfg2)


def test_render_transition_returns_none_for_hard_cut(tmp_path: Path):
    """The dispatcher returns None when style='none'."""
    a = _make_test_clip(tmp_path / "a.mp4", duration=0.5, color="red")
    b = _make_test_clip(tmp_path / "b.mp4", duration=0.5, color="blue")
    cfg = TransitionConfig(style="none", duration_sec=0.0, sfx=None)
    result = render_transition(a, b, cfg, tmp_path / "cache", width=320, height=180, fps=30)
    assert result is None


def test_render_transition_caches_result(tmp_path: Path):
    """Second call with same inputs returns the same cached path without re-rendering."""
    a = _make_test_clip(tmp_path / "a.mp4", duration=0.5, color="red")
    b = _make_test_clip(tmp_path / "b.mp4", duration=0.5, color="blue")
    cache_dir = tmp_path / "cache"
    cfg = TransitionConfig(style="fade", duration_sec=0.5, sfx=None)

    p1 = render_transition(a, b, cfg, cache_dir, width=320, height=180, fps=30)
    assert p1 is not None and p1.exists()
    mtime1 = p1.stat().st_mtime

    p2 = render_transition(a, b, cfg, cache_dir, width=320, height=180, fps=30)
    assert p2 == p1
    assert p2.stat().st_mtime == mtime1  # not re-rendered
