from __future__ import annotations

from pathlib import Path

from PIL import Image

from pipeline.director.still_gate.checks import check_blank_substrate, check_duplicate_frames


def _png(path: Path, color) -> Path:
    Image.new("RGB", (256, 256), color).save(path)
    return path


def test_duplicate_frames_flags_identical_stills(tmp_path: Path):
    a = ("s1", _png(tmp_path / "s1.png", (100, 100, 100)))
    b = ("s2", _png(tmp_path / "s2.png", (100, 100, 100)))  # identical
    findings = check_duplicate_frames([a, b])
    assert len(findings) == 1
    assert findings[0].check == "duplicate_frame"
    assert "s2" in findings[0].scene_id or "s2" in findings[0].message


def test_duplicate_frames_true_negative_on_distinct_stills(tmp_path: Path):
    a = ("s1", _png(tmp_path / "s1.png", (10, 10, 10)))
    b = ("s2", _png(tmp_path / "s2.png", (240, 30, 30)))  # clearly different
    assert check_duplicate_frames([a, b]) == []


def test_blank_substrate_flags_flat_image(flat_grey_png):
    scene = {"id": "s24", "visual": {"type": "article_image", "path": "x"}}
    findings = check_blank_substrate(flat_grey_png, scene)
    assert len(findings) == 1
    assert findings[0].check == "blank_substrate"


def test_blank_substrate_true_negative_on_busy_image(busy_png):
    scene = {"id": "s1", "visual": {"type": "article_image", "path": "x"}}
    assert check_blank_substrate(busy_png, scene) == []
