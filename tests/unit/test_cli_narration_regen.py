from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pipeline.cli_narration import narration_app
from pipeline.storyboard import NarrationSource, Scene, Storyboard


@pytest.fixture
def project_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    out_root = tmp_path / "output"
    proj = out_root / "projects" / "42"
    proj.mkdir(parents=True)
    sb = Storyboard(
        scenes=[
            Scene(
                id="s1",
                section="content",
                narration="original text",
                narration_est_sec=1.0,
            ),
            Scene(id="s2", section="content", narration="another", narration_est_sec=1.0),
        ]
    )
    sb.save(proj / "storyboard.json")
    (proj / "context.json").write_text(
        json.dumps({"project_id": 42, "source_url": "x", "locale": "zh-TW", "work_dir": str(proj)}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "pipeline.cli_narration.PipelineConfig",
        lambda: type("C", (), {"OUTPUT_DIR": out_root})(),
    )
    return proj


def test_regen_overwrites_narration_text(project_tree: Path):
    runner = CliRunner()
    result = runner.invoke(
        narration_app,
        ["regen", "--project-id", "42", "--scene", "s1", "--text", "rewritten"],
    )
    assert result.exit_code == 0, result.output
    sb = Storyboard.load(project_tree / "storyboard.json")
    assert sb.get_scene("s1").narration == "rewritten"
    assert sb.get_scene("s2").narration == "another"


def test_regen_rejects_unknown_scene(project_tree: Path):
    runner = CliRunner()
    result = runner.invoke(
        narration_app,
        ["regen", "--project-id", "42", "--scene", "s99", "--text", "x"],
    )
    assert result.exit_code != 0
    assert "s99" in result.output


def test_regen_preserves_narration_source(project_tree: Path):
    sb = Storyboard.load(project_tree / "storyboard.json")
    sb.get_scene("s1").narration_source = NarrationSource(
        engine="edge", voice="zh-TW-HsiaoChenNeural"
    )
    sb.save(project_tree / "storyboard.json")

    runner = CliRunner()
    result = runner.invoke(
        narration_app,
        ["regen", "--project-id", "42", "--scene", "s1", "--text", "fresh"],
    )
    assert result.exit_code == 0, result.output
    sb = Storyboard.load(project_tree / "storyboard.json")
    assert sb.get_scene("s1").narration == "fresh"
    assert sb.get_scene("s1").narration_source is not None
    assert sb.get_scene("s1").narration_source.engine == "edge"
