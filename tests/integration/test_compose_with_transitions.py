"""Integration: storyboard with a transition produces a master concat that
includes a transition clip between the two scenes.

These tests run real ffmpeg invocations and may take 10-30s each.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from pipeline.composer.transitions import REGISTRY


def _ffprobe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def _make_solid_clip(path: Path, *, duration: float, color: str,
                      width: int = 320, height: int = 180, fps: int = 30) -> Path:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "lavfi", "-i", f"color=c={color}:s={width}x{height}:r={fps}:d={duration}",
         "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
         "-t", str(duration),
         "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-ar", "48000", "-b:a", "128k",
         "-shortest", str(path)],
        check=True,
    )
    return path


def test_concat_with_transition_clip_increases_total_duration(tmp_path: Path):
    """When we splice a transition clip into the concat list, the output is
    longer by the transition's duration."""
    from pipeline.composer.transitions import TransitionConfig, render_transition

    a = _make_solid_clip(tmp_path / "scene1.mp4", duration=1.0, color="red")
    b = _make_solid_clip(tmp_path / "scene2.mp4", duration=1.0, color="blue")
    cfg = TransitionConfig(style="fade", duration_sec=0.5, sfx=None)
    cache = tmp_path / "cache"
    transition_clip = render_transition(a, b, cfg, cache, width=320, height=180, fps=30)
    assert transition_clip is not None and transition_clip.exists()

    # Build a concat list and run the demuxer.
    filelist = tmp_path / "list.txt"
    filelist.write_text("\n".join(f"file '{p.resolve()}'" for p in [a, transition_clip, b]),
                         encoding="utf-8")
    out = tmp_path / "out.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "concat", "-safe", "0", "-i", str(filelist),
         "-c:v", "copy", "-c:a", "aac", "-ar", "48000", "-b:a", "128k", str(out)],
        check=True,
    )
    duration = _ffprobe_duration(out)
    # Two 1.0s scenes + one 0.5s transition = ~2.5s
    assert 2.4 <= duration <= 2.6, f"Expected ~2.5s, got {duration}s"


def test_splice_transitions_inserts_transition_between_scenes(tmp_path: Path):
    from pipeline.stages.compose import splice_transitions
    from pipeline.storyboard import Storyboard, Scene, Transition
    s1 = _make_solid_clip(tmp_path / "s1.mp4", duration=1.0, color="red")
    s2 = _make_solid_clip(tmp_path / "s2.mp4", duration=1.0, color="blue")
    sb = Storyboard(
        scenes=[
            Scene(id="s1", section="content", narration="a", narration_est_sec=1.0),
            Scene(id="s2", section="content", narration="b", narration_est_sec=1.0),
        ],
        transitions=[Transition("s1", "s2", "fade", 0.5, None)],
    )
    spliced = splice_transitions(
        scene_paths=[s1, s2],
        scene_ids=["s1", "s2"],
        sb=sb,
        cache_dir=tmp_path / "transitions",
        width=320, height=180, fps=30,
    )
    assert len(spliced) == 3
    assert spliced[0] == s1
    assert spliced[2] == s2
    assert spliced[1].name.endswith(".mp4")
    assert spliced[1].parent == tmp_path / "transitions"


def test_splice_transitions_skips_hard_cut(tmp_path: Path):
    from pipeline.stages.compose import splice_transitions
    from pipeline.storyboard import Storyboard, Scene, Transition
    s1 = _make_solid_clip(tmp_path / "s1.mp4", duration=1.0, color="red")
    s2 = _make_solid_clip(tmp_path / "s2.mp4", duration=1.0, color="blue")
    sb = Storyboard(
        scenes=[
            Scene(id="s1", section="content", narration="a", narration_est_sec=1.0),
            Scene(id="s2", section="content", narration="b", narration_est_sec=1.0),
        ],
        transitions=[Transition("s1", "s2", "none", 0.0, None)],
    )
    spliced = splice_transitions(
        scene_paths=[s1, s2],
        scene_ids=["s1", "s2"],
        sb=sb,
        cache_dir=tmp_path / "cache",
        width=320, height=180, fps=30,
    )
    assert len(spliced) == 2  # no clip inserted for "none"


def test_splice_transitions_passthrough_when_no_transitions(tmp_path: Path):
    from pipeline.stages.compose import splice_transitions
    from pipeline.storyboard import Storyboard, Scene
    s1 = _make_solid_clip(tmp_path / "s1.mp4", duration=1.0, color="red")
    s2 = _make_solid_clip(tmp_path / "s2.mp4", duration=1.0, color="blue")
    sb = Storyboard(scenes=[
        Scene(id="s1", section="content", narration="a", narration_est_sec=1.0),
        Scene(id="s2", section="content", narration="b", narration_est_sec=1.0),
    ])
    spliced = splice_transitions(
        scene_paths=[s1, s2],
        scene_ids=["s1", "s2"],
        sb=sb,
        cache_dir=tmp_path / "cache",
        width=320, height=180, fps=30,
    )
    assert spliced == [s1, s2]
