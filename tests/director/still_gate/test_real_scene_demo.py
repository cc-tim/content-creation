import json
from pathlib import Path

import pytest

from pipeline.director.still_gate import render_scene_still, run_checks

SNAPSHOT = Path("tmp/storyboard.BEFORE-quality-pass.json")


@pytest.mark.skipif(not SNAPSHOT.exists(), reason="defect-state snapshot not present")
def test_blank_map_and_dup_fire_on_baby_walker_defect_snapshot(tmp_path):
    scenes = json.loads(SNAPSHOT.read_text())["scenes"]
    targets = [s for s in scenes if s.get("id") in {"s24", "s25", "s26"}]
    if not targets:
        pytest.skip("snapshot does not contain s24-26")
    for s in targets:
        p = s.get("visual", {}).get("path")
        if p and not Path(p).exists():
            pytest.skip(f"asset not on this machine: {p}")
    stills = []
    for s in targets:
        png = render_scene_still(s, variant="no_overlay", work_dir=tmp_path / s["id"], theme={})
        stills.append((s["id"], png, s))
    findings = run_checks(stills)
    checks = {f.check for f in findings}
    assert "blank_substrate" in checks
    assert "duplicate_frame" in checks
