"""E11 S12-14 (Review Focus 1): a toy3d clip has exactly round(narration × COMPOSE_FPS) frames, on
the real browser. A narration longer than the authored 8.0 s holds the last shot: the camera path
runs past its last tween and holds, and the cast keeps acting. A shorter one cuts."""
import json
import subprocess

import pytest

from pipeline.stages.compose import COMPOSE_FPS

pytestmark = pytest.mark.integration

W, H = 320, 180


def _frames(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
                          "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True)
    return int(out.stdout.strip())


@pytest.mark.parametrize("narration", [8.0, 9.2, 6.1])
def test_clip_frame_count_equals_narration(worked, bank, tmp_path, narration):
    from toy3d.render import render_clip

    out = render_clip(worked, bank, tmp_path / "s.mp4", narration, W, H)
    assert _frames(out) == round(narration * COMPOSE_FPS)


def test_a_longer_narration_holds_the_last_shot(worked, bank):
    from toy3d.acting import resolve

    end = json.dumps(resolve(worked, bank, 7.6)["camera"])               # the pull-back's last tween ends
    for t in (8.0, 9.0, 9.2):
        later = resolve(worked, bank, t)
        assert json.dumps(later["camera"]) == end                        # the camera holds…
        assert later["actors"]["tim"]["face"] == "tim_shock"              # …on the same shot
    assert resolve(worked, bank, 9.0)["actors"]["lioness"]["joints"] != resolve(worked, bank, 9.2)["actors"]["lioness"]["joints"]
