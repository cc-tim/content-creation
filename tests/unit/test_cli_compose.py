"""Tests for pipeline compose subcommands."""
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from pipeline.cli_compose import compose_app
from pipeline.stages.base import PipelineContext
from pipeline.stages.compose import _book_start_title, _render_book_start_cover
from pipeline.storyboard import Scene, Storyboard


def _close_coro(coro):
    coro.close()
    return None


@pytest.fixture()
def project_dir(tmp_path):
    """Set up a minimal project dir with context.json and raws."""
    work_dir = tmp_path / "projects" / "9999"
    compose_dir = work_dir / "compose"
    scenes_dir = compose_dir / "scenes"
    scenes_dir.mkdir(parents=True)
    audio_dir = work_dir / "audio"
    audio_dir.mkdir()
    subs = audio_dir / "subs.srt"
    subs.write_text("1\n00:00:00,000 --> 00:00:01,000\nx\n")
    storyboard_path = work_dir / "storyboard.json"
    storyboard_path.write_text('{"scenes": [], "aspect_ratio": "16:9", "theme": {}}')

    ctx = PipelineContext(
        project_id=9999, source_url="x", locale="zh-TW",
        work_dir=work_dir, subtitle_path=subs, storyboard_path=storyboard_path,
    )
    ctx.save()

    (compose_dir / "raw.mp4").write_bytes(b"raw")
    (compose_dir / "raw_no_overlay.mp4").write_bytes(b"raw_no_ov")
    (compose_dir / "final_zh-TW.mp4").write_bytes(b"final")
    (compose_dir / "final_zh-TW_subtitles_no_overlay.mp4").write_bytes(b"subs_no_ov")
    (scenes_dir / "s1_final.mp4").write_bytes(b"s1f")
    (scenes_dir / "s1_final_no_overlay.mp4").write_bytes(b"s1f_no_ov")
    return work_dir


def test_set_variant_updates_context(project_dir, tmp_path):
    """set-variant persists preferred_variant in context.json."""
    runner = CliRunner()
    with patch("pipeline.cli_compose._resolve_work_dir", return_value=project_dir):
        result = runner.invoke(compose_app, [
            "set-variant", "--project-id", "9999", "--variant", "subtitles_no_overlay"
        ])
    assert result.exit_code == 0, result.output
    ctx = PipelineContext.load(project_dir / "context.json")
    assert ctx.preferred_variant == "subtitles_no_overlay"


def test_rescene_deletes_scene_finals(project_dir, tmp_path):
    """rescene deletes sN_final.mp4 and sN_final_no_overlay.mp4, then re-runs compose."""
    runner = CliRunner()
    with (
        patch("pipeline.cli_compose._resolve_work_dir", return_value=project_dir),
        patch("pipeline.cli_compose.asyncio.run", side_effect=_close_coro) as mock_run,
    ):
        result = runner.invoke(compose_app, [
            "rescene", "--project-id", "9999", "--scene", "s1"
        ])
    assert result.exit_code == 0, result.output
    scenes_dir = project_dir / "compose" / "scenes"
    assert not (scenes_dir / "s1_final.mp4").exists()
    assert not (scenes_dir / "s1_final_no_overlay.mp4").exists()
    assert mock_run.called


def test_reburn_calls_burn_pass_for_subs_no_overlay(project_dir):
    """reburn --variant subtitles_no_overlay burns subs over raw_no_overlay.mp4."""
    runner = CliRunner()
    burned: list[tuple[Path, Path]] = []

    def fake_burn(src, dst, subtitle_path, theme_dict):
        burned.append((src, dst))
        dst.write_bytes(b"burned")

    with (
        patch("pipeline.cli_compose._resolve_work_dir", return_value=project_dir),
        patch("pipeline.cli_compose._burn_subtitle_pass", fake_burn),
    ):
        result = runner.invoke(compose_app, [
            "reburn", "--project-id", "9999", "--variant", "subtitles_no_overlay"
        ])
    assert result.exit_code == 0, result.output
    assert len(burned) == 1
    assert burned[0][0].name == "raw_no_overlay.mp4"
    assert burned[0][1].name == "final_zh-TW_subtitles_no_overlay.mp4"


def test_transitions_rebuild_deletes_transition_and_concat_outputs(project_dir):
    sb = Storyboard(
        scenes=[
            Scene(id="s1", section="content", narration="a", narration_est_sec=1.0),
        ]
    )
    sb.save(project_dir / "storyboard.json")
    transition_dir = project_dir / "compose" / "transitions"
    transition_dir.mkdir()
    (transition_dir / "old.mp4").write_bytes(b"old")
    runner = CliRunner()

    with (
        patch("pipeline.cli_compose._resolve_work_dir", return_value=project_dir),
        patch("pipeline.cli_compose.asyncio.run", side_effect=_close_coro) as mock_run,
    ):
        result = runner.invoke(compose_app, [
            "transitions", "--project-id", "9999",
        ])

    assert result.exit_code == 0, result.output
    assert not transition_dir.exists()
    assert not (project_dir / "compose" / "raw.mp4").exists()
    assert not (project_dir / "compose" / "final_zh-TW_subtitles_no_overlay.mp4").exists()
    assert mock_run.called


def test_frame_reuses_cached_visuals_and_rebuilds_outputs(project_dir):
    sb = Storyboard(
        scenes=[
            Scene(id="s1", section="content", narration="a", narration_est_sec=1.0),
        ]
    )
    sb.save(project_dir / "storyboard.json")
    scenes_dir = project_dir / "compose" / "scenes"
    (scenes_dir / "s1_visual.mp4").write_bytes(b"visual")
    runner = CliRunner()

    with (
        patch("pipeline.cli_compose._resolve_work_dir", return_value=project_dir),
        patch("pipeline.cli_compose._frame_scene_outputs") as frame_outputs,
        patch("pipeline.cli_compose._rebuild_transitions_and_concat") as rebuild,
    ):
        result = runner.invoke(compose_app, [
            "frame", "--project-id", "9999",
        ])

    assert result.exit_code == 0, result.output
    assert frame_outputs.called
    assert rebuild.called


def test_frame_accepts_string_project_id(project_dir):
    runner = CliRunner()
    with (
        patch("pipeline.cli_compose._resolve_work_dir", return_value=project_dir) as resolve,
        patch("pipeline.cli_compose._frame_scene_outputs"),
        patch("pipeline.cli_compose._rebuild_transitions_and_concat"),
    ):
        result = runner.invoke(compose_app, [
            "frame", "--project-id", "20260504-115232-baby-walker-story",
        ])

    assert result.exit_code == 0, result.output
    resolve.assert_called_once_with("20260504-115232-baby-walker-story")


def test_book_start_title_reads_explainer_frontmatter(tmp_path: Path) -> None:
    project = tmp_path / "project"
    compose_dir = project / "compose"
    source_dir = project / "source"
    source_dir.mkdir(parents=True)
    compose_dir.mkdir()
    (source_dir / "explainer.md").write_text(
        '---\ntitle: "Baby Walkers: A 600-Year Design"\n---\n',
        encoding="utf-8",
    )

    assert _book_start_title(compose_dir) == "Baby Walkers: A 600-Year Design"


def test_render_book_start_cover_adds_gold_title_detail() -> None:
    image = _render_book_start_cover(640, 360, "Baby Walkers: A 600-Year Design")
    data = image.convert("RGB").tobytes()

    gold_pixels = sum(
        1
        for idx in range(0, len(data), 3)
        if data[idx] > 180 and data[idx + 1] > 120 and data[idx + 2] < 90
    )
    assert gold_pixels > 200
