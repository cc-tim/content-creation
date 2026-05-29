from pipeline.director.still_gate.model import Finding


def test_finding_is_frozen_and_has_fields():
    f = Finding(
        scene_id="s5",
        check="duplicate_frame",
        severity="error",
        message="s5 frame is identical to s4",
        suggested_fix="give s5 a distinct image or camera_motion",
    )
    assert f.scene_id == "s5"
    assert f.check == "duplicate_frame"
    assert f.severity == "error"
    import dataclasses
    with __import__("pytest").raises(dataclasses.FrozenInstanceError):
        f.scene_id = "s6"  # type: ignore[misc]
