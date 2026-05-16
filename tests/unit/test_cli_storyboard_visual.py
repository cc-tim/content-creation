from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from pipeline.cli import app

runner = CliRunner()

_MINIMAL_SB = {
    "scenes": [{
        "id": "s5",
        "section": "hook",
        "narration": "test narration",
        "narration_est_sec": 5,
        "pause_after_sec": 0,
        "visual": {"type": "generated_image", "prompt": "parent and child"},
    }],
    "theme": {},
}


def _write_sb(tmp_path: Path) -> Path:
    p = tmp_path / "storyboard.json"
    p.write_text(json.dumps(_MINIMAL_SB))
    return p


def test_set_style_modifier(tmp_path):
    _write_sb(tmp_path)
    result = runner.invoke(app, [
        "storyboard", "set", "s5", "visual.style_modifier=darker, tense",
        "--work-dir", str(tmp_path),
    ])
    assert result.exit_code == 0, result.output
    sb = json.loads((tmp_path / "storyboard.json").read_text())
    assert sb["scenes"][0]["visual"]["style_modifier"] == "darker, tense"


def test_set_edit_mode_true(tmp_path):
    _write_sb(tmp_path)
    result = runner.invoke(app, [
        "storyboard", "set", "s5", "visual.edit_mode=true",
        "--work-dir", str(tmp_path),
    ])
    assert result.exit_code == 0, result.output
    sb = json.loads((tmp_path / "storyboard.json").read_text())
    assert sb["scenes"][0]["visual"]["edit_mode"] is True


def test_set_edit_mode_false(tmp_path):
    _write_sb(tmp_path)
    result = runner.invoke(app, [
        "storyboard", "set", "s5", "visual.edit_mode=false",
        "--work-dir", str(tmp_path),
    ])
    assert result.exit_code == 0
    sb = json.loads((tmp_path / "storyboard.json").read_text())
    assert sb["scenes"][0]["visual"]["edit_mode"] is False


def test_set_edit_strength_coerced_to_float(tmp_path):
    _write_sb(tmp_path)
    result = runner.invoke(app, [
        "storyboard", "set", "s5", "visual.edit_strength=0.25",
        "--work-dir", str(tmp_path),
    ])
    assert result.exit_code == 0
    sb = json.loads((tmp_path / "storyboard.json").read_text())
    assert sb["scenes"][0]["visual"]["edit_strength"] == 0.25


def test_set_edit_type_validated(tmp_path):
    _write_sb(tmp_path)
    result = runner.invoke(app, [
        "storyboard", "set", "s5", "visual.edit_type=bad_value",
        "--work-dir", str(tmp_path),
    ])
    assert result.exit_code != 0


def test_set_unknown_visual_field_rejected(tmp_path):
    _write_sb(tmp_path)
    result = runner.invoke(app, [
        "storyboard", "set", "s5", "visual.unknown_field=value",
        "--work-dir", str(tmp_path),
    ])
    assert result.exit_code != 0


def test_existing_fields_still_work(tmp_path):
    _write_sb(tmp_path)
    result = runner.invoke(app, [
        "storyboard", "set", "s5", "narration=new text",
        "--work-dir", str(tmp_path),
    ])
    assert result.exit_code == 0
    sb = json.loads((tmp_path / "storyboard.json").read_text())
    assert sb["scenes"][0]["narration"] == "new text"


def test_set_reports_validation_error_after_edit(tmp_path):
    _write_sb(tmp_path)
    sb_path = tmp_path / "storyboard.json"
    sb = json.loads(sb_path.read_text())
    sb["scenes"][0]["visual"] = {"type": "unknown_visual_type"}
    sb_path.write_text(json.dumps(sb), encoding="utf-8")

    result = runner.invoke(app, [
        "storyboard", "set", "s5", "narration=new text",
        "--work-dir", str(tmp_path),
    ])

    assert result.exit_code != 0
    assert "Storyboard visual validation failed" in result.output


def test_set_refit_path(tmp_path):
    _write_sb(tmp_path)
    result = runner.invoke(app, [
        "storyboard", "set", "s5", "visual.refit_path=output/projects/p/edits/s5_crop.png",
        "--work-dir", str(tmp_path),
    ])
    assert result.exit_code == 0, result.output
    sb = json.loads((tmp_path / "storyboard.json").read_text())
    assert sb["scenes"][0]["visual"]["refit_path"] == "output/projects/p/edits/s5_crop.png"


def test_clear_refit_path_with_null(tmp_path):
    _write_sb(tmp_path)
    sb_path = tmp_path / "storyboard.json"
    sb = json.loads(sb_path.read_text())
    sb["scenes"][0]["visual"]["refit_path"] = "output/projects/p/edits/s5_crop.png"
    sb_path.write_text(json.dumps(sb), encoding="utf-8")

    result = runner.invoke(app, [
        "storyboard", "set", "s5", "visual.refit_path=null",
        "--work-dir", str(tmp_path),
    ])
    assert result.exit_code == 0, result.output
    sb = json.loads(sb_path.read_text())
    assert "refit_path" not in sb["scenes"][0]["visual"]
