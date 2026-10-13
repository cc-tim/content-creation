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


def test_a_still_matches_the_same_frame_of_a_clip(bank, tmp_path):
    """Phase 2 review I3: a frame is a pure function of its spec. Rendered after the 90 frames
    before it (as a clip renders it) it equals a still from a fresh page, across a cut that
    leaves the seat Tim turned and pushed in shot 1 empty in shot 2."""
    import io
    from contextlib import contextmanager

    import numpy as np
    from PIL import Image

    from toon.scene import load_scene
    from toy3d import runtime
    from toy3d.acting import resolve
    from toy3d.render import render_clip

    shot1 = {"at": 0.0, "set": "office", "camera": "twoshot",
             "place": {"tim": {"spot": "desk_seat", "pose": "typing", "expr": "neutral"}},
             "beats": [{"at": 0.2, "pose": "tim", "to": "turned", "over": 0.3},
                       {"at": 0.2, "pose": "tim", "to": "pushed", "over": 0.3}]}
    shot2 = {"at": 2.0, "set": "office", "camera": "twoshot",
             "place": {"lioness": {"spot": "doorway_in", "pose": "stand", "expr": "stern"}}}
    scene = load_scene({"id": "cut", "engine": "toy3d", "duration": 3.1, "cast": {"tim": "tim", "lioness": "lioness"},
                        "shots": [shot1, shot2]}, bank)
    frames = {}

    @contextmanager
    def recording(w, h, mode="render", **kw):
        with runtime.open_page(w, h, mode, **kw) as page:
            real = page.render_state

            def render_state(spec):
                png = real(spec)
                frames[spec["frame"]] = png
                return png
            page.render_state = render_state
            yield page

    render_clip(scene, bank, tmp_path / "cut.mp4", 3.1, W, H, page_factory=recording)
    with runtime.open_page(W, H, "render") as page:
        runtime.start(page, bank, W, H)
        still = page.render_state(json.loads(json.dumps(resolve(scene, bank, 3.0))))
    a, b = (np.asarray(Image.open(io.BytesIO(x)).convert("RGB")).astype(int) for x in (frames[90], still))
    assert np.abs(a - b).max() <= 1                     # byte-identical on the Mac; the hub GPU's 1 level
