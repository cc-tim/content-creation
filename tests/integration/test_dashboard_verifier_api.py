import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pipeline.dashboard.server import create_app


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    proj_root = tmp_path / "projects"
    proj = proj_root / "abc123"
    (proj / "source").mkdir(parents=True)
    (proj / "compose").mkdir()

    (proj / "source" / "explainer.md").write_text(
        """---
title: T
type: explainer
domain: parenting
intent: video
verbatim_lines:
  - "needle line"
required_images:
  - path: raw/parenting/x/img.jpg
sources: []
created: 2026-05-03
updated: 2026-05-03
---

# T
""",
        encoding="utf-8",
    )
    (proj / "storyboard.json").write_text(
        json.dumps({"scenes": [
            {
                "id": "s1",
                "narration": "the needle line is here",
                "visual": {"path": "raw/parenting/x/img.jpg"},
            }
        ]}),
        encoding="utf-8",
    )
    return proj_root


def test_get_verify_returns_manifest_and_items(project_dir: Path):
    client = TestClient(create_app(output_dir=project_dir))
    res = client.get("/api/verify/abc123")
    assert res.status_code == 200
    data = res.json()
    assert data["manifest"]["intent"] == "video"
    assert any(it["item_id"] == "verbatim_line:0" and it["status"] == "used" for it in data["items"])
    assert any(it["item_id"] == "required_image:0" and it["status"] == "used" for it in data["items"])
    assert data["used_count"] == 2
    assert data["missing_count"] == 0


def test_get_verify_unknown_project_returns_404(project_dir: Path):
    client = TestClient(create_app(output_dir=project_dir))
    res = client.get("/api/verify/nope")
    assert res.status_code == 404


def test_get_verify_project_without_explainer_returns_409(project_dir: Path, tmp_path: Path):
    other = tmp_path / "projects" / "noex"
    (other / "source").mkdir(parents=True)
    (other / "storyboard.json").write_text("{}", encoding="utf-8")
    client = TestClient(create_app(output_dir=tmp_path / "projects"))
    res = client.get("/api/verify/noex")
    assert res.status_code == 409
    assert "explainer" in res.json()["detail"].lower()


def test_post_skip_toggles_status(project_dir: Path):
    client = TestClient(create_app(output_dir=project_dir))

    res = client.post("/api/verify/abc123/skip", json={
        "item_id": "verbatim_line:0",
        "skipped": True,
    })
    assert res.status_code == 200

    res2 = client.get("/api/verify/abc123")
    line0 = next(it for it in res2.json()["items"] if it["item_id"] == "verbatim_line:0")
    assert line0["status"] == "user_skipped"

    client.post("/api/verify/abc123/skip", json={
        "item_id": "verbatim_line:0",
        "skipped": False,
    })
    res3 = client.get("/api/verify/abc123")
    line0_again = next(it for it in res3.json()["items"] if it["item_id"] == "verbatim_line:0")
    assert line0_again["status"] == "used"


def test_post_manual_check_marks_fact_used(project_dir: Path):
    explainer_path = project_dir / "abc123" / "source" / "explainer.md"
    text = explainer_path.read_text(encoding="utf-8")
    text = text.replace("verbatim_lines:", "key_facts:\n  - 'a stated fact'\nverbatim_lines:")
    explainer_path.write_text(text, encoding="utf-8")

    client = TestClient(create_app(output_dir=project_dir))
    res = client.post("/api/verify/abc123/manual-check", json={
        "item_id": "key_fact:0",
        "checked": True,
    })
    assert res.status_code == 200

    res2 = client.get("/api/verify/abc123")
    fact0 = next(it for it in res2.json()["items"] if it["item_id"] == "key_fact:0")
    assert fact0["status"] == "used"
