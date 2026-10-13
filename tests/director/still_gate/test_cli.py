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


def test_still_gate_resolves_project_relative_image_with_cwd_elsewhere(tmp_path, busy_png, monkeypatch):
    """A project-relative article_image that `pipeline validate` accepts must render in the
    still-gate too, whatever the cwd (no [render_error], exit 0)."""
    import shutil

    monkeypatch.setenv("PIPELINE_OUTPUT_DIR", str(tmp_path))
    scenes = [
        {"id": "s1", "section": "h", "visual": {"type": "article_image", "path": "source/busy.png"}, "overlay": None},
    ]
    pid = _project(tmp_path, scenes)
    source_dir = tmp_path / "projects" / pid / "source"
    source_dir.mkdir()
    shutil.copyfile(busy_png, source_dir / "busy.png")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    result = runner.invoke(storyboard_app, ["still-gate", pid])

    assert "render_error" not in result.output
    assert result.exit_code == 0, result.output


def test_still_gate_toon_error_names_the_storyboard_file(tmp_path, monkeypatch):
    """Sprint 11 (code review R1 M10): a bad inline toon scene's render_error names the
    storyboard file and scene id, as `pipeline validate` and compose do."""
    monkeypatch.setenv("PIPELINE_OUTPUT_DIR", str(tmp_path))
    toon = {"type": "toon", "cast": {"tim": "tim"}, "shots": [{
        "at": 0.0, "set": "office", "camera": "two_shot",
        "place": {"tim": {"spot": "desk_seat", "pose": "sit_typing"}},
        "beats": [{"at": 1.0, "show": {"bubble": ["Dishes. Now."], "from": "tim"}}]}]}
    pid = _project(tmp_path, [{"id": "s1", "section": "h", "visual": toon, "overlay": None}])
    result = runner.invoke(storyboard_app, ["still-gate", pid])
    sb_file = tmp_path / "projects" / pid / "storyboard.json"
    assert f"{sb_file} scene s1: shots[0].beats[0].show" in result.output, result.output
