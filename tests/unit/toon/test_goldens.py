from pathlib import Path

import pytest
from PIL import Image

from tests.golden_policy import assert_matches_golden
from toon.bank import load_bank
from toon.render import frame
from toon.scene import load_scene, read_scene
from toon.sheets import model_sheet

GOLD = Path("tests/fixtures/toon/goldens")


@pytest.mark.parametrize("t", [1.5, 4.7, 12.2])
def test_scene_001_golden(t):
    bank = load_bank()
    img = frame(load_scene(read_scene("001-lioness-dishes"), bank), bank, t, 960, 540)
    assert_matches_golden(Image.fromarray(img[..., [2, 1, 0]]), GOLD / f"s001_{t:05.2f}.png")


def test_tim_model_sheet_golden(tmp_path):
    bank = load_bank()
    out_file = model_sheet(bank, "tim", tmp_path)
    img = Image.open(out_file)
    # keep the golden fixture small: downscale deterministically before comparing.
    small = img.resize((img.width // 2, img.height // 2), Image.LANCZOS)
    assert_matches_golden(small, GOLD / "tim_model_sheet.png")
