"""E11 S12-6, S12-20, S12-23 (bank half): the toy3d bank v0, Tim's frozen v7 picks as data."""
import hashlib
import shutil
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[3]
WORKED = REPO / "assets" / "toy3d" / "scenes" / "001-beat2-break-in.yaml"
SHEET = REPO / "tests" / "fixtures" / "toy3d" / "sheet"
SNAPSHOT = "d9c61f63"   # the frozen snapshot's SHA256SUMS (spec §12)


def test_v0_bank_holds_exactly_the_picked_items():
    from toy3d.bank import load_bank

    b = load_bank()
    assert set(b.characters) == {"tim", "lioness", "guoguo"}
    assert {c: set(p) for c, p in b.poses.items()} == {
        "tim": {"typing", "shock", "turned", "pushed"},
        "lioness": {"stand", "listen", "brace", "upright", "turned", "akimbo", "point"},
        "guoguo": {"seated", "startled", "flinch", "look_off", "standing"}}
    assert {c: set(e) for c, e in b.expressions.items()} == {
        "tim": {"neutral", "blink", "shock"}, "lioness": {"stern", "blink"}, "guoguo": {"neutral"}}
    assert set(b.sets) == {"office"}
    assert set(b.sets["office"].spots) == {"desk_seat", "doorway_out", "doorway_in", "shelf_top", "turntable"}
    assert set(b.cameras) == {"beat2", "twoshot", "closeup", "guo_34"}
    assert set(b.props) == {"idea_bulb"}
    assert b.bubble.icons == ("dishes", "bang")
    # S12-20: the only toy3d scene is the worked one
    assert sorted(p.name for p in WORKED.parent.glob("*.yaml")) == ["001-beat2-break-in.yaml"]


def test_every_item_carries_provenance():
    from toy3d.bank import load_bank

    b = load_bank()
    picks = [b.style, *b.characters.values(), *b.sets.values(), *b.cameras.values(), *b.props.values(),
             b.bubble, *b.pose_files.values(), *b.expression_files.values()]
    for item in picks:
        assert item.picked.date == "2026-10-13" and SNAPSHOT in item.picked.source, item


def test_guo_trace_is_the_snapshots():
    from toy3d.bank import default_root

    data = (default_root() / "guo_trace.json").read_bytes()
    assert hashlib.sha256(data).hexdigest().startswith("c15df598")   # the snapshot's entry


@pytest.mark.parametrize("file, old, new, message", [
    ("poses/tim.yaml", "{type: half_sine, channel: hips.py", "{type: half_sin, channel: hips.py",
     r"poses/tim\.yaml: poses\.shock\.accents\.0"),
    ("poses/tim.yaml", "torso.rx: 0.13", "torso.rq: 0.13",
     r"poses/tim\.yaml: poses\.typing\.channels\.torso\.rq: not a tim rig channel"),
    ("poses/lioness.yaml", "channels: {body.rx: 0.1}", "channels: {body.rx: 0.1}\n    sparkle: 1",
     r"poses/lioness\.yaml: poses\.brace\.sparkle: Extra inputs are not permitted"),
    ("poses/guoguo.yaml", "channel: fidle", "channel: fiddle",
     r"poses/guoguo\.yaml: poses\.seated\.accents\.3\.channel: not a guoguo rig channel"),
    ("cameras/beat2.yaml", "ease: inout, to: 25.0", "ease: wobble, to: 25.0", r"cameras/beat2\.yaml: fov\.tweens\.0\.ease"),
    # Phase 2 review M7: a face that draws decals draws one for every expression (no stale face)
    ("expressions/tim.yaml", "  blink: {decal: tim_blink}\n", "  blink: {}\n",
     r"expressions/tim\.yaml: expressions\.blink: no decal \(tim's other expressions draw one\)"),
    # Phase 2 review M10: the engine programs' channels are the rig's
    ("characters/guoguo.yaml", "channels: [look.dy, hop, sq, land, wob, flap, jig, raise, fidle, bob, body.rz]",
     "channels: [look.dy, hop, sq, land, flap, jig, raise, fidle, bob, body.rz]",
     r"characters/guoguo\.yaml: guoguo: GuoGuo's program reads \['wob'\], not channels of the rig"),
])
def test_acting_fields_fail_naming_file_and_path(tmp_path, file, old, new, message):
    from toy3d.bank import BankError, default_root, load_bank

    root = tmp_path / "bank"
    shutil.copytree(default_root(), root)
    p = root / file
    text = p.read_text()
    assert old in text
    p.write_text(text.replace(old, new, 1))
    with pytest.raises(BankError, match=message):
        load_bank(root)


def test_the_walk_drives_only_rig_channels(tmp_path):
    """Phase 2 review M10: the lioness's walk program writes body.rz; a rig without it fails at load."""
    from toy3d.bank import BankError, default_root, load_bank

    root = tmp_path / "bank"
    shutil.copytree(default_root(), root)
    p = root / "characters" / "lioness.yaml"
    p.write_text(p.read_text().replace("channels: [root.ry, hips.py, body.rx, body.rz,", "channels: [root.ry, hips.py, body.rx,", 1))
    with pytest.raises(BankError, match=r"characters/lioness\.yaml: walk: the walk drives \['body\.rz'\], not channels of the rig"):
        load_bank(root)


def _scenes():
    return [yaml.safe_load(WORKED.read_text()), *(yaml.safe_load(p.read_text()) for p in sorted(SHEET.glob("*.yaml")))]


def test_every_accent_is_used():
    # S12-23 exact-acting fence: every pose (with its loops and accents) and every expression in
    # the bank is used by the worked scene or the model sheet. No speculative acting library.
    from toy3d.bank import load_bank

    b = load_bank()
    poses: dict[str, set] = {c: set() for c in b.characters}
    exprs: dict[str, set] = {c: set() for c in b.characters}
    for scene in _scenes():
        for shot in scene["shots"]:
            for who, pl in shot["place"].items():
                poses[scene["cast"][who]].add(pl["pose"])
                exprs[scene["cast"][who]].add(pl.get("expr", "neutral"))
            for beat in shot.get("beats", []):
                if "pose" in beat:
                    char = scene["cast"][beat["pose"]]
                    poses[char] |= {beat["to"]} if "to" in beat else set()
                    exprs[char] |= {beat["expr"]} if "expr" in beat else set()
    assert poses == {c: set(p) for c, p in b.poses.items()}
    assert exprs == {c: set(e) for c, e in b.expressions.items()}


def test_toy3d_catalog_is_the_banks():
    from toon.catalog import TOY3D, SceneCatalog, load_catalog

    c = load_catalog("toy3d")
    assert isinstance(c, SceneCatalog) and c.capabilities is TOY3D
    assert c.pose_class("guoguo", "seated") == "sit" and c.pose_class("tim", "stand") is None
    assert set(c.expressions_of("lioness")) == {"stern", "blink"}
    assert set(c.icons) == {"dishes", "bang"} and c.prop_kind("idea_bulb") == "idea_bulb"


def test_worked_scene_and_design_view_load_against_the_bank():
    from toon.catalog import load_catalog
    from toon.scene import load_scene, read_scene

    catalog = load_catalog("toy3d")
    assert load_scene(read_scene(str(WORKED)), catalog).engine == "toy3d"
    for p in SHEET.glob("*.yaml"):
        assert load_scene(read_scene(str(p)), catalog).engine == "toy3d"
