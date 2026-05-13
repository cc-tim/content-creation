from __future__ import annotations

import json
import os
from pathlib import Path

from pipeline.dashboard.scanner import scan_projects


def _make_project(
    tmp_path: Path,
    project_id: str,
    *,
    ctx_extra: dict | None = None,
    meta: dict | None = None,
    files: list[str] | None = None,
) -> Path:
    project_dir = tmp_path / "output" / "projects" / project_id
    project_dir.mkdir(parents=True)
    ctx: dict = {
        "project_id": project_id,
        "locale": "zh-TW",
        "source_url": "https://www.youtube.com/watch?v=abc123",
        "niche": None,
        "youtube_video_id": None,
        "published_at": None,
        **(ctx_extra or {}),
    }
    (project_dir / "context.json").write_text(json.dumps(ctx))
    if meta is not None:
        (project_dir / "metadata.json").write_text(json.dumps(meta))
    for rel in files or []:
        p = project_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("")
    return project_dir


def test_returns_empty_when_no_projects_dir(tmp_path: Path) -> None:
    result = scan_projects(tmp_path / "output")
    assert result == []


def test_status_new_when_only_context(tmp_path: Path) -> None:
    _make_project(tmp_path, "1000")
    [p] = scan_projects(tmp_path / "output")
    assert p.status == "new"
    assert p.has_video is False
    assert p.final_video_url_path is None


def test_status_acquired(tmp_path: Path) -> None:
    _make_project(tmp_path, "1001", files=["source/video.mp4"])
    [p] = scan_projects(tmp_path / "output")
    assert p.status == "acquired"


def test_status_analyzed(tmp_path: Path) -> None:
    _make_project(tmp_path, "1002", files=["source/video.mp4", "knowledge.json"])
    [p] = scan_projects(tmp_path / "output")
    assert p.status == "analyzed"


def test_status_storyboard(tmp_path: Path) -> None:
    _make_project(
        tmp_path,
        "1003",
        files=["source/video.mp4", "knowledge.json", "storyboard.json"],
    )
    [p] = scan_projects(tmp_path / "output")
    assert p.status == "storyboard"


def test_status_rendered(tmp_path: Path) -> None:
    _make_project(
        tmp_path,
        "1004",
        files=["source/video.mp4", "knowledge.json", "storyboard.json", "compose/final_zh-TW.mp4"],
    )
    [p] = scan_projects(tmp_path / "output")
    assert p.status == "rendered"
    assert p.has_video is True
    assert p.final_video_url_path == "/output/projects/1004/compose/final_zh-TW.mp4"


def test_status_published(tmp_path: Path) -> None:
    _make_project(
        tmp_path,
        "1005",
        ctx_extra={"youtube_video_id": "xyz999", "published_at": "2026-04-23T00:00:00+00:00"},
        files=["compose/final_zh-TW.mp4"],
    )
    [p] = scan_projects(tmp_path / "output")
    assert p.status == "published"
    assert p.youtube_video_id == "xyz999"
    assert p.published_at == "2026-04-23T00:00:00+00:00"


def test_title_and_tags_from_metadata(tmp_path: Path) -> None:
    _make_project(
        tmp_path,
        "1006",
        meta={"title": "My Video Title", "tags": ["tag1", "tag2"]},
    )
    [p] = scan_projects(tmp_path / "output")
    assert p.title == "My Video Title"
    assert p.tags == ["tag1", "tag2"]


def test_title_none_tags_empty_when_no_metadata(tmp_path: Path) -> None:
    _make_project(tmp_path, "1007")
    [p] = scan_projects(tmp_path / "output")
    assert p.title is None
    assert p.tags == []


def test_projects_sorted_newest_first(tmp_path: Path) -> None:
    _make_project(tmp_path, "1000")
    _make_project(tmp_path, "2000")
    _make_project(tmp_path, "1500")
    results = scan_projects(tmp_path / "output")
    assert [p.project_id for p in results] == ["2000", "1500", "1000"]


def test_locale_and_niche_populated(tmp_path: Path) -> None:
    _make_project(tmp_path, "1008", ctx_extra={"locale": "ja", "niche": "crime"})
    [p] = scan_projects(tmp_path / "output")
    assert p.locale == "ja"
    assert p.niche == "crime"


