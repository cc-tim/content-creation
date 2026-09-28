"""Cadence guard: toon's fps must survive compose's concat normalisation.

Compose's ``_concat_scenes`` re-times every scene segment onto ``COMPOSE_FPS`` (see
``pipeline.stages.compose``) before concatenating. If toon renders at a different fps,
ffmpeg's ``fps`` filter resamples by nearest-neighbour, not motion interpolation, so some
output frames become exact (or near-exact) repeats of the previous frame -- the camera-push
judder the EM's hub compose smoke caught (24 fps toon into a 30 fps concat).

This test renders scene 001's shot-1 camera push (front34_push, shot span 0.0-3.5s) across
about t=0.5-2.0s -- past the camera ease-in, where `smooth()` in timeline.py's rel_move/span
ramp is still near-flat -- pushes the frames through the exact ffmpeg filter compose's concat
uses, and asserts no output transition reads as a duplicate.
"""
from __future__ import annotations

import statistics
import subprocess
from pathlib import Path

import numpy as np
import pytest

from pipeline.stages.compose import COMPOSE_FPS
from toon.bank import load_bank
from toon.render import render_frames
from toon.scene import load_scene, read_scene

pytestmark = pytest.mark.integration

WIDTH, HEIGHT = 320, 180
T_START, T_END = 0.5, 2.0
# The smoke that found the bug: near-duplicates around ~0.03 mean abs diff vs. ~0.55 on
# genuine motion steps -- comfortably below 15% of a normal step.
NEAR_DUPLICATE_FRACTION = 0.15


def _decode_bgr24(path: Path, width: int, height: int) -> list[np.ndarray]:
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
        capture_output=True, check=True,
    )
    frame_size = width * height * 3
    data = proc.stdout
    n = len(data) // frame_size
    return [
        np.frombuffer(data[i * frame_size:(i + 1) * frame_size], dtype=np.uint8).reshape(height, width, 3)
        for i in range(n)
    ]


def _render_source_clip(out_path: Path) -> None:
    """Render shot 1's camera push at the bank's native fps, the same way render_clip does."""
    bank = load_bank()
    scene = load_scene(read_scene("001-lioness-dishes"), bank)
    fps = bank.style.fps
    times = [i / fps for i in range(round(T_START * fps), round(T_END * fps) + 1)]
    proc = subprocess.Popen(
        [
            "ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgra",
            "-s", f"{WIDTH}x{HEIGHT}", "-r", str(fps), "-i", "-",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "medium",
            str(out_path),
        ],
        stdin=subprocess.PIPE,
    )
    assert proc.stdin is not None
    for data in render_frames(scene, bank, times, WIDTH, HEIGHT):
        proc.stdin.write(data)
    proc.stdin.close()
    assert proc.wait() == 0, "rendering the shot-1 source clip failed"


def _normalise_to_compose_fps(src: Path, out_path: Path) -> None:
    """The exact filter compose._concat_scenes applies to every segment before concat."""
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
            "-vf", f"setpts=PTS-STARTPTS,fps={COMPOSE_FPS},format=yuv420p,setsar=1",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "medium",
            str(out_path),
        ],
        check=True,
    )


def test_toon_cadence_survives_compose_concat_normalisation(tmp_path):
    src = tmp_path / "shot1_push.mp4"
    norm = tmp_path / "shot1_push_normalised.mp4"
    _render_source_clip(src)
    _normalise_to_compose_fps(src, norm)

    frames = _decode_bgr24(norm, WIDTH, HEIGHT)
    assert len(frames) >= 3, f"expected several normalised frames, got {len(frames)}"

    diffs = [
        float(np.abs(frames[i + 1].astype(np.int16) - frames[i].astype(np.int16)).mean())
        for i in range(len(frames) - 1)
    ]
    median = statistics.median(diffs)
    threshold = NEAR_DUPLICATE_FRACTION * median
    near_duplicates = [(i, d) for i, d in enumerate(diffs) if d < threshold]

    assert not near_duplicates, (
        f"{len(near_duplicates)}/{len(diffs)} frame-to-frame steps after normalising to "
        f"{COMPOSE_FPS} fps look like duplicates (< {NEAR_DUPLICATE_FRACTION:.0%} of median "
        f"step {median:.3f}): {near_duplicates}; full diffs: {[round(d, 3) for d in diffs]}"
    )
