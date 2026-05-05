from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pipeline.cli_overlay import overlay_app
from pipeline.storyboard import Scene, Storyboard


@pytest.fixture
def project_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    out_root = tmp_path / "output"
    proj = out_root / "projects" / "42"
    proj.mkdir(parents=True)
    sb = Storyboard(
        scenes=[
            Scene(id="s1", section="content", narration="a", narration_est_sec=1.0),
            Scene(
                id="s2",
                section="content",
                narration="b",
                narration_est_sec=1.0,
                overlay={"text": "old", "position": "lower-third", "style": "bold"},
            ),
        ]
    )
    sb.save(proj / "storyboard.json")
    (proj / "context.json").write_text(
        json.dumps({"project_id": 42, "source_url": "x", "locale": "zh-TW", "work_dir": str(proj)}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "pipeline.cli_overlay.PipelineConfig",
        lambda: type("C", (), {"OUTPUT_DIR": out_root})(),
    )
    return proj


def test_set_creates_overlay_when_absent(project_tree: Path):
    runner = CliRunner()
    result = runner.invoke(
        overlay_app,
        ["set", "--project-id", "42", "--scene", "s1", "--text", "hello"],
    )
    assert result.exit_code == 0, result.output
    sb = Storyboard.load(project_tree / "storyboard.json")
    assert sb.get_scene("s1").overlay == {"text": "hello"}


def test_set_preserves_existing_overlay_keys(project_tree: Path):
    runner = CliRunner()
    result = runner.invoke(
        overlay_app,
        ["set", "--project-id", "42", "--scene", "s2", "--text", "new text"],
    )
    assert result.exit_code == 0, result.output
    sb = Storyboard.load(project_tree / "storyboard.json")
    overlay = sb.get_scene("s2").overlay
    assert overlay == {"text": "new text", "position": "lower-third", "style": "bold"}


def test_set_rejects_unknown_scene(project_tree: Path):
    runner = CliRunner()
    result = runner.invoke(
        overlay_app,
        ["set", "--project-id", "42", "--scene", "s99", "--text", "x"],
    )
    assert result.exit_code != 0
    assert "s99" in result.output
