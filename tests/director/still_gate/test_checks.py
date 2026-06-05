from __future__ import annotations

from pathlib import Path

from PIL import Image

from pipeline.director.still_gate.checks import (
    check_blank_substrate,
    check_duplicate_frames,
    run_checks,
)


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


def test_blank_substrate_measures_inset_not_whole_frame(tmp_path):
    # Busy brown border + flat-grey content inset => must fire (inset is what matters).
    from PIL import Image

    from pipeline.composer.base import get_resolution
    from pipeline.composer.book_scene import BookSceneSpec
    w, h = get_resolution("16:9")
    g = BookSceneSpec.open_book(w, h).as_frame_geometry()
    img = Image.new("RGB", (w, h), (20, 20, 20))
    px = img.load()
    for y in range(h):                       # busy stripes EVERYWHERE (incl. border)
        for x in range(0, w, 3):
            px[x, y] = (240, 200, 40)
    # overwrite the inset region with flat grey
    for y in range(g["inset_y"], g["inset_y"] + g["inset_h"]):
        for x in range(g["inset_x"], g["inset_x"] + g["inset_w"]):
            px[x, y] = (136, 136, 136)
    p = tmp_path / "framed_flat.png"
    img.save(p)
    scene = {"id": "s9", "visual": {"type": "article_image", "path": "x"}}
    findings = check_blank_substrate(p, scene)
    assert len(findings) == 1
    assert findings[0].check == "blank_substrate"


def test_run_checks_aggregates_both_checks(tmp_path, flat_grey_png):
    import shutil
    s1 = tmp_path / "s1.png"
    shutil.copy(flat_grey_png, s1)
    s2 = tmp_path / "s2.png"
    shutil.copy(flat_grey_png, s2)
    stills = [
        ("s1", s1, {"id": "s1", "visual": {"type": "article_image"}}),
        ("s2", s2, {"id": "s2", "visual": {"type": "article_image"}}),
    ]
    findings = run_checks(stills)
    kinds = sorted(f.check for f in findings)
    assert "duplicate_frame" in kinds
    assert kinds.count("blank_substrate") == 2
