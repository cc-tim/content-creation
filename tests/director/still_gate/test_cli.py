import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from pipeline.cli_storyboard import storyboard_app

runner = CliRunner()


def _project(tmp_path: Path, scenes: list[dict], variant: str = "no_overlay") -> str:
    pid = "testproj"
    pdir = tmp_path / "projects" / pid
    pdir.mkdir(parents=True)
    (pdir / "context.json").write_text(json.dumps({"preferred_variant": variant}))
    (pdir / "storyboard.json").write_text(
        json.dumps({"scenes": scenes, "transitions": []}, ensure_ascii=False)
    )
    return pid


def test_still_gate_exits_2_on_blank_and_dup(tmp_path, busy_png, flat_grey_png, monkeypatch):
    monkeypatch.setenv("PIPELINE_OUTPUT_DIR", str(tmp_path))
    scenes = [
        {"id": "s1", "section": "h", "visual": {"type": "article_image", "path": str(flat_grey_png)}, "overlay": None},
        {"id": "s2", "section": "h", "visual": {"type": "article_image", "path": str(flat_grey_png)}, "overlay": None},
    ]
    pid = _project(tmp_path, scenes)

    # render_scene_still wraps images in a frame — short-circuit it to return the
    # raw flat grey so blank_substrate and duplicate_frame fire on the CLI path too.
    def _fake_render(scene, *, variant, work_dir, theme):
        work_dir.mkdir(parents=True, exist_ok=True)
        sid = scene.get("id", "scene")
        dst = work_dir / f"{sid}.png"
        import shutil
        shutil.copy(flat_grey_png, dst)
        return dst

    with patch("pipeline.director.still_gate.render_scene_still", _fake_render):
        result = runner.invoke(storyboard_app, ["still-gate", pid])
    assert result.exit_code == 2
    assert "blank_substrate" in result.stdout
    assert "duplicate_frame" in result.stdout


def test_still_gate_exits_0_when_clean(tmp_path, busy_png, monkeypatch):
    monkeypatch.setenv("PIPELINE_OUTPUT_DIR", str(tmp_path))
    scenes = [
        {"id": "s1", "section": "h", "visual": {"type": "article_image", "path": str(busy_png)}, "overlay": None},
    ]
    pid = _project(tmp_path, scenes)

    def _fake_render(scene, *, variant, work_dir, theme):
        work_dir.mkdir(parents=True, exist_ok=True)
        sid = scene.get("id", "scene")
        dst = work_dir / f"{sid}.png"
        import shutil
        shutil.copy(busy_png, dst)
        return dst

    with patch("pipeline.director.still_gate.render_scene_still", _fake_render):
        result = runner.invoke(storyboard_app, ["still-gate", pid])
    assert result.exit_code == 0
