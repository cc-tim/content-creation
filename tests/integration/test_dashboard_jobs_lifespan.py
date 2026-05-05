from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pipeline.dashboard.server import create_app


@pytest.fixture(autouse=True)
def _no_telegram_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)


def test_dashboard_starts_and_jobs_endpoints_are_registered(tmp_path: Path) -> None:
    output = tmp_path / "output"
    (output / "projects" / "42").mkdir(parents=True)
    app = create_app(output)
    with TestClient(app) as client:
        response = client.post(
            "/api/jobs/42/submit",
            json={"tokens": [], "instruction": ""},
        )
        assert response.status_code == 400


def test_reload_on_startup_marks_orphan_running_as_interrupted(tmp_path: Path) -> None:
    output = tmp_path / "output"
    edit_dir = output / "projects" / "42" / "edit_jobs"
    edit_dir.mkdir(parents=True)
    sidecar = edit_dir / "orphan.json"
    sidecar.write_text(
        json.dumps({
            "job_id": "orphan",
            "project_id": "42",
            "tokens": [],
            "instruction": "x",
            "status": "running",
            "telegram_opener_id": None,
            "sub_action_results": [],
            "created_at": "2026-05-04T00:00:00",
            "started_at": "2026-05-04T00:00:01",
            "finished_at": None,
        }),
        encoding="utf-8",
    )
    app = create_app(output)
    with TestClient(app):
        pass
    after = json.loads(sidecar.read_text(encoding="utf-8"))
    assert after["status"] == "interrupted"
