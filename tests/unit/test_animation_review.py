from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from pipeline.composer.animation_review import (
    ReviewTarget,
    build_findings,
    compute_metrics,
    review_frame_files,
    summarize_metrics,
)


def _write_frame(path: Path, color: tuple[int, int, int], *, center_column: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (160, 90), color)
    draw = ImageDraw.Draw(image)
    draw.rectangle((12, 10, 148, 80), outline=(205, 170, 98), width=2)
    if center_column:
        draw.rectangle((76, 10, 84, 80), fill=(115, 82, 38))
    image.save(path)


def test_transition_findings_flag_blank_page_and_center_column(tmp_path: Path) -> None:
    frames: list[Path] = []
    for idx in range(12):
        path = tmp_path / "frames" / f"frame_{idx:05d}.png"
        _write_frame(path, (236, 224, 192), center_column=True)
        frames.append(path)

    frame_metrics, delta_metrics = compute_metrics(frames, fps=30)
    stats = summarize_metrics(frame_metrics, delta_metrics)
    findings = build_findings(
        ReviewTarget("s1_s2", tmp_path / "clip.mp4", "transition"),
        frame_metrics,
        delta_metrics,
        stats,
    )

    finding_types = {finding.type for finding in findings}
    assert "blank_page_dominance" in finding_types
    assert "center_brown_column_artifact" in finding_types


def test_center_column_detector_ignores_black_scene_matte(tmp_path: Path) -> None:
    frames: list[Path] = []
    for idx in range(12):
        path = tmp_path / "frames" / f"frame_{idx:05d}.png"
        _write_frame(path, (236, 224, 192))
        image = Image.open(path).convert("RGB")
        draw = ImageDraw.Draw(image)
        draw.rectangle((76, 10, 84, 80), fill=(12, 12, 12))
        image.save(path)
        frames.append(path)

    frame_metrics, delta_metrics = compute_metrics(frames, fps=30)
    stats = summarize_metrics(frame_metrics, delta_metrics)
    findings = build_findings(
        ReviewTarget("s1_s2", tmp_path / "clip.mp4", "transition"),
        frame_metrics,
        delta_metrics,
        stats,
    )

    assert "center_brown_column_artifact" not in {finding.type for finding in findings}


def test_intro_findings_flag_empty_brown_cover(tmp_path: Path) -> None:
    frames: list[Path] = []
    for idx in range(10):
        path = tmp_path / "intro" / f"frame_{idx:05d}.png"
        _write_frame(path, (92, 49, 25))
        frames.append(path)

    frame_metrics, delta_metrics = compute_metrics(frames, fps=30)
    stats = summarize_metrics(frame_metrics, delta_metrics)
    findings = build_findings(
        ReviewTarget("intro", tmp_path / "clip.mp4", "transition"),
        frame_metrics,
        delta_metrics,
        stats,
    )

    assert "intro_empty_brown_cover" in {finding.type for finding in findings}


def test_intro_cover_with_gold_title_detail_is_not_empty(tmp_path: Path) -> None:
    frames: list[Path] = []
    for idx in range(10):
        path = tmp_path / "intro" / f"frame_{idx:05d}.png"
        _write_frame(path, (92, 49, 25))
        image = Image.open(path).convert("RGB")
        draw = ImageDraw.Draw(image)
        draw.rectangle((44, 34, 116, 42), fill=(220, 155, 42))
        draw.rectangle((62, 50, 98, 54), fill=(255, 225, 120))
        image.save(path)
        frames.append(path)

    frame_metrics, delta_metrics = compute_metrics(frames, fps=30)
    stats = summarize_metrics(frame_metrics, delta_metrics)
    findings = build_findings(
        ReviewTarget("intro", tmp_path / "clip.mp4", "transition"),
        frame_metrics,
        delta_metrics,
        stats,
    )

    assert "intro_empty_brown_cover" not in {finding.type for finding in findings}


def test_scene_findings_flag_static_hold(tmp_path: Path) -> None:
    frames: list[Path] = []
    for idx in range(14):
        path = tmp_path / "scene" / f"frame_{idx:05d}.png"
        _write_frame(path, (180, 150, 115))
        frames.append(path)

    frame_metrics, delta_metrics = compute_metrics(frames, fps=30)
    stats = summarize_metrics(frame_metrics, delta_metrics)
    findings = build_findings(
        ReviewTarget("s2_scene", tmp_path / "clip.mp4", "scene"),
        frame_metrics,
        delta_metrics,
        stats,
    )

    assert "static_scene_hold" in {finding.type for finding in findings}


def test_review_frame_files_writes_agent_readable_artifacts(tmp_path: Path) -> None:
    frames: list[Path] = []
    for idx in range(8):
        path = tmp_path / "frames" / f"frame_{idx:05d}.png"
        _write_frame(path, (236, 224, 192), center_column=idx % 2 == 0)
        frames.append(path)

    review = review_frame_files(
        ReviewTarget("s1_s2", tmp_path / "clip.mp4", "transition"),
        frames,
        tmp_path / "review",
        fps=30,
        duration_sec=8 / 30,
    )

    assert review.agent_review_status == "warn"
    for artifact in review.artifacts.values():
        assert Path(artifact).exists()
