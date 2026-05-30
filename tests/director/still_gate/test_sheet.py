from pathlib import Path

from PIL import Image

from pipeline.director.still_gate.sheet import build_contact_sheet


def _png(path: Path, color) -> Path:
    Image.new("RGB", (1280, 720), color).save(path)
    return path


def test_build_contact_sheet_grids_all_stills(tmp_path: Path):
    items = [
        ("s1", _png(tmp_path / "s1.png", (200, 0, 0)), "article_image · a.png"),
        ("s2", _png(tmp_path / "s2.png", (0, 200, 0)), "chart · bar"),
        ("s3", _png(tmp_path / "s3.png", (0, 0, 200)), "text_card"),
    ]
    out = build_contact_sheet(items, tmp_path / "sheet.png", columns=2)
    assert out.exists()
    with Image.open(out) as im:
        w, h = im.size
        assert w > 0 and h > 0
