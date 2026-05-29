"""Tests for `pipeline compose music` orchestration (ffmpeg fns monkeypatched)."""
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from pipeline.cli_compose import compose_app
from pipeline.composer.music import MoodTrack
from pipeline.stages.base import PipelineContext
from pipeline.storyboard import Scene, Storyboard, Theme


def _make_project(tmp_path, moods, theme_default="none", with_final=True):
    """moods: list of (scene_id, music_mood). Builds a minimal work_dir."""
    work_dir = tmp_path / "projects" / "9999"
    compose_dir = work_dir / "compose"
    compose_dir.mkdir(parents=True)
    storyboard_path = work_dir / "storyboard.json"

    scenes = [
        Scene(id=i, section="rising", narration="x", narration_est_sec=1.0, music_mood=m)
        for i, m in moods
    ]
    Storyboard(theme=Theme(music_default_mood=theme_default), scenes=scenes).save(storyboard_path)

    rows = [
        {"id": i, "section": "rising", "start_sec": float(n * 5),
         "duration_sec": 5.0, "narration": "x"}
        for n, (i, _) in enumerate(moods)
    ]
    (compose_dir / "scenes.json").write_text(json.dumps(rows), encoding="utf-8")
    (compose_dir / "raw.mp4").write_bytes(b"raw")
    if with_final:
        (compose_dir / "final_zh-TW_subtitles_no_overlay.mp4").write_bytes(b"final")

    PipelineContext(
        project_id=9999, source_url="x", locale="zh-TW",
        work_dir=work_dir, storyboard_path=storyboard_path,
    ).save()
    return work_dir


def _patch_ffmpeg(monkeypatch, library):
    build = MagicMock(return_value=Path("/tmp/bed.m4a"))
    duck = MagicMock(return_value=Path("/tmp/ducked.m4a"))
    mux = MagicMock()
    monkeypatch.setattr("pipeline.composer.music.build_bed", build)
    monkeypatch.setattr("pipeline.composer.music.duck_bed", duck)
    monkeypatch.setattr("pipeline.composer.music.mux_music_onto_final", mux)
    monkeypatch.setattr("pipeline.composer.music.load_library", lambda *a, **k: library)
    monkeypatch.setattr("pipeline.stages.compose._get_duration_sec", lambda p: 25.0)
    return build, duck, mux


def _run(work_dir, monkeypatch, args):
    monkeypatch.setattr("pipeline.cli_compose._resolve_work_dir", lambda pid: work_dir)
    return CliRunner().invoke(compose_app, ["music", "--project-id", "9999", *args])


def test_music_short_circuits_when_no_moods(tmp_path, monkeypatch):
    work_dir = _make_project(tmp_path, [("s1", ""), ("s2", "")])
    build, _, mux = _patch_ffmpeg(monkeypatch, {})
    res = _run(work_dir, monkeypatch, [])
    assert res.exit_code == 0, res.output
    assert "nothing to do" in res.output.lower()
    build.assert_not_called()
    mux.assert_not_called()


def test_music_errors_when_bed_missing(tmp_path, monkeypatch):
    work_dir = _make_project(tmp_path, [("s1", "tense")])
    _patch_ffmpeg(monkeypatch, {})  # empty library
    res = _run(work_dir, monkeypatch, [])
    assert res.exit_code == 1
    assert "tense" in res.output


def test_music_dry_run_prints_plan_and_skips_render(tmp_path, monkeypatch):
    work_dir = _make_project(tmp_path, [("s1", "tense")])
    build, _, mux = _patch_ffmpeg(monkeypatch, {"tense": MoodTrack("tense", Path("/x/t.mp3"))})
    res = _run(work_dir, monkeypatch, ["--dry-run"])
    assert res.exit_code == 0, res.output
    assert "tense" in res.output and "cue" in res.output.lower()
    build.assert_not_called()
    mux.assert_not_called()


def test_music_happy_path_builds_and_muxes(tmp_path, monkeypatch):
    work_dir = _make_project(tmp_path, [("s1", "tense")])
    build, duck, mux = _patch_ffmpeg(monkeypatch, {"tense": MoodTrack("tense", Path("/x/t.mp3"))})
    res = _run(work_dir, monkeypatch, [])
    assert res.exit_code == 0, res.output
    build.assert_called_once()
    duck.assert_called_once()
    mux.assert_called_once()  # one final variant present
    assert "Done" in res.output
