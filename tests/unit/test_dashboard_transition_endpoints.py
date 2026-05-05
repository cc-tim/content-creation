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
