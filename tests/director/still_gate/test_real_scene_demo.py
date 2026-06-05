import json
from pathlib import Path

import pytest

from pipeline.director.still_gate import render_scene_still, resolve_variant, run_checks

SNAPSHOT = Path("tmp/storyboard.BEFORE-quality-pass.json")


@pytest.mark.skipif(not SNAPSHOT.exists(), reason="defect-state snapshot not present")
def test_reused_blank_map_is_caught_on_baby_walker_defect_snapshot(tmp_path):
    """Proving test on the real baby-walker defect snapshot.

    s24/s25/s26 reuse the identical `north_america_blank_map.png`, whose meaning
    lived in overlays the `no_overlay` deliverable strips. The deterministically
    catchable, operative defect is the REUSE, so `duplicate_frame` must fire.

    KNOWN GAP (flagged to the EM REVIEW): `blank_substrate` does NOT fire on this
    map. The map is bordered/varied (~62% dominant color), and dominant-color
    measured on the whole book-framed still is diluted further — so check 2 only
    catches genuinely-flat frames, not "informationally empty but visually varied"
    maps. Catching that needs a content-inset / edge-entropy redesign of check 2.
    The bare-frame-meaninglessness here is still surfaced via the duplicate catch.
    """
    scenes = json.loads(SNAPSHOT.read_text())["scenes"]
    targets = [s for s in scenes if s.get("id") in {"s24", "s25", "s26"}]
    if len(targets) < 2:
        pytest.skip("snapshot does not contain the reused-map scenes s24-26")
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
    assert "duplicate_frame" in checks  # the reused map IS caught


@pytest.mark.skipif(not SNAPSHOT.exists(), reason="defect-state snapshot not present")
def test_wired_default_variant_catches_dup_on_snapshot(tmp_path):
    """Regression for the EM REWORK finding (2026-05-30): the gate must catch the
    reused map at its REAL invocation, where context.json has no preferred_variant
    yet (it's written post-TTS). The wired default must resolve to a NON-burning
    variant so the reuse isn't masked by distinct burned overlays.
    """
    # No context.json in this project dir -> the path the live gate hits pre-TTS.
    variant = resolve_variant(tmp_path)
    assert variant == "no_overlay"  # NOT 'plain'

    scenes = json.loads(SNAPSHOT.read_text())["scenes"]
    targets = [s for s in scenes if s.get("id") in {"s24", "s25", "s26"}]
    if len(targets) < 2:
        pytest.skip("snapshot does not contain the reused-map scenes s24-26")
    for s in targets:
        p = s.get("visual", {}).get("path")
        if p and not Path(p).exists():
            pytest.skip(f"asset not on this machine: {p}")
    stills = []
    for s in targets:
        png = render_scene_still(s, variant=variant, work_dir=tmp_path / "r" / s["id"], theme={})
        stills.append((s["id"], png, s))
    checks = {f.check for f in run_checks(stills)}
    assert "duplicate_frame" in checks  # caught via the wired default, not a forced variant
