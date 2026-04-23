from __future__ import annotations

import json
from pathlib import Path

import pytest

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
        tmp_path, "1003",
        files=["source/video.mp4", "knowledge.json", "storyboard.json"],
    )
    [p] = scan_projects(tmp_path / "output")
    assert p.status == "storyboard"


def test_status_rendered(tmp_path: Path) -> None:
    _make_project(
        tmp_path, "1004",
        files=["source/video.mp4", "knowledge.json", "storyboard.json",
               "compose/final_zh-TW.mp4"],
    )
    [p] = scan_projects(tmp_path / "output")
    assert p.status == "rendered"
    assert p.has_video is True
    assert p.final_video_url_path == "/output/projects/1004/compose/final_zh-TW.mp4"


def test_status_published(tmp_path: Path) -> None:
    _make_project(
        tmp_path, "1005",
        ctx_extra={"youtube_video_id": "xyz999", "published_at": "2026-04-23T00:00:00+00:00"},
        files=["compose/final_zh-TW.mp4"],
    )
    [p] = scan_projects(tmp_path / "output")
    assert p.status == "published"
    assert p.youtube_video_id == "xyz999"
    assert p.published_at == "2026-04-23T00:00:00+00:00"


def test_title_and_tags_from_metadata(tmp_path: Path) -> None:
    _make_project(
        tmp_path, "1006",
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
