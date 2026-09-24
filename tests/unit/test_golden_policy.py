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
