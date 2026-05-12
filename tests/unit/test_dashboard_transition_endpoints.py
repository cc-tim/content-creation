from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pipeline.dashboard.server import create_app
from pipeline.storyboard import Scene, Storyboard


def _seed_project(projects_dir: Path, project_id: str = "42") -> Path:
    proj = projects_dir / project_id
    proj.mkdir(parents=True, exist_ok=True)
    sb = Storyboard(scenes=[
        Scene(id="s1", section="content", narration="a", narration_est_sec=1.0),
        Scene(id="s2", section="content", narration="b", narration_est_sec=1.0),
    ])
    sb.save(proj / "storyboard.json")
    return proj


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    out_root = tmp_path / "output"
    projects_dir = out_root / "projects"
    _seed_project(projects_dir)
    monkeypatch.setattr(
        "pipeline.cli_transition.PipelineConfig",
        lambda: type("C", (), {"OUTPUT_DIR": out_root})(),
    )
    app = create_app(projects_dir)
    return TestClient(app)


def test_set_transition_writes_storyboard(client: TestClient, tmp_path: Path):
    resp = client.post("/api/transition/42/set", json={
        "from_scene": "s1", "to_scene": "s2",
        "style": "page-turn", "duration_sec": 0.5,
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert "page-turn" in body["summary"]
    sb = Storyboard.load(tmp_path / "output" / "projects" / "42" / "storyboard.json")
    assert len(sb.transitions) == 1
    assert sb.transitions[0].style == "page-turn"


def test_set_transition_with_sfx(client: TestClient, tmp_path: Path):
    resp = client.post("/api/transition/42/set", json={
        "from_scene": "s1", "to_scene": "s2",
        "style": "fade", "duration_sec": 0.3,
        "sfx": "assets/sfx/whoosh.mp3",
    })
    assert resp.status_code == 200
    sb = Storyboard.load(tmp_path / "output" / "projects" / "42" / "storyboard.json")
    assert sb.transitions[0].sfx == "assets/sfx/whoosh.mp3"


def test_set_transition_with_page_count(client: TestClient, tmp_path: Path):
    resp = client.post("/api/transition/42/set", json={
        "from_scene": "s1", "to_scene": "s2",
        "style": "book-page-turn", "duration_sec": 0.8,
        "page_count": 3,
    })
    assert resp.status_code == 200
    sb = Storyboard.load(tmp_path / "output" / "projects" / "42" / "storyboard.json")
    assert sb.transitions[0].style == "book-page-turn"
    assert sb.transitions[0].page_count == 3


def test_set_transition_with_stock_asset_metadata(client: TestClient, tmp_path: Path):
    resp = client.post("/api/transition/42/set", json={
        "from_scene": "s1",
        "to_scene": "s2",
        "style": "stock-book-page-turn",
        "duration_sec": 1.2,
        "renderer_mode": "licensed_clip",
        "asset_path": "assets/transitions/book_page_flip.mp4",
        "asset_source": "Artgrid",
        "asset_source_url": "https://example.com/artgrid",
        "asset_license": "licensed full clip",
        "asset_notes": "replace preview before publish",
    })
    assert resp.status_code == 200
    sb = Storyboard.load(tmp_path / "output" / "projects" / "42" / "storyboard.json")
    transition = sb.transitions[0]
    assert transition.style == "stock-book-page-turn"
    assert transition.renderer_mode == "licensed_clip"
    assert transition.asset_path == "assets/transitions/book_page_flip.mp4"
    assert transition.asset_source == "Artgrid"
    assert transition.asset_source_url == "https://example.com/artgrid"
    assert transition.asset_license == "licensed full clip"
    assert transition.asset_notes == "replace preview before publish"


def test_set_intro_transition_writes_theme(client: TestClient, tmp_path: Path):
    resp = client.post("/api/transition/42/intro/set", json={
        "style": "book-page-turn",
        "duration_sec": 1.0,
        "page_count": 2,
    })
    assert resp.status_code == 200
    sb = Storyboard.load(tmp_path / "output" / "projects" / "42" / "storyboard.json")
    assert sb.theme.intro_transition_style == "book-page-turn"
    assert sb.theme.intro_transition_duration_sec == "1.0"
    assert sb.theme.intro_transition_page_count == "2"


def test_set_intro_transition_with_stock_asset_metadata(client: TestClient, tmp_path: Path):
    resp = client.post("/api/transition/42/intro/set", json={
        "style": "stock-book-page-turn",
        "duration_sec": 1.2,
        "page_count": 2,
        "renderer_mode": "licensed_clip",
        "asset_path": "assets/transitions/book_page_flip.mp4",
        "asset_source": "Artgrid",
        "asset_source_url": "https://example.com/artgrid",
        "asset_license": "licensed full clip",
        "asset_notes": "replace preview before publish",
    })
    assert resp.status_code == 200
    sb = Storyboard.load(tmp_path / "output" / "projects" / "42" / "storyboard.json")
    assert sb.theme.intro_transition_style == "stock-book-page-turn"
    assert sb.theme.intro_transition_renderer_mode == "licensed_clip"
    assert sb.theme.intro_transition_asset_path == "assets/transitions/book_page_flip.mp4"
    assert sb.theme.intro_transition_asset_source == "Artgrid"
    assert sb.theme.intro_transition_asset_source_url == "https://example.com/artgrid"
    assert sb.theme.intro_transition_asset_license == "licensed full clip"
    assert sb.theme.intro_transition_asset_notes == "replace preview before publish"


def test_clear_intro_transition_clears_theme(client: TestClient, tmp_path: Path):
    client.post("/api/transition/42/intro/set", json={
        "style": "book-page-turn",
        "duration_sec": 1.0,
        "page_count": 2,
    })
    resp = client.post("/api/transition/42/intro/clear")
    assert resp.status_code == 200
    sb = Storyboard.load(tmp_path / "output" / "projects" / "42" / "storyboard.json")
    assert sb.theme.intro_transition_style == ""
    assert sb.theme.intro_transition_duration_sec == ""
    assert sb.theme.intro_transition_page_count == ""
    assert sb.theme.intro_transition_renderer_mode == ""
    assert sb.theme.intro_transition_asset_path == ""


def test_compose_transitions_endpoint_starts_action(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    called = {}

    async def fake_start(app, running_actions, *, project_id, action, runner):
        called["project_id"] = project_id
        called["action"] = action
        return "action123"

    monkeypatch.setattr("pipeline.dashboard.server._start_compose_action", fake_start)
    resp = client.post("/api/compose/42/transitions")
    assert resp.status_code == 200
    assert resp.json()["action_id"] == "action123"
    assert called == {"project_id": "42", "action": "transitions"}


def test_compose_frame_endpoint_starts_action(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    called = {}

    async def fake_start(app, running_actions, *, project_id, action, runner):
        called["project_id"] = project_id
        called["action"] = action
        return "action456"

    monkeypatch.setattr("pipeline.dashboard.server._start_compose_action", fake_start)
    resp = client.post("/api/compose/42/frame")
    assert resp.status_code == 200
    assert resp.json()["action_id"] == "action456"
    assert called == {"project_id": "42", "action": "frame"}


def test_compose_rescene_endpoint_requires_scene_list(client: TestClient):
    resp = client.post("/api/compose/42/rescene", json={"scenes": []})
    assert resp.status_code == 400
    assert "scene" in resp.json()["detail"]


def test_preview_loop_endpoint_returns_output_urls(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "pipeline.dashboard.preview.build_project_preview_manifest",
        lambda _proj: {
            "scenes": [{"id": "s1", "label": "s1", "path": "compose/previews/scenes/s1.jpg"}],
            "transitions": [{"id": "intro", "label": "intro", "path": "compose/previews/transitions/intro.jpg"}],
        },
    )
    resp = client.get("/api/projects/42/preview-loop")
    assert resp.status_code == 200
    body = resp.json()
    assert body["scenes"][0]["url"] == "/output/projects/42/compose/previews/scenes/s1.jpg"
    assert body["transitions"][0]["url"] == "/output/projects/42/compose/previews/transitions/intro.jpg"


def test_transition_preview_endpoint_returns_output_url(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    preview = tmp_path / "output" / "projects" / "42" / "compose" / "previews" / "transitions" / "draft.jpg"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_bytes(b"jpg")
    monkeypatch.setattr(
        "pipeline.dashboard.preview.build_transition_preview_image",
        lambda *_args, **_kwargs: preview,
    )
    resp = client.post("/api/transition/42/preview", json={
        "from_scene": "s1",
        "to_scene": "s2",
        "style": "fade",
        "duration_sec": 0.5,
        "preview_name": "draft",
    })
    assert resp.status_code == 200
    assert resp.json()["url"] == "/output/projects/42/compose/previews/transitions/draft.jpg"


def test_set_transition_rejects_unknown_style(client: TestClient):
    resp = client.post("/api/transition/42/set", json={
        "from_scene": "s1", "to_scene": "s2",
        "style": "ribbon", "duration_sec": 0.5,
    })
    assert resp.status_code == 400
    assert "ribbon" in resp.json()["detail"] or "Unknown" in resp.json()["detail"]


def test_set_transition_rejects_unknown_scene(client: TestClient):
    resp = client.post("/api/transition/42/set", json={
        "from_scene": "s1", "to_scene": "s99",
        "style": "fade", "duration_sec": 0.5,
    })
    assert resp.status_code == 400
    assert "s99" in resp.json()["detail"]


def test_set_transition_404_when_project_missing(client: TestClient):
    resp = client.post("/api/transition/nope/set", json={
        "from_scene": "s1", "to_scene": "s2",
        "style": "fade", "duration_sec": 0.5,
    })
    assert resp.status_code == 404


def test_clear_transition_removes_entry(client: TestClient, tmp_path: Path):
    client.post("/api/transition/42/set", json={
        "from_scene": "s1", "to_scene": "s2",
        "style": "fade", "duration_sec": 0.3,
    })
    resp = client.post("/api/transition/42/clear", json={
        "from_scene": "s1", "to_scene": "s2",
    })
    assert resp.status_code == 200
    sb = Storyboard.load(tmp_path / "output" / "projects" / "42" / "storyboard.json")
    assert sb.transitions == []


def test_clear_transition_noop_when_absent(client: TestClient):
    resp = client.post("/api/transition/42/clear", json={
        "from_scene": "s1", "to_scene": "s2",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert "nothing" in body["summary"].lower() or "no transition" in body["summary"].lower()


def test_set_transition_409_when_storyboard_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    out_root = tmp_path / "output"
    projects_dir = out_root / "projects"
    (projects_dir / "77").mkdir(parents=True)
    monkeypatch.setattr(
        "pipeline.cli_transition.PipelineConfig",
        lambda: type("C", (), {"OUTPUT_DIR": out_root})(),
    )
    app = create_app(projects_dir)
    client = TestClient(app)
    resp = client.post("/api/transition/77/set", json={
        "from_scene": "s1", "to_scene": "s2",
        "style": "fade", "duration_sec": 0.3,
    })
    assert resp.status_code == 409
    assert "storyboard" in resp.json()["detail"].lower()
