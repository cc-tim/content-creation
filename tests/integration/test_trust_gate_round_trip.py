from __future__ import annotations

import asyncio
import json
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from pipeline.dashboard.job_queue import EditJob, save_job
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
            "kind": "message",
            "text": text,
            "parse_mode": parse_mode,
            "reply_to_message_id": reply_to_message_id,
            "reply_markup": reply_markup,
        })
        return {"message_id": 100 + len(self.messages)}

    def send_photo(
        self,
        path: Path,
        *,
        caption: str | None = None,
        reply_markup: dict[str, Any] | None = None,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        self.messages.append({
            "kind": "photo",
            "path": str(path),
            "caption": caption,
            "reply_markup": reply_markup,
        })
        return {"message_id": 100 + len(self.messages)}

    def send_video(
        self,
        path: Path,
        *,
        caption: str | None = None,
        reply_markup: dict[str, Any] | None = None,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        self.messages.append({
            "kind": "video",
            "path": str(path),
            "caption": caption,
            "reply_markup": reply_markup,
        })
        return {"message_id": 100 + len(self.messages)}

    def edit_message_text(self, **_kwargs: Any) -> dict[str, Any]:
        return {}

    async def get_updates(self, **_kwargs: Any) -> list[dict[str, Any]]:
        await asyncio.sleep(0.01)
        return []


@pytest.fixture
def app_with_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    project = tmp_path / "projects" / "42"
    project.mkdir(parents=True)
    Storyboard(scenes=[
        Scene(
            id="s1",
            section="content",
            narration="ORIGINAL",
            narration_est_sec=1.0,
            subtitle_override="ORIGINAL",
            visual={"prompt": "old prompt", "tier": "draft"},
        ),
    ]).save(project / "storyboard.json")
    for job_id in ("auto-job", "apply-job", "cancel-job", "revert-job"):
        save_job(project, EditJob(job_id=job_id, project_id="42", tokens=[], instruction=job_id))

    fake = FakeNotifier()
    monkeypatch.setattr("pipeline.notify.telegram.TelegramNotifier.from_env", lambda: fake)

    from pipeline.dashboard.server import create_app

    app = create_app(output_dir=tmp_path)
    return app, fake, project


def test_auto_apply_subtitle_edit_lands_immediately_and_sends_revert(app_with_project) -> None:
    app, fake, project = app_with_project
    with TestClient(app) as client:
        response = client.post(
            "/api/mutations/auto-job/propose",
            json={
                "job_id": "auto-job",
                "verb": "subtitle set",
                "args": {"scene": "s1", "text": "ORIGINAJ"},
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "applied"
    assert body["mutation_id"]
    assert Storyboard.load(project / "storyboard.json").get_scene("s1").subtitle_override == "ORIGINAJ"
    assert any("Revert" in json.dumps(m.get("reply_markup"), ensure_ascii=False) for m in fake.messages)


def test_propose_image_regen_then_apply_via_callback(app_with_project) -> None:
    app, _fake, project = app_with_project
    with TestClient(app) as client:
        propose = client.post(
            "/api/mutations/apply-job/propose",
            json={
                "job_id": "apply-job",
                "verb": "image regen",
                "args": {"scene": "s1", "prompt": "new prompt", "tier": "production"},
            },
        )
        assert propose.status_code == 200
        mutation_id = propose.json()["mutation_id"]

        def fire_apply() -> None:
            time.sleep(0.05)
            asyncio.run(app.state.job_queue.handle_callback_query({
                "data": f"apply:42:{mutation_id}",
            }))

        threading.Thread(target=fire_apply, daemon=True).start()
        awaited = client.get(f"/api/mutations/{mutation_id}/await", params={"timeout": "2.0"})

    assert awaited.status_code == 200
    assert awaited.json()["status"] == "applied"
    assert Storyboard.load(project / "storyboard.json").get_scene("s1").visual["prompt"] == "new prompt"


def test_propose_image_regen_then_cancel_does_not_mutate(app_with_project) -> None:
    app, _fake, project = app_with_project
    with TestClient(app) as client:
        propose = client.post(
            "/api/mutations/cancel-job/propose",
            json={
                "job_id": "cancel-job",
                "verb": "image regen",
                "args": {"scene": "s1", "prompt": "should not land", "tier": "draft"},
            },
        )
        assert propose.status_code == 200
        mutation_id = propose.json()["mutation_id"]
        asyncio.run(app.state.job_queue.handle_callback_query({
            "data": f"cancel_proposal:42:{mutation_id}",
        }))
        awaited = client.get(f"/api/mutations/{mutation_id}/await", params={"timeout": "2.0"})

    assert awaited.status_code == 200
    assert awaited.json()["status"] == "cancelled"
    assert Storyboard.load(project / "storyboard.json").get_scene("s1").visual["prompt"] == "old prompt"


def test_full_revert_flow_restores_storyboard(app_with_project) -> None:
    app, _fake, project = app_with_project
    with TestClient(app) as client:
        edit = client.post(
            "/api/mutations/revert-job/propose",
            json={
                "job_id": "revert-job",
                "verb": "subtitle set",
                "args": {"scene": "s1", "text": "ORIGINAJ"},
            },
        )
        assert edit.status_code == 200
        mutation_id = edit.json()["mutation_id"]

        recent = client.get("/api/projects/42/recent-mutations")
        assert recent.status_code == 200
        assert recent.json()[-1]["mutation_id"] == mutation_id

        revert = client.post(f"/api/jobs/42/{mutation_id}/revert")
        assert revert.status_code == 200
        for _ in range(80):
            scene = Storyboard.load(project / "storyboard.json").get_scene("s1")
            assert scene is not None
            if scene.subtitle_override == "ORIGINAL":
                break
            time.sleep(0.025)

    assert Storyboard.load(project / "storyboard.json").get_scene("s1").subtitle_override == "ORIGINAL"
