from toon.bank import load_bank
from toon.scene import load_scene, read_scene, scenes_root


def test_scene_001_loads_and_is_the_only_scene():
    s = load_scene(read_scene("001-lioness-dishes"), load_bank())
    assert [sh.set for sh in s.shots] == ["office", "office", "kitchen", "kitchen"]
    assert sorted(p.name for p in scenes_root().glob("*.yaml")) == ["001-lioness-dishes.yaml"]
