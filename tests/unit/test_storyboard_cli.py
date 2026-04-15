from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from pipeline.storyboard import Scene, Storyboard


def _write_storyboard(work_dir: Path) -> Path:
    sb = Storyboard(
        scenes=[
            Scene(
                id="hook_1",
                section="hook",
                narration="第一段旁白。",
                narration_est_sec=3.0,
                pause_after_sec=0.5,
                visual={"type": "text_card", "text": "hi"},
            ),
            Scene(
                id="ctx_1",
                section="context",
                narration="第二段旁白內容更長一些，看看顯示效果。",
                narration_est_sec=5.0,
                pause_after_sec=1.0,
                visual={"type": "text_card", "text": "hi"},
            ),
        ]
    )
    path = work_dir / "storyboard.json"
    sb.save(path)
    return path


def test_storyboard_show_lists_all_scenes(tmp_path):
    from pipeline.cli_storyboard import storyboard_app

    _write_storyboard(tmp_path)
    runner = CliRunner()
    result = runner.invoke(storyboard_app, ["show", "--work-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "hook_1" in result.output
    assert "ctx_1" in result.output
    assert "hook" in result.output
    assert "context" in result.output


def test_storyboard_show_single_scene(tmp_path):
    from pipeline.cli_storyboard import storyboard_app

    _write_storyboard(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        storyboard_app, ["show", "--scene", "ctx_1", "--work-dir", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    assert "第二段旁白內容更長一些" in result.output
    assert "ctx_1" in result.output


def _write_registry(voices_dir: Path, rec_dir: Path) -> None:
    voices_dir.mkdir(parents=True, exist_ok=True)
    (voices_dir / "registry.json").write_text(
        json.dumps(
            {
                "voices": [
                    {
                        "id": "tim-zhtw",
                        "engine": "prerecorded",
                        "locale": "zh-TW",
                        "params": {"recording_dir": str(rec_dir)},
                    },
                    {
                        "id": "zh-TW-default-f",
                        "engine": "edge",
                        "locale": "zh-TW",
                        "params": {"voice": "zh-TW-HsiaoChenNeural"},
                    },
                ]
            }
        ),
        encoding="utf-8",
    )


def test_storyboard_recordings_classifies_states(tmp_path, monkeypatch):
    from pipeline.cli_storyboard import storyboard_app

    work_dir = tmp_path / "work"
    work_dir.mkdir()
    _write_storyboard(work_dir)

    voices_dir = tmp_path / "voices"
    rec_dir = voices_dir / "prerecorded" / "tim-zhtw"
    rec_dir.mkdir(parents=True)
    _write_registry(voices_dir, rec_dir)

    # hook_1: recorded & fresh
    (rec_dir / "hook_1.wav").write_bytes(b"x")
    (rec_dir / "hook_1.txt").write_text("第一段旁白。", encoding="utf-8")

    # ctx_1: missing (no file)

    # orphan recording
    (rec_dir / "ghost_scene.wav").write_bytes(b"x")

    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        storyboard_app,
        ["recordings", "--voice", "tim-zhtw", "--work-dir", str(work_dir)],
    )
    assert result.exit_code == 0, result.output
    assert "hook_1" in result.output
    assert "recorded" in result.output
    assert "ctx_1" in result.output
    assert "missing" in result.output
    assert "ghost_scene" in result.output  # orphan section


def test_storyboard_recordings_marks_stale_when_text_drifts(tmp_path, monkeypatch):
    from pipeline.cli_storyboard import storyboard_app

    work_dir = tmp_path / "work"
    work_dir.mkdir()
    _write_storyboard(work_dir)

    voices_dir = tmp_path / "voices"
    rec_dir = voices_dir / "prerecorded" / "tim-zhtw"
    rec_dir.mkdir(parents=True)
    _write_registry(voices_dir, rec_dir)

    (rec_dir / "hook_1.wav").write_bytes(b"x")
    (rec_dir / "hook_1.txt").write_text("舊文字", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        storyboard_app,
        ["recordings", "--voice", "tim-zhtw", "--work-dir", str(work_dir)],
    )
    assert result.exit_code == 0, result.output
    assert "stale" in result.output


def test_storyboard_set_narration(tmp_path):
    from pipeline.cli_storyboard import storyboard_app

    _write_storyboard(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        storyboard_app,
        ["set", "hook_1", "narration=新的旁白內容", "--work-dir", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output

    data = json.loads((tmp_path / "storyboard.json").read_text())
    scene = next(s for s in data["scenes"] if s["id"] == "hook_1")
    assert scene["narration"] == "新的旁白內容"


def test_storyboard_set_pause(tmp_path):
    from pipeline.cli_storyboard import storyboard_app

    _write_storyboard(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        storyboard_app,
        ["set", "hook_1", "pause_after_sec=2.5", "--work-dir", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output

    data = json.loads((tmp_path / "storyboard.json").read_text())
    scene = next(s for s in data["scenes"] if s["id"] == "hook_1")
    assert scene["pause_after_sec"] == 2.5


def test_storyboard_set_rejects_unsafe_field(tmp_path):
    from pipeline.cli_storyboard import storyboard_app

    _write_storyboard(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        storyboard_app,
        ["set", "hook_1", "visual.type=still", "--work-dir", str(tmp_path)],
    )
    assert result.exit_code != 0


def test_storyboard_set_rejects_unknown_section(tmp_path):
    from pipeline.cli_storyboard import storyboard_app

    _write_storyboard(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        storyboard_app,
        ["set", "hook_1", "section=unknown", "--work-dir", str(tmp_path)],
    )
    assert result.exit_code != 0
