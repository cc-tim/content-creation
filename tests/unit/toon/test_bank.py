import shutil

import pytest

from toon.bank import BankError, bank_files, default_root, load_bank
from toon.engine import palette


def test_v0_bank_holds_exactly_the_picked_items():
    b = load_bank()
    assert set(b.characters) == {"tim", "lioness"}
    assert set(b.expressions) == {"neutral", "talking", "happy", "focused", "worried", "shocked",
                                  "angry", "glum", "deflated"}
    assert set(b.poses) == {"sit_typing", "sit_shock", "stand_rest", "stand_point", "stand_wash",
                            "stand_sink_idle"}
    assert set(b.sets) == {"office", "kitchen"}
    assert set(b.props) == {"idea_bulb", "plate", "plate_stack"}
    assert set(b.cameras) == {"front34_push", "two_shot", "side_truck", "close_push", "ots_mid",
                              "screen_insert"}
    assert not [f for f in bank_files(b.root) if "fire" in f.stem]   # campfire was not picked


def test_every_item_carries_provenance():
    b = load_bank()
    groups = [b.characters, b.expressions, b.poses, b.sets, b.props, b.cameras, {"style": b.style}]
    for group in groups:
        for name, item in group.items():
            assert item.picked.date and item.picked.source, name


def test_style_palette_matches_engine_palette():
    for name, rgb in load_bank().style.palette.items():
        assert tuple(rgb) == getattr(palette, name.upper()), name


def test_unknown_field_fails_with_file_and_path(tmp_path):
    root = tmp_path / "bank"
    shutil.copytree(default_root(), root)
    p = root / "poses.yaml"
    p.write_text(p.read_text().replace("stand_rest:\n", "stand_rest:\n  sparkle: 1\n", 1))
    with pytest.raises(BankError, match=r"poses\.yaml:stand_rest: sparkle"):
        load_bank(root)


def test_missing_bank_dir(tmp_path):
    with pytest.raises(BankError, match="bank not found"):
        load_bank(tmp_path / "nope")
