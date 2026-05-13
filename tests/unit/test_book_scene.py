from __future__ import annotations

from pathlib import Path

from pipeline.composer.animation_review import compute_metrics, summarize_metrics
from pipeline.composer.book_scene import BookSceneSpec, _blank_book_canvas


def test_open_book_spec_matches_existing_frame_geometry() -> None:
    spec = BookSceneSpec.open_book(1280, 720)

    assert spec.page.x == 83
    assert spec.page.y == 54
    assert spec.page.w == 1114
    assert spec.page.h == 612
    assert spec.inset.w == 947
    assert spec.inset.h == 484
    assert spec.as_frame_geometry()["inset_w"] == 947


def test_blank_book_canvas_has_textured_pages_without_strong_center_column(tmp_path: Path) -> None:
    spec = BookSceneSpec.open_book(1280, 720)
    frame = tmp_path / "frame_00000.png"
    _blank_book_canvas(spec).convert("RGB").save(frame)

    frame_metrics, delta_metrics = compute_metrics([frame, frame], fps=30)
    stats = summarize_metrics(frame_metrics, delta_metrics)

    assert stats["blank_like_frame_count"] == 0
    assert stats["center_brown_column_frame_count"] == 0
