from __future__ import annotations

from PIL import Image

from pipeline.composer.book_scene import (
    BookSceneSpec,
    _blank_book_canvas,
    _multi_page_turn_surfaces,
)


def test_open_book_spec_matches_existing_frame_geometry() -> None:
    spec = BookSceneSpec.open_book(1280, 720)

    assert spec.page.x == 83
    assert spec.page.y == 54
    assert spec.page.w == 1114
    assert spec.page.h == 612
    assert spec.inset.w == 947
    assert spec.inset.h == 484
    assert spec.as_frame_geometry()["inset_w"] == 947


def test_multi_page_turn_surfaces_repeat_destination_scene_after_first_flip() -> None:
    source_scene = Image.new("RGBA", (16, 9), "red")
    destination_scene = Image.new("RGBA", (16, 9), "blue")

    first_source, first_under = _multi_page_turn_surfaces(source_scene, destination_scene, 0)
    repeat_source, repeat_under = _multi_page_turn_surfaces(source_scene, destination_scene, 1)

    assert first_source is source_scene
    assert first_under is destination_scene
    assert repeat_source is destination_scene
    assert repeat_under is destination_scene


def test_multi_page_turn_surfaces_can_use_calligraphy_texture() -> None:
    source_scene = Image.new("RGBA", (160, 90), "red")
    destination_scene = Image.new("RGBA", (160, 90), "blue")
    calligraphy_page = _blank_book_canvas(BookSceneSpec.open_book(160, 90))

    first_source, first_under = _multi_page_turn_surfaces(
        source_scene,
        destination_scene,
        0,
        flip_count=5,
        page_surface="calligraphy_texture",
        calligraphy_page=calligraphy_page,
    )
    middle_source, middle_under = _multi_page_turn_surfaces(
        source_scene,
        destination_scene,
        2,
        flip_count=5,
        page_surface="calligraphy_texture",
        calligraphy_page=calligraphy_page,
    )
    final_source, final_under = _multi_page_turn_surfaces(
        source_scene,
        destination_scene,
        4,
        flip_count=5,
        page_surface="calligraphy_texture",
        calligraphy_page=calligraphy_page,
    )

    assert first_source is source_scene
    assert first_under is calligraphy_page
    assert middle_source is calligraphy_page
    assert middle_under is calligraphy_page
    assert final_source is calligraphy_page
    assert final_under is destination_scene
