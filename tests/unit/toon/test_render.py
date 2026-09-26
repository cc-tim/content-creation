import copy
import shutil

import numpy as np
import pytest
from PIL import Image, ImageFilter

from tests.unit.toon.test_timeline import BASE
from toon import render as R
from toon.bank import default_root, load_bank
from toon.scene import load_scene

BANK = load_bank()
SCENE = load_scene(copy.deepcopy(BASE), BANK)


def test_frame_is_deterministic():
    assert np.array_equal(R.frame(SCENE, BANK, 1.3, 480, 270), R.frame(SCENE, BANK, 1.3, 480, 270))


def test_720p_matches_downscaled_1080p():
    hi = Image.fromarray(R.frame(SCENE, BANK, 1.3, 1920, 1080)[..., [2, 1, 0]]).resize((1280, 720), Image.LANCZOS)
    lo = Image.fromarray(R.frame(SCENE, BANK, 1.3, 1280, 720)[..., [2, 1, 0]])
    blur = ImageFilter.GaussianBlur(4)
    diff = np.abs(np.asarray(hi.filter(blur), np.int16) - np.asarray(lo.filter(blur), np.int16))
    assert diff.mean() <= 6.0


def test_parallel_equals_serial():
    times = [0.5, 1.4, 4.6]
    serial = list(R.render_frames(SCENE, BANK, times, 320, 180, workers=1))
    parallel = list(R.render_frames(SCENE, BANK, times, 320, 180, workers=2))
    assert serial == parallel


def test_cache_key_changes_when_a_bank_file_changes(tmp_path):
    root = tmp_path / "bank"
    shutil.copytree(default_root(), root)
    k1 = R.cache_key(SCENE, load_bank(root), 8.0, 320, 180)
    (root / "expressions.yaml").write_text((root / "expressions.yaml").read_text() + "\n# touched\n")
    assert R.cache_key(SCENE, load_bank(root), 8.0, 320, 180) != k1


def test_a_failing_frame_leaves_no_file(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("worker died")
        yield  # pragma: no cover

    monkeypatch.setattr(R, "render_frames", boom)
    out = tmp_path / "x.mp4"
    with pytest.raises(R.ToonRenderError, match="worker died"):
        R.render_clip(SCENE, BANK, out, 1.0, 320, 180)
    assert not list(tmp_path.iterdir())


@pytest.mark.integration
def test_clip_has_exact_frame_count_and_cache_hits(tmp_path, monkeypatch):
    import subprocess

    out = R.render_clip(SCENE, BANK, tmp_path / "c.mp4", 1.25, 320, 180, workers=2)
    n = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
                        "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(out)],
                       capture_output=True, text=True, check=True).stdout.strip()
    assert int(n) == 30
    monkeypatch.setattr(R, "render_frames", lambda *a, **k: (_ for _ in ()).throw(AssertionError("re-rendered")))
    assert R.render_clip(SCENE, BANK, tmp_path / "c.mp4", 1.25, 320, 180) == out
