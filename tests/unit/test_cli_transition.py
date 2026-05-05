from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pipeline.cli_transition import transition_app
from pipeline.storyboard import Scene, Storyboard


def _write_minimal_storyboard(work_dir: Path) -> Path:
    """Create a project tree with a 2-scene storyboard for the CLI to mutate."""
    work_dir.mkdir(parents=True, exist_ok=True)
    sb = Storyboard(scenes=[
        Scene(id="s1", section="content", narration="a", narration_est_sec=1.0),
        Scene(id="s2", section="content", narration="b", narration_est_sec=1.0),
    ])
    sb_path = work_dir / "storyboard.json"
    sb.save(sb_path)
    # Minimal context.json (required by some commands; not strictly needed by transition)
    (work_dir / "context.json").write_text(
        json.dumps({"project_id": 42, "source_url": "x", "locale": "zh-TW",
                    "work_dir": str(work_dir)}),
        encoding="utf-8",
    )
    return sb_path


@pytest.fixture
def project_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Set up a fake projects directory and return the project's work dir."""
    out_root = tmp_path / "output"
    proj = out_root / "projects" / "42"
    _write_minimal_storyboard(proj)
    monkeypatch.setattr(
        "pipeline.cli_transition.PipelineConfig",
        lambda: type("C", (), {"OUTPUT_DIR": out_root})(),
    )
    return proj


def test_set_writes_transition_to_storyboard(project_tree: Path):
    runner = CliRunner()
    result = runner.invoke(transition_app, [
        "set",
        "--project-id", "42",
        "--from", "s1",
        "--to", "s2",
        "--style", "page-turn",
        "--duration", "0.5",
    ])
    assert result.exit_code == 0, result.output
    sb = Storyboard.load(project_tree / "storyboard.json")
    assert len(sb.transitions) == 1
    assert sb.transitions[0].from_scene == "s1"
    assert sb.transitions[0].to_scene == "s2"
    assert sb.transitions[0].style == "page-turn"
    assert sb.transitions[0].duration_sec == 0.5
    assert sb.transitions[0].sfx is None


def test_set_with_sfx_writes_sfx(project_tree: Path):
    runner = CliRunner()
    result = runner.invoke(transition_app, [
        "set", "--project-id", "42", "--from", "s1", "--to", "s2",
        "--style", "fade", "--duration", "0.3",
        "--sfx", "assets/sfx/page_flip.mp3",
    ])
    assert result.exit_code == 0, result.output
    sb = Storyboard.load(project_tree / "storyboard.json")
    assert sb.transitions[0].sfx == "assets/sfx/page_flip.mp3"


def test_set_updates_existing_transition_for_same_seam(project_tree: Path):
    runner = CliRunner()
    runner.invoke(transition_app, [
        "set", "--project-id", "42", "--from", "s1", "--to", "s2",
        "--style", "fade", "--duration", "0.3",
    ])
    runner.invoke(transition_app, [
        "set", "--project-id", "42", "--from", "s1", "--to", "s2",
        "--style", "page-turn", "--duration", "0.6",
    ])
    sb = Storyboard.load(project_tree / "storyboard.json")
    assert len(sb.transitions) == 1, "second set should replace, not append"
    assert sb.transitions[0].style == "page-turn"
    assert sb.transitions[0].duration_sec == 0.6


def test_set_rejects_unknown_style(project_tree: Path):
    runner = CliRunner()
    result = runner.invoke(transition_app, [
        "set", "--project-id", "42", "--from", "s1", "--to", "s2",
        "--style", "ribbon", "--duration", "0.5",
    ])
    assert result.exit_code != 0
    assert "Unknown transition style" in result.output or "ribbon" in result.output


def test_set_rejects_unknown_scene(project_tree: Path):
    runner = CliRunner()
    result = runner.invoke(transition_app, [
        "set", "--project-id", "42", "--from", "s1", "--to", "s99",
        "--style", "fade", "--duration", "0.5",
    ])
    assert result.exit_code != 0
    assert "s99" in result.output


def test_clear_removes_transition(project_tree: Path):
    runner = CliRunner()
    runner.invoke(transition_app, [
        "set", "--project-id", "42", "--from", "s1", "--to", "s2",
        "--style", "fade", "--duration", "0.3",
    ])
    result = runner.invoke(transition_app, [
        "clear", "--project-id", "42", "--from", "s1", "--to", "s2",
    ])
    assert result.exit_code == 0, result.output
    sb = Storyboard.load(project_tree / "storyboard.json")
    assert sb.transitions == []


def test_clear_is_noop_when_no_transition_exists(project_tree: Path):
    runner = CliRunner()
    result = runner.invoke(transition_app, [
        "clear", "--project-id", "42", "--from", "s1", "--to", "s2",
    ])
    assert result.exit_code == 0
    assert "no transition" in result.output.lower() or "nothing to clear" in result.output.lower()


def test_apply_set_transition_writes_to_storyboard(project_tree: Path):
    from pipeline.cli_transition import apply_set_transition

    summary = apply_set_transition(
        project_id=42, from_scene="s1", to_scene="s2",
        style="fade", duration_sec=0.3, sfx=None,
    )
    sb = Storyboard.load(project_tree / "storyboard.json")
    assert len(sb.transitions) == 1
    assert sb.transitions[0].style == "fade"
    assert "s1" in summary and "s2" in summary


def test_apply_set_transition_rejects_unknown_style(project_tree: Path):
    from pipeline.cli_transition import apply_set_transition

    with pytest.raises(ValueError, match="Unknown transition style"):
        apply_set_transition(
            project_id=42, from_scene="s1", to_scene="s2",
            style="ribbon", duration_sec=0.3, sfx=None,
        )


def test_apply_set_transition_rejects_unknown_scene(project_tree: Path):
    from pipeline.cli_transition import apply_set_transition

    with pytest.raises(ValueError, match="s99"):
        apply_set_transition(
            project_id=42, from_scene="s1", to_scene="s99",
            style="fade", duration_sec=0.3, sfx=None,
        )


def test_apply_clear_transition_removes_entry(project_tree: Path):
    from pipeline.cli_transition import apply_clear_transition, apply_set_transition

    apply_set_transition(
        project_id=42, from_scene="s1", to_scene="s2",
        style="fade", duration_sec=0.3, sfx=None,
    )
    summary = apply_clear_transition(project_id=42, from_scene="s1", to_scene="s2")
    sb = Storyboard.load(project_tree / "storyboard.json")
    assert sb.transitions == []
    assert "cleared" in summary.lower() or "s1" in summary


def test_apply_clear_transition_returns_noop_summary_when_absent(project_tree: Path):
    from pipeline.cli_transition import apply_clear_transition

    summary = apply_clear_transition(project_id=42, from_scene="s1", to_scene="s2")
    assert "no transition" in summary.lower() or "nothing" in summary.lower()
