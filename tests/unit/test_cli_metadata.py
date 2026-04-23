from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pipeline.cli_metadata import metadata_app

FIXTURE = Path(__file__).parents[1] / "fixtures" / "sample_metadata.json"


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    d = tmp_path / "project"
    d.mkdir()
    shutil.copy(FIXTURE, d / "metadata.json")
    return d


def test_show_prints_fields(project_dir: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(metadata_app, ["show", "--work-dir", str(project_dir)])
    assert result.exit_code == 0, result.output
    assert "Sample Title" in result.output
    assert "sample" in result.output.lower()


def test_show_errors_when_missing(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(metadata_app, ["show", "--work-dir", str(tmp_path)])
    assert result.exit_code != 0


def test_set_title(project_dir: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        metadata_app,
        ["set", "title=Updated Title", "--work-dir", str(project_dir)],
    )
    assert result.exit_code == 0, result.output
    raw = json.loads((project_dir / "metadata.json").read_text())
    assert raw["title"] == "Updated Title"


def test_set_tags_json_list(project_dir: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        metadata_app,
        ["set", 'tags=["x","y","z"]', "--work-dir", str(project_dir)],
    )
    assert result.exit_code == 0, result.output
    raw = json.loads((project_dir / "metadata.json").read_text())
    assert raw["tags"] == ["x", "y", "z"]


def test_set_rejects_unsafe_field(project_dir: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        metadata_app,
        ["set", "_generated_at=bad", "--work-dir", str(project_dir)],
    )
    assert result.exit_code != 0
    assert "not a safe field" in result.output.lower()


def test_validate_passes(project_dir: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(metadata_app, ["validate", "--work-dir", str(project_dir)])
    assert result.exit_code == 0, result.output
    assert "ok" in result.output.lower()


def test_validate_fails_on_too_long_title(project_dir: Path) -> None:
    raw = json.loads((project_dir / "metadata.json").read_text())
    raw["title"] = "x" * 150
    (project_dir / "metadata.json").write_text(json.dumps(raw))
    runner = CliRunner()
    result = runner.invoke(metadata_app, ["validate", "--work-dir", str(project_dir)])
    assert result.exit_code != 0
