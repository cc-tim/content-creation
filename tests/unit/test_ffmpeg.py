import subprocess
from pathlib import Path

import pytest

from pipeline.utils import ffmpeg
from pipeline.utils.ffmpeg import (
    build_burn_subtitles_cmd,
    build_concat_cmd,
    build_extract_clip_cmd,
)


def test_extract_clip_cmd():
    cmd = build_extract_clip_cmd(
        input_path="video.mp4",
        output_path="clip.mp4",
        start_sec=83.0,
        end_sec=95.0,
    )
    assert "video.mp4" in cmd
    assert "clip.mp4" in cmd
    assert "-ss" in cmd
    assert "83.0" in cmd


def test_burn_subtitles_cmd():
    cmd = build_burn_subtitles_cmd(
        input_path="video.mp4",
        subtitle_path="subs.srt",
        output_path="output.mp4",
        font_name="Noto Sans CJK TC",
    )
    assert "subs.srt" in " ".join(cmd)
    assert "Noto Sans CJK TC" in " ".join(cmd)


def test_concat_cmd(tmp_path):
    filelist = tmp_path / "files.txt"
    cmd = build_concat_cmd(
        filelist_path=str(filelist),
        output_path="final.mp4",
    )
    assert "concat" in " ".join(cmd)
    assert "final.mp4" in cmd


def test_ffmpeg_concat_uses_atomic_output(tmp_path, monkeypatch):
    output = tmp_path / "final.mp4"
    inputs = [tmp_path / "a.mp4", tmp_path / "b.mp4"]
    seen = {}

    def fake_atomic(cmd: list[str], output_path: Path, timeout: int = 600):
        seen["cmd"] = cmd
        seen["output"] = output_path
        seen["timeout"] = timeout
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(ffmpeg, "run_ffmpeg_atomic", fake_atomic)

    ffmpeg.ffmpeg_concat(inputs, output)

    assert seen["output"] == output
    assert seen["cmd"][-1] == str(output)
    assert not (tmp_path / "_concat_final.txt").exists()


def test_run_ffmpeg_atomic_replaces_output_after_success(tmp_path, monkeypatch):
    output = tmp_path / "final.mp4"
    output.write_text("old", encoding="utf-8")

    def fake_run(cmd: list[str], timeout: int = 600):
        Path(cmd[-1]).write_text("new", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(ffmpeg, "run_ffmpeg", fake_run)

    ffmpeg.run_ffmpeg_atomic(["ffmpeg", "-y", "final.mp4"], output)

    assert output.read_text(encoding="utf-8") == "new"
    assert not list(tmp_path.glob(".final.*.tmp.mp4"))


def test_run_ffmpeg_atomic_keeps_existing_output_on_failure(tmp_path, monkeypatch):
    output = tmp_path / "final.mp4"
    output.write_text("old", encoding="utf-8")

    def fake_run(cmd: list[str], timeout: int = 600):
        Path(cmd[-1]).write_text("partial", encoding="utf-8")
        raise RuntimeError("encode interrupted")

    monkeypatch.setattr(ffmpeg, "run_ffmpeg", fake_run)

    with pytest.raises(RuntimeError, match="encode interrupted"):
        ffmpeg.run_ffmpeg_atomic(["ffmpeg", "-y", "final.mp4"], output)

    assert output.read_text(encoding="utf-8") == "old"
    assert not list(tmp_path.glob(".final.*.tmp.mp4"))
