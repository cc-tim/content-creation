import json
from pathlib import Path

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


def test_still_gate_exits_2_on_duplicate_frames(tmp_path, flat_grey_png, monkeypatch):
    """End-to-end (NO mock): two scenes sharing one image render to identical
    composited stills, so duplicate_frame fires and the CLI exits 2."""
    monkeypatch.setenv("PIPELINE_OUTPUT_DIR", str(tmp_path))
    scenes = [
        {"id": "s1", "section": "h", "visual": {"type": "article_image", "path": str(flat_grey_png)}, "overlay": None},
        {"id": "s2", "section": "h", "visual": {"type": "article_image", "path": str(flat_grey_png)}, "overlay": None},
    ]
    pid = _project(tmp_path, scenes)
    result = runner.invoke(storyboard_app, ["still-gate", pid])
    assert result.exit_code == 2
    assert "duplicate_frame" in result.stdout


def test_still_gate_exits_0_when_clean(tmp_path, busy_png, monkeypatch):
    """A single distinct, content-rich scene yields no findings → exit 0."""
    monkeypatch.setenv("PIPELINE_OUTPUT_DIR", str(tmp_path))
    scenes = [
        {"id": "s1", "section": "h", "visual": {"type": "article_image", "path": str(busy_png)}, "overlay": None},
    ]
    pid = _project(tmp_path, scenes)
    result = runner.invoke(storyboard_app, ["still-gate", pid])
    assert result.exit_code == 0
