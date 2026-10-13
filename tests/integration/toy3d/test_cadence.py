"""E11 S12-15 (standards anatomy 9): toy3d's frames survive compose's concat normalisation. The
worked scene's opening orbit (0.5–2.0 s), rendered by the toy3d runner at the bank's fps, goes
through the exact filter compose's `_concat_scenes` applies; no output step may read as a
duplicate (the 24 fps judder the 2.5D engine once had)."""
import statistics
import subprocess

import numpy as np
import pytest

from pipeline.stages.compose import COMPOSE_FPS

pytestmark = pytest.mark.integration

W, H = 320, 180
T_START, T_END = 0.5, 2.0
NEAR_DUPLICATE_FRACTION = 0.15


def _decode(path):
    data = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                          capture_output=True, check=True).stdout
    n = len(data) // (W * H * 3)
    return [np.frombuffer(data[i * W * H * 3:(i + 1) * W * H * 3], np.uint8).reshape(H, W, 3) for i in range(n)]


def test_toy3d_cadence_survives_compose_concat_normalisation(worked, bank, tmp_path):
    from toy3d.acting import resolve
    from toy3d.render import render_clip

    def window(scene, bank_, t):                       # the orbit, T_START onwards
        return resolve(scene, bank_, T_START + t)

    src = render_clip(worked, bank, tmp_path / "orbit.mp4", T_END - T_START, W, H, resolve=window)
    norm = tmp_path / "orbit_norm.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
                    "-vf", f"setpts=PTS-STARTPTS,fps={COMPOSE_FPS},format=yuv420p,setsar=1",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "medium", str(norm)],
                   check=True)
    frames = _decode(norm)
    assert len(frames) == round((T_END - T_START) * COMPOSE_FPS)
    diffs = [float(np.abs(frames[i + 1].astype(np.int16) - frames[i].astype(np.int16)).mean())
             for i in range(len(frames) - 1)]
    threshold = NEAR_DUPLICATE_FRACTION * statistics.median(diffs)
    dupes = [(i, round(d, 3)) for i, d in enumerate(diffs) if d < threshold]
    assert not dupes, f"near-duplicate steps after normalising to {COMPOSE_FPS} fps: {dupes}"
