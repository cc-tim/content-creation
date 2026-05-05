from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pipeline.cli_image import image_app
from pipeline.storyboard import Scene, Storyboard


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
                narration="a",
                narration_est_sec=1.0,
                visual={"type": "ai_image", "prompt": "old prompt", "tier": "draft"},
            ),
            Scene(id="s2", section="content", narration="b", narration_est_sec=1.0),
        ]
    )
    sb.save(proj / "storyboard.json")
    (proj / "context.json").write_text(
        json.dumps({"project_id": 42, "source_url": "x", "locale": "zh-TW", "work_dir": str(proj)}),
        encoding="utf-8",
    )

    (proj / "images").mkdir()
    (proj / "images" / "s1.png").write_bytes(b"fake png")
    (proj / "compose" / "scenes").mkdir(parents=True)
    (proj / "compose" / "scenes" / "s1_final.mp4").write_bytes(b"x")
    (proj / "compose" / "scenes" / "s1_final_no_overlay.mp4").write_bytes(b"y")

    monkeypatch.setattr(
        "pipeline.cli_image.PipelineConfig",
        lambda: type("C", (), {"OUTPUT_DIR": out_root})(),
    )
    return proj


def test_regen_updates_visual_prompt_and_tier(project_tree: Path):
    runner = CliRunner()
    result = runner.invoke(
        image_app,
        [
            "regen",
            "--project-id",
            "42",
            "--scene",
            "s1",
            "--prompt",
            "a man on a rainy street",
            "--tier",
            "production",
        ],
    )
    assert result.exit_code == 0, result.output
    sb = Storyboard.load(project_tree / "storyboard.json")
    visual = sb.get_scene("s1").visual
    assert visual["prompt"] == "a man on a rainy street"
    assert visual["tier"] == "production"
    assert visual["type"] == "ai_image"


def test_regen_deletes_cached_image_and_scene_clips(project_tree: Path):
    runner = CliRunner()
    result = runner.invoke(
        image_app,
        ["regen", "--project-id", "42", "--scene", "s1", "--prompt", "x", "--tier", "draft"],
    )
    assert result.exit_code == 0, result.output
    assert not (project_tree / "images" / "s1.png").exists()
    assert not (project_tree / "compose" / "scenes" / "s1_final.mp4").exists()
    assert not (project_tree / "compose" / "scenes" / "s1_final_no_overlay.mp4").exists()


def test_regen_creates_visual_dict_when_scene_has_none(project_tree: Path):
    runner = CliRunner()
    result = runner.invoke(
        image_app,
        [
            "regen",
            "--project-id",
            "42",
            "--scene",
            "s2",
            "--prompt",
            "fresh prompt",
            "--tier",
            "draft",
        ],
    )
    assert result.exit_code == 0, result.output
    sb = Storyboard.load(project_tree / "storyboard.json")
    assert sb.get_scene("s2").visual["prompt"] == "fresh prompt"
    assert sb.get_scene("s2").visual["tier"] == "draft"


def test_regen_rejects_unknown_tier(project_tree: Path):
    runner = CliRunner()
    result = runner.invoke(
        image_app,
        [
            "regen",
            "--project-id",
            "42",
            "--scene",
            "s1",
            "--prompt",
            "x",
            "--tier",
            "platinum",
        ],
    )
    assert result.exit_code != 0
    assert "platinum" in result.output or "tier" in result.output.lower()


def test_regen_rejects_unknown_scene(project_tree: Path):
    runner = CliRunner()
    result = runner.invoke(
        image_app,
        ["regen", "--project-id", "42", "--scene", "s99", "--prompt", "x", "--tier", "draft"],
    )
    assert result.exit_code != 0
    assert "s99" in result.output


def test_regen_handles_missing_image_cache_gracefully(project_tree: Path):
    (project_tree / "images" / "s1.png").unlink()
    runner = CliRunner()
    result = runner.invoke(
        image_app,
        ["regen", "--project-id", "42", "--scene", "s1", "--prompt", "x", "--tier", "draft"],
    )
    assert result.exit_code == 0, result.output
