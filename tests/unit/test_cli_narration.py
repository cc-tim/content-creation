from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pipeline.cli_narration import narration_app
from pipeline.storyboard import Scene, Storyboard


def _write_minimal_storyboard(work_dir: Path) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)
    sb = Storyboard(scenes=[
        Scene(id="s1", section="content", narration="a", narration_est_sec=1.0),
        Scene(id="s2", section="content", narration="b", narration_est_sec=1.0),
    ])
    sb_path = work_dir / "storyboard.json"
    sb.save(sb_path)
    (work_dir / "context.json").write_text(
        json.dumps({"project_id": 42, "source_url": "x", "locale": "zh-TW",
                    "work_dir": str(work_dir)}),
        encoding="utf-8",
    )
    return sb_path


@pytest.fixture
def project_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    out_root = tmp_path / "output"
    proj = out_root / "projects" / "42"
    _write_minimal_storyboard(proj)
    monkeypatch.setattr(
        "pipeline.cli_narration.PipelineConfig",
        lambda: type("C", (), {"OUTPUT_DIR": out_root})(),
    )
    return proj


def test_set_source_edge_with_voice(project_tree: Path):
    runner = CliRunner()
    result = runner.invoke(narration_app, [
        "set-source",
        "--project-id", "42",
        "--scene", "s1",
        "--engine", "edge",
        "--voice", "zh-tw-default-f",
    ])
    assert result.exit_code == 0, result.output
    sb = Storyboard.load(project_tree / "storyboard.json")
    s1 = sb.get_scene("s1")
    assert s1 is not None
    assert s1.narration_source is not None
    assert s1.narration_source.engine == "edge"
    assert s1.narration_source.voice == "zh-tw-default-f"
    assert s1.narration_source.file is None


def test_set_source_prerecorded_with_file(project_tree: Path):
    # Place a recording inside the project tree so the path resolves.
    overrides = project_tree / "narration_overrides"
    overrides.mkdir(parents=True)
    (overrides / "s1.wav").write_bytes(b"RIFF....WAVEfmt ")  # placeholder
    runner = CliRunner()
    result = runner.invoke(narration_app, [
        "set-source",
        "--project-id", "42",
        "--scene", "s1",
        "--engine", "prerecorded",
        "--file", "narration_overrides/s1.wav",
    ])
    assert result.exit_code == 0, result.output
    sb = Storyboard.load(project_tree / "storyboard.json")
    s1 = sb.get_scene("s1")
    assert s1 is not None
    assert s1.narration_source is not None
    assert s1.narration_source.engine == "prerecorded"
    assert s1.narration_source.file == "narration_overrides/s1.wav"


def test_set_source_replaces_existing(project_tree: Path):
    runner = CliRunner()
    runner.invoke(narration_app, [
        "set-source", "--project-id", "42", "--scene", "s1",
        "--engine", "edge", "--voice", "zh-tw-default-f",
    ])
    runner.invoke(narration_app, [
        "set-source", "--project-id", "42", "--scene", "s1",
        "--engine", "fish_audio", "--voice", "fish-jingjing",
    ])
    sb = Storyboard.load(project_tree / "storyboard.json")
    s1 = sb.get_scene("s1")
    assert s1 is not None
    assert s1.narration_source is not None
    assert s1.narration_source.engine == "fish_audio"
    assert s1.narration_source.voice == "fish-jingjing"


def test_set_source_rejects_unknown_engine(project_tree: Path):
    runner = CliRunner()
    result = runner.invoke(narration_app, [
        "set-source", "--project-id", "42", "--scene", "s1",
        "--engine", "elevenlabs", "--voice", "any",
    ])
    assert result.exit_code != 0
    assert "Unknown narration engine" in result.output or "elevenlabs" in result.output


def test_set_source_rejects_unknown_scene(project_tree: Path):
    runner = CliRunner()
    result = runner.invoke(narration_app, [
        "set-source", "--project-id", "42", "--scene", "s99",
        "--engine", "edge", "--voice", "zh-tw-default-f",
    ])
    assert result.exit_code != 0
    assert "s99" in result.output


def test_set_source_tts_engine_requires_voice(project_tree: Path):
    runner = CliRunner()
    result = runner.invoke(narration_app, [
        "set-source", "--project-id", "42", "--scene", "s1",
        "--engine", "edge",  # no --voice
    ])
    assert result.exit_code != 0
    assert "voice" in result.output.lower()


def test_set_source_prerecorded_requires_file(project_tree: Path):
    runner = CliRunner()
    result = runner.invoke(narration_app, [
        "set-source", "--project-id", "42", "--scene", "s1",
        "--engine", "prerecorded",  # no --file
    ])
    assert result.exit_code != 0
    assert "file" in result.output.lower()


def test_set_source_rejects_file_outside_project_tree(project_tree: Path):
    """Sandbox check: a --file path that escapes the project root is rejected."""
    runner = CliRunner()
    result = runner.invoke(narration_app, [
        "set-source", "--project-id", "42", "--scene", "s1",
        "--engine", "prerecorded", "--file", "../../etc/passwd",
    ])
    assert result.exit_code != 0
    assert "outside" in result.output.lower() or "project tree" in result.output.lower()


def test_set_source_rejects_missing_file(project_tree: Path):
    """The referenced file must exist under the project tree."""
    runner = CliRunner()
    result = runner.invoke(narration_app, [
        "set-source", "--project-id", "42", "--scene", "s1",
        "--engine", "prerecorded", "--file", "narration_overrides/s1.wav",
    ])
    assert result.exit_code != 0
    assert "not found" in result.output.lower() or "does not exist" in result.output.lower()


def test_set_source_appends_session_entry(project_tree: Path):
    runner = CliRunner()
    runner.invoke(narration_app, [
        "set-source", "--project-id", "42", "--scene", "s1",
        "--engine", "edge", "--voice", "zh-tw-default-f",
    ])
    sessions = json.loads((project_tree / "sessions.json").read_text())
    assert any("narration set-source" in e["command"] for e in sessions)
    assert any("s1" in e.get("summary", "") for e in sessions)
