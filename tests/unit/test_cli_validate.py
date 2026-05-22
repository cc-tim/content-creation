from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pipeline.cli_validate import validate_app


@pytest.fixture
def project_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a project dir under a temp OUTPUT_DIR and switch OUTPUT_DIR there."""
    output = tmp_path / "output"
    project_id = "20990101-000000-test-project"
    pdir = output / "projects" / project_id
    pdir.mkdir(parents=True)
    # cli_validate reads OUTPUT_DIR via PipelineConfig() at call time
    # PipelineConfig uses env_prefix="PIPELINE_", so the env var is PIPELINE_OUTPUT_DIR
    monkeypatch.setenv("PIPELINE_OUTPUT_DIR", str(output))
    return pdir


def _write_storyboard(pdir: Path, scenes: list[dict], filename: str = "storyboard.json") -> Path:
    payload = {"scenes": scenes, "theme": {}}
    sb = pdir / filename
    sb.write_text(json.dumps(payload), encoding="utf-8")
    return sb


def test_validate_clean_storyboard_exits_zero(project_dir: Path) -> None:
    _write_storyboard(project_dir, [
        {
            "id": "s1",
            "section": "hook",
            "narration": "ok",
            "narration_est_sec": 5,
            "visual": {"type": "text_card", "text": "hi"},
        },
    ])
    runner = CliRunner()
    result = runner.invoke(validate_app, ["--project-id", project_dir.name])
    assert result.exit_code == 0, result.output


def test_validate_broken_chart_exits_two(project_dir: Path) -> None:
    _write_storyboard(project_dir, [
        {
            "id": "s1",
            "section": "hook",
            "narration": "ok",
            "narration_est_sec": 5,
            "visual": {"type": "chart"},  # missing chart_type
        },
    ])
    runner = CliRunner()
    result = runner.invoke(validate_app, ["--project-id", project_dir.name])
    assert result.exit_code == 2, result.output
    assert "chart_type" in result.output


def test_validate_missing_project_exits_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = tmp_path / "output"
    output.mkdir()
    monkeypatch.setenv("PIPELINE_OUTPUT_DIR", str(output))
    runner = CliRunner()
    result = runner.invoke(validate_app, ["--project-id", "does-not-exist"])
    assert result.exit_code == 1, result.output


def test_validate_no_storyboard_exits_one(project_dir: Path) -> None:
    # project_dir exists, but no storyboard*.json
    runner = CliRunner()
    result = runner.invoke(validate_app, ["--project-id", project_dir.name])
    assert result.exit_code == 1, result.output
    assert "storyboard" in result.output.lower()


def test_validate_multiple_storyboards_requires_locale(project_dir: Path) -> None:
    _write_storyboard(project_dir, [
        {
            "id": "s1",
            "section": "hook",
            "narration": "ok",
            "narration_est_sec": 5,
            "visual": {"type": "text_card", "text": "hi"},
        },
    ], filename="storyboard_zh-TW.json")
    _write_storyboard(project_dir, [
        {
            "id": "s1",
            "section": "hook",
            "narration": "ok",
            "narration_est_sec": 5,
            "visual": {"type": "text_card", "text": "hi"},
        },
    ], filename="storyboard_ja.json")
    runner = CliRunner()
    result = runner.invoke(validate_app, ["--project-id", project_dir.name])
    assert result.exit_code == 1, result.output
    assert "--locale" in result.output


def test_validate_locale_override_picks_correct_file(project_dir: Path) -> None:
    _write_storyboard(project_dir, [
        {
            "id": "s1",
            "section": "hook",
            "narration": "ok",
            "narration_est_sec": 5,
            "visual": {"type": "text_card", "text": "hi"},
        },
    ], filename="storyboard_zh-TW.json")
    _write_storyboard(project_dir, [
        {
            "id": "s1",
            "section": "hook",
            "narration": "broken",
            "narration_est_sec": 5,
            "visual": {"type": "chart"},  # missing chart_type
        },
    ], filename="storyboard_ja.json")
    runner = CliRunner()
    # zh-TW is clean → exit 0
    result_zh = runner.invoke(
        validate_app, ["--project-id", project_dir.name, "--locale", "zh-TW"]
    )
    assert result_zh.exit_code == 0, result_zh.output
    # ja is broken → exit 2
    result_ja = runner.invoke(
        validate_app, ["--project-id", project_dir.name, "--locale", "ja"]
    )
    assert result_ja.exit_code == 2, result_ja.output


def test_validate_prefers_unsuffixed_storyboard_when_both_exist(project_dir: Path) -> None:
    """If both `storyboard.json` and `storyboard_<locale>.json` exist (mixed-vintage
    project), pick `storyboard.json` first — it's the canonical name used by compose."""
    _write_storyboard(project_dir, [
        {
            "id": "s1",
            "section": "hook",
            "narration": "canonical",
            "narration_est_sec": 5,
            "visual": {"type": "text_card", "text": "hi"},
        },
    ], filename="storyboard.json")
    _write_storyboard(project_dir, [
        {
            "id": "s1",
            "section": "hook",
            "narration": "broken locale",
            "narration_est_sec": 5,
            "visual": {"type": "chart"},  # would fail
        },
    ], filename="storyboard_ja.json")
    runner = CliRunner()
    result = runner.invoke(validate_app, ["--project-id", project_dir.name])
    # storyboard.json is clean → exit 0 (proves we picked it, not the broken locale)
    assert result.exit_code == 0, result.output
