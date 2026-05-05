from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from pipeline.dashboard.job_queue import EditJob, save_job
from pipeline.dashboard.mutation_runtime import MutationCoordinator
from pipeline.storyboard import Scene, Storyboard


class FakeNotifier:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def send_message(
        self,
        text: str,
        *,
        parse_mode: str = "MarkdownV2",
        reply_to_message_id: int | None = None,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.messages.append({
            "text": text,
            "parse_mode": parse_mode,
            "reply_to_message_id": reply_to_message_id,
            "reply_markup": reply_markup,
        })
        return {"message_id": 1234 + len(self.messages)}

    async def get_updates(
        self,
        *,
        offset: int | None = None,
        timeout: int = 25,
        allowed_updates: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        await _sleep_briefly()
        return []


async def _sleep_briefly() -> None:
    import asyncio

    await asyncio.sleep(0.01)


def _basic_sb() -> Storyboard:
    return Storyboard(scenes=[
        Scene(
            id="s1",
            section="content",
            narration="old subtitle",
            narration_est_sec=1.0,
            subtitle_override="old subtitle",
            visual={"prompt": "old prompt", "tier": "draft"},
        ),
    ])


def _project_with_job(tmp_path: Path, job_id: str = "job-1") -> Path:
    project_root = tmp_path / "projects" / "42"
    project_root.mkdir(parents=True)
    _basic_sb().save(project_root / "storyboard.json")
    save_job(
        project_root,
        EditJob(job_id=job_id, project_id="42", tokens=["@s1/subtitle"], instruction="edit"),
    )
    return project_root


@pytest.fixture
def app_with_fake_telegram(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _project_with_job(tmp_path)
    fake = FakeNotifier()
    monkeypatch.setattr("pipeline.notify.telegram.TelegramNotifier.from_env", lambda: fake)

    from pipeline.dashboard.server import create_app

    app = create_app(output_dir=tmp_path)
    return app, fake


def test_propose_auto_applies_small_subtitle_edit(
    app_with_fake_telegram,
    tmp_path: Path,
) -> None:
    app, fake = app_with_fake_telegram
    with TestClient(app) as client:
        response = client.post(
            "/api/mutations/job-1/propose",
            json={
                "job_id": "job-1",
                "verb": "subtitle set",
                "args": {"scene": "s1", "text": "old subtitlz"},
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "applied"
    assert body["mutation_id"]
    assert "subtitle" in body["message"]

    sb = Storyboard.load(tmp_path / "projects" / "42" / "storyboard.json")
    assert sb.get_scene("s1").subtitle_override == "old subtitlz"
    assert fake.messages[-1]["text"].startswith("[42] mutation applied")


def test_propose_returns_proposed_for_image_regen(app_with_fake_telegram) -> None:
    app, fake = app_with_fake_telegram
    with TestClient(app) as client:
        response = client.post(
            "/api/mutations/job-1/propose",
            json={
                "job_id": "job-1",
                "verb": "image regen",
                "args": {"scene": "s1", "prompt": "x", "tier": "draft"},
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "proposed"
    assert body["mutation_id"]
    assert fake.messages[-1]["reply_markup"]["inline_keyboard"][0][0]["text"] == "Apply"


def test_await_returns_terminal_after_resolve(
    app_with_fake_telegram,
    tmp_path: Path,
) -> None:
    app, _fake = app_with_fake_telegram
    with TestClient(app) as client:
        propose = client.post(
            "/api/mutations/job-1/propose",
            json={
                "job_id": "job-1",
                "verb": "image regen",
                "args": {"scene": "s1", "prompt": "new prompt", "tier": "draft"},
            },
        )
        mutation_id = propose.json()["mutation_id"]
        coord: MutationCoordinator = app.state.mutation_coordinator

        def fire() -> None:
            time.sleep(0.05)
            coord.resolve(mutation_id, decision="apply")

        threading.Thread(target=fire, daemon=True).start()
        response = client.get(f"/api/mutations/{mutation_id}/await", params={"timeout": "1.0"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "applied"
    sb = Storyboard.load(tmp_path / "projects" / "42" / "storyboard.json")
    assert sb.get_scene("s1").visual["prompt"] == "new prompt"


def test_await_returns_cancelled_after_cancel_resolution(app_with_fake_telegram) -> None:
    app, _fake = app_with_fake_telegram
    with TestClient(app) as client:
        propose = client.post(
            "/api/mutations/job-1/propose",
            json={
                "job_id": "job-1",
                "verb": "image regen",
                "args": {"scene": "s1", "prompt": "x", "tier": "draft"},
            },
        )
        mutation_id = propose.json()["mutation_id"]
        coord: MutationCoordinator = app.state.mutation_coordinator
        coord.resolve(mutation_id, decision="cancel")

        response = client.get(f"/api/mutations/{mutation_id}/await", params={"timeout": "1.0"})

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_await_returns_504_on_server_side_timeout(app_with_fake_telegram) -> None:
    app, _fake = app_with_fake_telegram
    with TestClient(app) as client:
        propose = client.post(
            "/api/mutations/job-1/propose",
            json={
                "job_id": "job-1",
                "verb": "image regen",
                "args": {"scene": "s1", "prompt": "x", "tier": "draft"},
            },
        )
        mutation_id = propose.json()["mutation_id"]
        response = client.get(f"/api/mutations/{mutation_id}/await", params={"timeout": "0.05"})
        assert response.status_code == 504

        coord: MutationCoordinator = app.state.mutation_coordinator
        coord.resolve(mutation_id, decision="cancel")
        retry = client.get(f"/api/mutations/{mutation_id}/await", params={"timeout": "1.0"})

    assert retry.status_code == 200
    assert retry.json()["status"] == "cancelled"


def test_await_unknown_mutation_id_returns_404(app_with_fake_telegram) -> None:
    app, _fake = app_with_fake_telegram
    with TestClient(app) as client:
        response = client.get("/api/mutations/does-not-exist/await", params={"timeout": "0.05"})
    assert response.status_code == 404


def test_propose_unknown_job_returns_404(app_with_fake_telegram) -> None:
    app, _fake = app_with_fake_telegram
    with TestClient(app) as client:
        response = client.post(
            "/api/mutations/job-99/propose",
            json={
                "job_id": "job-99",
                "verb": "subtitle set",
                "args": {"scene": "s1", "text": "x"},
            },
        )
    assert response.status_code == 404


def test_propose_rejects_path_body_job_mismatch(app_with_fake_telegram) -> None:
    app, _fake = app_with_fake_telegram
    with TestClient(app) as client:
        response = client.post(
            "/api/mutations/job-1/propose",
            json={
                "job_id": "job-2",
                "verb": "subtitle set",
                "args": {"scene": "s1", "text": "x"},
            },
        )
    assert response.status_code == 400


def test_propose_requires_storyboard_for_resolved_job(
    app_with_fake_telegram,
    tmp_path: Path,
) -> None:
    app, _fake = app_with_fake_telegram
    project_root = tmp_path / "projects" / "42"
    (project_root / "storyboard.json").unlink()

    with TestClient(app) as client:
        response = client.post(
            "/api/mutations/job-1/propose",
            json={
                "job_id": "job-1",
                "verb": "subtitle set",
                "args": {"scene": "s1", "text": "x"},
            },
        )
    assert response.status_code == 409


def test_auto_apply_writes_revertable_session_entry(
    app_with_fake_telegram,
    tmp_path: Path,
) -> None:
    app, _fake = app_with_fake_telegram
    with TestClient(app) as client:
        response = client.post(
            "/api/mutations/job-1/propose",
            json={
                "job_id": "job-1",
                "verb": "subtitle set",
                "args": {"scene": "s1", "text": "old subtitlz"},
            },
        )
    assert response.status_code == 200

    rows = json.loads((tmp_path / "projects" / "42" / "sessions.json").read_text(encoding="utf-8"))
    assert rows[-1]["mutation_id"] == response.json()["mutation_id"]
    assert rows[-1]["revert_payload"]["verb"] == "subtitle set"
