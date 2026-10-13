"""E11 S12-12: the cast model sheet: standing GuoGuo 3/4 (the design view), the two-shot and the
close-up of the worked scene at the snapshot's still time."""
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def test_the_sheet_views_are_the_snapshots_stills():
    from toon.scene import load_scene, read_scene
    from toy3d.bank import load_bank
    from toy3d.sheet import SHEET_T, sheet_views

    bank = load_bank()
    worked = load_scene(read_scene(str(REPO / "assets/toy3d/scenes/001-beat2-break-in.yaml")), bank.catalog)
    design = load_scene(read_scene(str(REPO / "tests/fixtures/toy3d/sheet/guo_design_view.yaml")), bank.catalog)
    views = sheet_views(worked, design)
    assert [(name, t) for name, _, t in views] == [("guo_34", 0.714), ("twoshot", SHEET_T), ("closeup", SHEET_T)]
    assert SHEET_T == 4.6                                                 # scene.js STILL_T
    assert [scene.shots[0].camera for _, scene, _ in views] == ["guo_34", "twoshot", "closeup"]
    assert views[1][1].shots[0].beats == worked.shots[0].beats            # the worked scene's acting
    assert worked.shots[0].camera == "beat2"                              # the worked scene is untouched
