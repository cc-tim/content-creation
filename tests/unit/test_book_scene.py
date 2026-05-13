from __future__ import annotations

from pipeline.composer.book_scene import BookSceneSpec


def test_open_book_spec_matches_existing_frame_geometry() -> None:
    spec = BookSceneSpec.open_book(1280, 720)

    assert spec.page.x == 83
    assert spec.page.y == 54
    assert spec.page.w == 1114
    assert spec.page.h == 612
    assert spec.inset.w == 947
    assert spec.inset.h == 484
    assert spec.as_frame_geometry()["inset_w"] == 947
