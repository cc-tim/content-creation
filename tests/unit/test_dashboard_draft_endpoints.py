from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pipeline.dashboard.server import create_app


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    out_root = tmp_path / "output"
    projects_dir = out_root / "projects"
    proj = projects_dir / "42"
    proj.mkdir(parents=True)
    (proj / "storyboard.json").write_text(json.dumps({"version": 1, "scenes": []}))
    app = create_app(projects_dir)
    return TestClient(app)


def test_get_draft_returns_empty_when_absent(client: TestClient):
    resp = client.get("/api/jobs/42/draft")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"tokens": [], "instruction": ""}


def test_post_draft_then_get_returns_saved(client: TestClient, tmp_path: Path):
    payload = {
        "tokens": ["@s9/visual", "@s11/subtitle"],
        "instruction": "make these darker",
    }
    resp = client.post("/api/jobs/42/draft", json=payload)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    resp2 = client.get("/api/jobs/42/draft")
    assert resp2.status_code == 200
    assert resp2.json() == payload

    saved = json.loads(
        (tmp_path / "output" / "projects" / "42" / "edit_draft.json").read_text()
    )
    assert saved == payload


def test_post_wrapper_chip_draft_then_get_returns_saved(
    client: TestClient,
    tmp_path: Path,
):
    payload = {
        "wrapperChips": {
            "@s9/visual": "make this darker",
            "@s11/subtitle": "shorten this line",
        },
    }
    resp = client.post("/api/jobs/42/draft", json=payload)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    resp2 = client.get("/api/jobs/42/draft")
    assert resp2.status_code == 200
    assert resp2.json() == payload

    saved = json.loads(
        (tmp_path / "output" / "projects" / "42" / "edit_draft.json").read_text()
    )
    assert saved == payload


def test_post_draft_overwrites(client: TestClient):
    client.post("/api/jobs/42/draft", json={"tokens": ["@s1"], "instruction": "first"})
    client.post("/api/jobs/42/draft", json={"tokens": ["@s2"], "instruction": "second"})
    resp = client.get("/api/jobs/42/draft")
    assert resp.json() == {"tokens": ["@s2"], "instruction": "second"}


def test_delete_draft_removes_file(client: TestClient, tmp_path: Path):
    client.post("/api/jobs/42/draft", json={"tokens": ["@s9"], "instruction": "x"})
    assert (tmp_path / "output" / "projects" / "42" / "edit_draft.json").exists()
    resp = client.delete("/api/jobs/42/draft")
    assert resp.status_code == 200
    assert not (tmp_path / "output" / "projects" / "42" / "edit_draft.json").exists()
    resp2 = client.get("/api/jobs/42/draft")
    assert resp2.json() == {"tokens": [], "instruction": ""}


def test_delete_draft_noop_when_absent(client: TestClient):
    resp = client.delete("/api/jobs/42/draft")
    assert resp.status_code == 200


def test_post_draft_404_when_project_missing(client: TestClient):
    resp = client.post(
        "/api/jobs/nope/draft",
        json={"tokens": [], "instruction": "x"},
    )
    assert resp.status_code == 404


def test_post_draft_rejects_oversize_payload(client: TestClient):
    huge = "x" * (64 * 1024 + 1)
    resp = client.post(
        "/api/jobs/42/draft",
        json={"tokens": [], "instruction": huge},
    )
    assert resp.status_code == 413
