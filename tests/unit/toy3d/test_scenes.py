"""E11 S12-20, the non-goal fence: v0's scene library holds the worked scene only (no EP1 scenes);
the model sheet's standing-GuoGuo scene is a test fixture, not a library scene."""
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def test_only_the_worked_scene():
    scenes = sorted(p.name for p in (REPO / "assets" / "toy3d" / "scenes").iterdir())
    assert scenes == ["001-beat2-break-in.yaml"]


def test_the_worked_scene_is_the_snapshots_beat():
    import yaml

    data = yaml.safe_load((REPO / "assets" / "toy3d" / "scenes" / "001-beat2-break-in.yaml").read_text())
    assert data["engine"] == "toy3d" and data["duration"] == 8.0 and len(data["shots"]) == 1
    assert data["shots"][0]["camera"] == "beat2" and len(data["shots"][0]["beats"]) == 37
