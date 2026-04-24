from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from pipeline.dashboard.server import create_app


def _output_dir(tmp_path: Path) -> Path:
    d = tmp_path / "output"
    d.mkdir()
    return d


def test_api_projects_empty(tmp_path: Path) -> None:
    client = TestClient(create_app(_output_dir(tmp_path)))
    resp = client.get("/api/projects")
    assert resp.status_code == 200
    assert resp.json() == []


def test_api_projects_returns_project(tmp_path: Path) -> None:
    output_dir = _output_dir(tmp_path)
    project_dir = output_dir / "projects" / "9999"
    project_dir.mkdir(parents=True)
    (project_dir / "context.json").write_text(json.dumps({
        "project_id": "9999",
        "locale": "zh-TW",
        "source_url": "https://www.youtube.com/watch?v=test123",
        "niche": "parenting",
        "youtube_video_id": None,
        "published_at": None,
    }))

    client = TestClient(create_app(output_dir))
    resp = client.get("/api/projects")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    p = data[0]
    assert p["project_id"] == "9999"
    assert p["status"] == "new"
    assert p["locale"] == "zh-TW"
    assert p["niche"] == "parenting"
    assert p["has_video"] is False
    assert p["tags"] == []


def test_api_projects_published_fields(tmp_path: Path) -> None:
    output_dir = _output_dir(tmp_path)
    project_dir = output_dir / "projects" / "8888"
    project_dir.mkdir(parents=True)
    (project_dir / "context.json").write_text(json.dumps({
        "project_id": "8888",
        "locale": "zh-TW",
        "source_url": "https://www.youtube.com/watch?v=src",
        "niche": None,
        "youtube_video_id": "pub123",
        "published_at": "2026-04-23T12:00:00+00:00",
    }))
    compose_dir = project_dir / "compose"
    compose_dir.mkdir()
    (compose_dir / "final_zh-TW.mp4").write_text("")
    (project_dir / "metadata.json").write_text(json.dumps({
        "title": "Test Title",
        "tags": ["a", "b"],
    }))

    client = TestClient(create_app(output_dir))
    resp = client.get("/api/projects")
    assert resp.status_code == 200
    [p] = resp.json()
    assert p["status"] == "published"
    assert p["youtube_video_id"] == "pub123"
    assert p["title"] == "Test Title"
    assert p["tags"] == ["a", "b"]
    assert p["has_video"] is True
    assert p["final_video_url_path"] == "/output/projects/8888/compose/final_zh-TW.mp4"


def test_index_serves_html(tmp_path: Path) -> None:
    client = TestClient(create_app(_output_dir(tmp_path)))
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert b"Content Dashboard" in resp.content
