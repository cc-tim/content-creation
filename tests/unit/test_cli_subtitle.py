from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pipeline.cli_subtitle import subtitle_app
from pipeline.storyboard import Scene, Storyboard


def _write_minimal_storyboard(work_dir: Path) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)
    sb = Storyboard(
        scenes=[
            Scene(id="s1", section="content", narration="a", narration_est_sec=1.0),
            Scene(id="s2", section="content", narration="b", narration_est_sec=1.0),
        ]
    )
    sb_path = work_dir / "storyboard.json"
    sb.save(sb_path)
    (work_dir / "context.json").write_text(
        json.dumps(
            {"project_id": 42, "source_url": "x", "locale": "zh-TW", "work_dir": str(work_dir)}
        ),
        encoding="utf-8",
    )
    return sb_path


@pytest.fixture
def project_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    out_root = tmp_path / "output"
    proj = out_root / "projects" / "42"
    _write_minimal_storyboard(proj)
    monkeypatch.setattr(
        "pipeline.cli_subtitle.PipelineConfig",
        lambda: type("C", (), {"OUTPUT_DIR": out_root})(),
    )
    return proj


def test_set_writes_subtitle_override(project_tree: Path):
    runner = CliRunner()
    result = runner.invoke(
        subtitle_app,
        ["set", "--project-id", "42", "--scene", "s1", "--text", "hello world"],
    )
    assert result.exit_code == 0, result.output
    sb = Storyboard.load(project_tree / "storyboard.json")
    assert sb.get_scene("s1").subtitle_override == "hello world"
    assert sb.get_scene("s2").subtitle_override is None


def test_set_replaces_existing_override(project_tree: Path):
    runner = CliRunner()
    runner.invoke(subtitle_app, ["set", "--project-id", "42", "--scene", "s1", "--text", "v1"])
    runner.invoke(subtitle_app, ["set", "--project-id", "42", "--scene", "s1", "--text", "v2"])
    sb = Storyboard.load(project_tree / "storyboard.json")
    assert sb.get_scene("s1").subtitle_override == "v2"


def test_set_rejects_unknown_scene(project_tree: Path):
    runner = CliRunner()
    result = runner.invoke(
        subtitle_app,
        ["set", "--project-id", "42", "--scene", "s99", "--text", "x"],
    )
    assert result.exit_code != 0
    assert "s99" in result.output


def test_set_rejects_missing_storyboard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "pipeline.cli_subtitle.PipelineConfig",
        lambda: type("C", (), {"OUTPUT_DIR": tmp_path / "output"})(),
    )
    runner = CliRunner()
    result = runner.invoke(
        subtitle_app,
        ["set", "--project-id", "999", "--scene", "s1", "--text", "x"],
    )
    assert result.exit_code != 0
    assert "storyboard" in result.output.lower()
