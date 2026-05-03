import json
from pathlib import Path

import pytest

from pipeline.explainer import Manifest, RequiredImage
from pipeline.verifier import (
    ItemStatus,
    VerifierResult,
    load_verifier_state,
    run_auto_checks,
    save_verifier_state,
)


def _fake_storyboard():
    return {
        "scenes": [
            {
                "id": "s1",
                "narration": "Welcome. this exact line must appear in narration.",
                "visual": {
                    "type": "article_image",
                    "path": "raw/parenting/sample/assets/img1.jpg",
                },
                "overlay": None,
            },
            {
                "id": "s2",
                "narration": "Next scene narration with no quote.",
                "visual": {"type": "generated_image", "path": "scenes/s2.png"},
                "overlay": {"text": "and so must this one"},
            },
        ]
    }


def _full_manifest():
    return Manifest(
        intent="video",
        verbatim_lines=[
            "this exact line must appear",
            "and so must this one",
            "missing line",
        ],
        key_facts=["fact A", "fact B"],
        required_images=[
            RequiredImage(path="raw/parenting/sample/assets/img1.jpg"),
            RequiredImage(path="raw/parenting/sample/assets/img-missing.jpg"),
        ],
    )


def test_run_auto_checks_marks_verbatim_line_used_when_in_narration():
    result = run_auto_checks(_full_manifest(), _fake_storyboard())
    line0 = next(i for i in result.items if i.item_id == "verbatim_line:0")
    assert line0.status == "used"


def test_run_auto_checks_marks_verbatim_line_used_when_in_overlay():
    result = run_auto_checks(_full_manifest(), _fake_storyboard())
    line1 = next(i for i in result.items if i.item_id == "verbatim_line:1")
    assert line1.status == "used"


def test_run_auto_checks_marks_verbatim_line_missing_when_nowhere():
    result = run_auto_checks(_full_manifest(), _fake_storyboard())
    line2 = next(i for i in result.items if i.item_id == "verbatim_line:2")
    assert line2.status == "missing"


def test_run_auto_checks_marks_image_used_when_path_in_visual():
    result = run_auto_checks(_full_manifest(), _fake_storyboard())
    img0 = next(i for i in result.items if i.item_id == "required_image:0")
    assert img0.status == "used"


def test_run_auto_checks_marks_image_missing_when_not_referenced():
    result = run_auto_checks(_full_manifest(), _fake_storyboard())
    img1 = next(i for i in result.items if i.item_id == "required_image:1")
    assert img1.status == "missing"


def test_run_auto_checks_marks_key_facts_for_manual_review():
    result = run_auto_checks(_full_manifest(), _fake_storyboard())
    fact0 = next(i for i in result.items if i.item_id == "key_fact:0")
    assert fact0.status == "missing"  # manual until user toggles
    assert fact0.auto_checked is False


def test_run_auto_checks_counts_summary():
    result = run_auto_checks(_full_manifest(), _fake_storyboard())
    assert result.used_count == 3       # 2 lines + 1 image
    assert result.missing_count == 4    # 1 line + 1 image + 2 facts
    assert result.skipped_count == 0


def test_run_auto_checks_applies_persisted_skips(tmp_path: Path):
    manifest = _full_manifest()
    state_path = tmp_path / "verifier_state.json"
    state_path.write_text(json.dumps({
        "skipped": ["verbatim_line:2"],
        "manual_checked": [],
    }))

    state = load_verifier_state(state_path)
    result = run_auto_checks(manifest, _fake_storyboard(), state=state)

    line2 = next(i for i in result.items if i.item_id == "verbatim_line:2")
    assert line2.status == "user_skipped"
    assert result.skipped_count == 1
    assert result.missing_count == 3


def test_run_auto_checks_applies_manual_checked(tmp_path: Path):
    manifest = _full_manifest()
    state_path = tmp_path / "verifier_state.json"
    state_path.write_text(json.dumps({
        "skipped": [],
        "manual_checked": ["key_fact:0"],
    }))

    state = load_verifier_state(state_path)
    result = run_auto_checks(manifest, _fake_storyboard(), state=state)

    fact0 = next(i for i in result.items if i.item_id == "key_fact:0")
    assert fact0.status == "used"


def test_save_and_load_verifier_state_roundtrip(tmp_path: Path):
    state_path = tmp_path / "verifier_state.json"
    save_verifier_state(state_path, skipped={"a", "b"}, manual_checked={"c"})
    loaded = load_verifier_state(state_path)
    assert loaded.skipped == {"a", "b"}
    assert loaded.manual_checked == {"c"}


def test_load_verifier_state_missing_file_returns_empty(tmp_path: Path):
    loaded = load_verifier_state(tmp_path / "does-not-exist.json")
    assert loaded.skipped == set()
    assert loaded.manual_checked == set()
