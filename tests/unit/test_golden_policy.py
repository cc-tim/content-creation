"""Golden policy: hub-canonical goldens, skipped (counted) elsewhere (spec 4.4, A6)."""
from __future__ import annotations

import pytest
from PIL import Image

from tests import golden_policy
from tests.golden_policy import SKIP_REASON, assert_matches_golden


@pytest.fixture
def golden(tmp_path):
    path = tmp_path / "g" / "x.png"
    path.parent.mkdir()
    Image.new("RGB", (8, 8), "white").save(path)
    return path


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("UPDATE_GOLDENS", raising=False)
    monkeypatch.delenv("PIPELINE_GOLDEN_STRICT", raising=False)


def _img(color="white"):
    return Image.new("RGB", (8, 8), color)


def test_linux_compares_and_passes(monkeypatch, golden):
    monkeypatch.setattr(golden_policy.sys, "platform", "linux")
    assert_matches_golden(_img(), golden)


def test_linux_compares_and_detects_drift(monkeypatch, golden):
    monkeypatch.setattr(golden_policy.sys, "platform", "linux")
    with pytest.raises(AssertionError, match="drifted"):
        assert_matches_golden(_img("black"), golden)


def test_accepts_png_path(monkeypatch, golden, tmp_path):
    monkeypatch.setattr(golden_policy.sys, "platform", "linux")
    p = tmp_path / "r.png"
    _img().save(p)
    assert_matches_golden(p, golden)


def test_darwin_skips_with_documented_reason(monkeypatch, golden):
    monkeypatch.setattr(golden_policy.sys, "platform", "darwin")
    with pytest.raises(pytest.skip.Exception) as ei:
        assert_matches_golden(_img("black"), golden)  # would drift; must skip, not fail
    assert str(ei.value.msg) == SKIP_REASON
    assert SKIP_REASON == (
        "golden PNGs are hub-canonical (linux); set PIPELINE_GOLDEN_STRICT=1 to compare"
    )


def test_darwin_update_goldens_is_hard_error(monkeypatch, golden):
    monkeypatch.setattr(golden_policy.sys, "platform", "darwin")
    monkeypatch.setenv("UPDATE_GOLDENS", "1")
    before = golden.read_bytes()
    with pytest.raises(RuntimeError, match="hub only"):
        assert_matches_golden(_img("black"), golden)
    assert golden.read_bytes() == before


def test_darwin_strict_forces_compare(monkeypatch, golden):
    monkeypatch.setattr(golden_policy.sys, "platform", "darwin")
    monkeypatch.setenv("PIPELINE_GOLDEN_STRICT", "1")
    assert_matches_golden(_img(), golden)
    with pytest.raises(AssertionError, match="drifted"):
        assert_matches_golden(_img("black"), golden)


def test_linux_update_goldens_writes(monkeypatch, tmp_path):
    monkeypatch.setattr(golden_policy.sys, "platform", "linux")
    monkeypatch.setenv("UPDATE_GOLDENS", "1")
    target = tmp_path / "new" / "y.png"
    assert_matches_golden(_img("black"), target)
    assert target.exists()


def test_golden_test_files_use_shared_helper():
    """The three duplicated _assert_golden helpers are gone (single policy)."""
    from pathlib import Path

    unit = Path(__file__).parent
    for name in ("test_chart.py", "test_chart_anim.py", "test_callout.py"):
        src = (unit / name).read_text(encoding="utf-8")
        assert "assert_matches_golden" in src, name
        assert "UPDATE_GOLDENS" not in src, name
        assert "def _assert_golden" not in src and "def _assert_anim_golden" not in src, name


# -- the tolerant helper (E11 S12-12): GPU-rendered goldens, hub-canonical, compared everywhere --

def _noisy(n_off, level, size=(100, 100)):
    import numpy as np

    a = np.full((size[1], size[0], 3), 128, np.uint8)
    flat = a.reshape(-1, 3)
    flat[:n_off] = 128 + level
    return Image.fromarray(a)


def _blob(side, level):
    import numpy as np

    a = np.full((100, 100, 3), 128, np.uint8)
    a[40:40 + side, 40:40 + side] = 128 + level
    return Image.fromarray(a)


@pytest.fixture
def grey(tmp_path):
    path = tmp_path / "g" / "grey.png"
    path.parent.mkdir()
    Image.new("RGB", (100, 100), (128, 128, 128)).save(path)
    return path


LOOSE = {"mean": 1.0, "p999": 50.0, "max_frac": 0.01, "tile": 40.0}


@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_close_compare_runs_on_both_machines(monkeypatch, grey, platform):
    from tests.golden_policy import assert_close_to_golden

    monkeypatch.setattr(golden_policy.sys, "platform", platform)
    stats = assert_close_to_golden(_noisy(5, 3), grey, **LOOSE)            # 5 px off by 3: noise
    assert stats["frac8"] == 0 and stats["max"] == 3


@pytest.mark.parametrize(("image", "limits", "metric"), [
    (lambda: _noisy(2000, 2), {**LOOSE, "mean": 0.1}, "mean"),             # many small: the mean
    (lambda: _noisy(200, 60), {**LOOSE, "max_frac": 0.001}, "frac8"),      # a few large: the fraction
    (lambda: _noisy(30, 120), {**LOOSE, "p999": 10.0}, "p999"),            # the tail
    (lambda: _blob(20, 120), {"mean": 10.0, "p999": 255.0, "max_frac": 1.0, "tile": 20.0}, "tile"),  # one blob
], ids=["mean", "frac8", "p999", "tile"])
def test_close_compare_fails_beyond_each_limit(monkeypatch, grey, image, limits, metric):
    from tests.golden_policy import assert_close_to_golden

    monkeypatch.setattr(golden_policy.sys, "platform", "linux")
    with pytest.raises(AssertionError, match=f"beyond tolerance on [^:]*{metric}"):
        assert_close_to_golden(image(), grey, **limits)


def test_close_compare_fails_on_a_size_change(monkeypatch, grey):
    from tests.golden_policy import assert_close_to_golden

    monkeypatch.setattr(golden_policy.sys, "platform", "linux")
    with pytest.raises(AssertionError, match="size"):
        assert_close_to_golden(Image.new("RGB", (100, 90), (128, 128, 128)), grey, **LOOSE)


def test_close_update_goldens_off_hub_is_a_hard_error(monkeypatch, grey):
    from tests.golden_policy import assert_close_to_golden

    monkeypatch.setattr(golden_policy.sys, "platform", "darwin")
    monkeypatch.setenv("UPDATE_GOLDENS", "1")
    before = grey.read_bytes()
    with pytest.raises(RuntimeError, match="hub only"):
        assert_close_to_golden(_noisy(5, 90), grey, **LOOSE)
    assert grey.read_bytes() == before


def test_close_update_goldens_on_the_hub_writes(monkeypatch, tmp_path):
    from tests.golden_policy import assert_close_to_golden

    monkeypatch.setattr(golden_policy.sys, "platform", "linux")
    monkeypatch.setenv("UPDATE_GOLDENS", "1")
    target = tmp_path / "new" / "z.png"
    assert assert_close_to_golden(_noisy(5, 90), target, **LOOSE) == {}
    assert target.exists()


def test_a_missing_close_golden_names_the_hub_mint(monkeypatch, tmp_path):
    from tests.golden_policy import assert_close_to_golden

    monkeypatch.setattr(golden_policy.sys, "platform", "darwin")
    with pytest.raises(AssertionError, match="UPDATE_GOLDENS=1 on the hub"):
        assert_close_to_golden(_noisy(5, 3), tmp_path / "none.png", **LOOSE)