def test_project_with_invalid_context_json_is_skipped(tmp_path: Path) -> None:
    project_dir = tmp_path / "output" / "projects" / "bad"
    project_dir.mkdir(parents=True)
    (project_dir / "context.json").write_text("{invalid json")
    result = scan_projects(tmp_path / "output")
    assert result == []


def test_project_with_invalid_metadata_json_falls_back(tmp_path: Path) -> None:
    _make_project(tmp_path, "good")
    bad_dir = tmp_path / "output" / "projects" / "bad2"
    bad_dir.mkdir(parents=True)
    (bad_dir / "context.json").write_text(
        json.dumps(
            {
                "project_id": "bad2",
                "locale": "zh-TW",
                "source_url": None,
                "niche": None,
                "youtube_video_id": None,
                "published_at": None,
            }
        )
    )
    (bad_dir / "metadata.json").write_text("{not json}")
    results = scan_projects(tmp_path / "output")
    bad = next(p for p in results if p.project_id == "bad2")
    assert bad.title is None
    assert bad.tags == []


def test_scenes_empty_when_no_storyboard(tmp_path: Path) -> None:
    _make_project(tmp_path, "2001")
    [p] = scan_projects(tmp_path / "output")
    assert p.scenes == []


def test_scenes_loaded_from_scenes_json(tmp_path: Path) -> None:
    scenes = [
        {
            "id": "s1",
            "section": "hook",
            "start_sec": 0.0,
            "duration_sec": 5.0,
            "narration": "Hello",
        },
        {
            "id": "s2",
            "section": "context",
            "start_sec": 5.0,
            "duration_sec": 8.0,
            "narration": "World",
        },
    ]
    project_dir = _make_project(tmp_path, "2002")
    compose_dir = project_dir / "compose"
    compose_dir.mkdir()
    (compose_dir / "scenes.json").write_text(json.dumps(scenes))
    [p] = scan_projects(tmp_path / "output")
    assert p.scenes == scenes


def test_scenes_estimated_from_storyboard_fallback(tmp_path: Path) -> None:
    storyboard = {
        "scenes": [
            {
                "id": "s1",
                "section": "hook",
                "narration": "First",
                "narration_est_sec": 10.0,
                "pause_after_sec": 0.5,
            },
            {
                "id": "s2",
                "section": "context",
                "narration": "Second",
                "narration_est_sec": 20.0,
                "pause_after_sec": 0.0,
            },
        ]
    }
    project_dir = _make_project(tmp_path, "2003")
    (project_dir / "storyboard.json").write_text(json.dumps(storyboard))
    [p] = scan_projects(tmp_path / "output")
    assert len(p.scenes) == 2
    assert p.scenes[0] == {
        "id": "s1",
        "section": "hook",
        "start_sec": 0.0,
        "duration_sec": 10.5,
        "narration": "First",
    }
    assert p.scenes[1] == {
        "id": "s2",
        "section": "context",
        "start_sec": 10.5,
        "duration_sec": 20.0,
        "narration": "Second",
    }


def test_scenes_json_takes_priority_over_storyboard(tmp_path: Path) -> None:
    scenes_json = [
        {
            "id": "s1",
            "section": "hook",
            "start_sec": 0.0,
            "duration_sec": 5.0,
            "narration": "From file",
        }
    ]
    storyboard = {
        "scenes": [
            {
                "id": "s1",
                "section": "hook",
                "narration": "From storyboard",
                "narration_est_sec": 99.0,
                "pause_after_sec": 0,
            }
        ]
    }
    project_dir = _make_project(tmp_path, "2004")
    (project_dir / "storyboard.json").write_text(json.dumps(storyboard))
    compose_dir = project_dir / "compose"
    compose_dir.mkdir()
    (compose_dir / "scenes.json").write_text(json.dumps(scenes_json))
    [p] = scan_projects(tmp_path / "output")
    assert p.scenes[0]["narration"] == "From file"
    assert p.scenes[0]["duration_sec"] == 5.0


