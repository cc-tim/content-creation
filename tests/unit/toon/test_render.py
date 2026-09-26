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

# Ruling R8 guard: x_card/check_pill already scale their own size by pen.px internally, so the
# renderer must call them without a pre-scaled size= argument. A scene with both cards shown,
# fully popped, lets the 720p-vs-downscaled-1080p comparison catch a reintroduced double-scale.
_CARD_DATA = copy.deepcopy(BASE)
_CARD_DATA["shots"][0]["beats"] += [
    {"at": 1.6, "show": {"x_card": "bulb", "at": [0.64, 0.30]}},
    {"at": 1.6, "show": {"check_pill": "bulb", "at": [0.08, 0.30]}},
]
CARD_SCENE = load_scene(_CARD_DATA, BANK)
CARD_T = 2.0  # rel 2.0 in shot 0: beat at 1.6 + default pop duration 0.25s -> fully popped (k=1)


def _region_diff(t, at_frac, size_w_1080, size_h_1080, margin=30):
    """Mean abs diff (720p-native vs 1080p-downscaled-to-720p) inside one graphic's bounding box."""
    px_lo = 720 / 1080
    x0 = at_frac[0] * 1280 - margin
    y0 = at_frac[1] * 720 - margin
    x1 = at_frac[0] * 1280 + size_w_1080 * px_lo + margin
    y1 = at_frac[1] * 720 + size_h_1080 * px_lo + margin
    hi = Image.fromarray(R.frame(CARD_SCENE, BANK, t, 1920, 1080)[..., [2, 1, 0]]).resize((1280, 720), Image.LANCZOS)
    lo = Image.fromarray(R.frame(CARD_SCENE, BANK, t, 1280, 720)[..., [2, 1, 0]])
    blur = ImageFilter.GaussianBlur(4)
    box = (max(int(x0), 0), max(int(y0), 0), min(int(x1), 1280), min(int(y1), 720))
    hi_arr = np.asarray(hi.filter(blur), np.int16)[box[1]:box[3], box[0]:box[2]]
    lo_arr = np.asarray(lo.filter(blur), np.int16)[box[1]:box[3], box[0]:box[2]]
    return np.abs(hi_arr - lo_arr).mean()


def test_720p_matches_downscaled_1080p_for_x_card_region():
    assert _region_diff(CARD_T, (0.64, 0.30), 140, 140) <= 6.0


def test_720p_matches_downscaled_1080p_for_check_pill_region():
    assert _region_diff(CARD_T, (0.08, 0.30), 210, 84) <= 6.0


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