def test_scanner_attaches_scene_camera_motion_from_storyboard(tmp_path: Path) -> None:
    scenes_json = [
        {
            "id": "s1",
            "section": "hook",
            "start_sec": 0.0,
            "duration_sec": 5.0,
            "narration": "From file",
        }
    ]
    camera_motion = {
        "type": "slow_push_pan",
        "focus_point": {"x": 0.66, "y": 0.69},
        "zoom_end": 2.35,
    }
    storyboard = {
        "scenes": [
            {
                "id": "s1",
                "section": "hook",
                "narration": "From storyboard",
                "narration_est_sec": 99.0,
                "pause_after_sec": 0,
                "visual": {"type": "article_image", "camera_motion": camera_motion},
            }
        ]
    }
    project_dir = _make_project(tmp_path, "2004-camera")
    (project_dir / "storyboard.json").write_text(json.dumps(storyboard))
    compose_dir = project_dir / "compose"
    compose_dir.mkdir()
    (compose_dir / "scenes.json").write_text(json.dumps(scenes_json))

    [p] = scan_projects(tmp_path / "output")

    assert p.scenes[0]["narration"] == "From file"
    assert p.scenes[0]["camera_motion"] == camera_motion


def test_scanner_includes_transition_theme_and_intro_summary(tmp_path: Path) -> None:
    storyboard = {
        "theme": {
            "frame_style": "open_book_page",
            "content_inset": "center_page",
            "intro_transition_style": "book-page-turn",
            "intro_transition_duration_sec": "1.0",
            "intro_transition_page_count": "2",
            "intro_transition_renderer_mode": "licensed_clip",
            "intro_transition_asset_path": "assets/transitions/book_page_flip.mp4",
            "intro_transition_asset_source": "Artgrid",
            "intro_transition_asset_license": "licensed full clip",
        },
        "transitions": [
            {
                "from": "s1",
                "to": "s2",
                "style": "stock-book-page-turn",
                "duration_sec": 1.2,
                "page_count": 3,
                "renderer_mode": "licensed_clip",
                "asset_path": "assets/transitions/book_page_flip.mp4",
                "asset_source": "Artgrid",
                "asset_license": "licensed full clip",
                "asset_notes": "replace preview before publish",
            }
        ],
        "scenes": [
            {"id": "s1", "section": "hook", "narration": "First", "narration_est_sec": 1},
            {"id": "s2", "section": "body", "narration": "Second", "narration_est_sec": 1},
        ],
    }
    project_dir = _make_project(tmp_path, "2005")
    (project_dir / "storyboard.json").write_text(json.dumps(storyboard))

    [p] = scan_projects(tmp_path / "output")

    assert p.theme["frame_style"] == "open_book_page"
    assert p.intro_transition == {
        "style": "book-page-turn",
        "duration_sec": "1.0",
        "page_count": "2",
        "renderer_mode": "licensed_clip",
        "asset_path": "assets/transitions/book_page_flip.mp4",
        "asset_source": "Artgrid",
        "asset_source_url": None,
        "asset_license": "licensed full clip",
        "asset_notes": None,
        "asset_warning": None,
    }
    assert p.transitions == [
        {
            "from": "s1",
            "to": "s2",
            "style": "stock-book-page-turn",
            "duration_sec": 1.2,
            "page_count": 3,
            "sfx": None,
            "renderer_mode": "licensed_clip",
            "asset_path": "assets/transitions/book_page_flip.mp4",
            "asset_source": "Artgrid",
            "asset_source_url": None,
            "asset_license": "licensed full clip",
            "asset_notes": "replace preview before publish",
            "asset_warning": "Preview or watermarked stock asset noted. Replace it before publish.",
        }
    ]


def test_scanner_warns_when_storyboard_newer_than_final_render(tmp_path: Path) -> None:
    project_dir = _make_project(
        tmp_path,
        "2006",
        files=["storyboard.json", "compose/final_zh-TW.mp4"],
    )
    final = project_dir / "compose" / "final_zh-TW.mp4"
    storyboard = project_dir / "storyboard.json"
    os.utime(final, (1000, 1000))
    os.utime(storyboard, (2000, 2000))

    [p] = scan_projects(tmp_path / "output")

    assert p.render_freshness["stale"] is True
    assert "Recompose needed" in p.render_freshness["warnings"][0]
