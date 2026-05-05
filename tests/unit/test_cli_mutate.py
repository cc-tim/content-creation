from __future__ import annotations

from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

import pipeline.cli_mutate as cli_mutate
from pipeline.cli_mutate import mutate_app


@pytest.fixture
def fake_dashboard(monkeypatch: pytest.MonkeyPatch):
    """Replace httpx.post / httpx.get with a recorder that returns canned bodies."""

    class FakeRouter:
        def __init__(self) -> None:
            self.posts: list[tuple[str, dict]] = []
            self.gets: list[str] = []
            self.next_post_response: dict[str, Any] = {
                "status": "applied",
                "mutation_id": "m1",
                "message": "ok",
            }
            self.next_get_responses: list[dict[str, Any]] = []

        def post(self, url: str, *, json: dict, timeout: float | None = None) -> httpx.Response:
            self.posts.append((url, json))
            return httpx.Response(
                status_code=200,
                json=self.next_post_response,
                headers={"content-type": "application/json"},
            )

        def get(self, url: str, *, timeout: float | None = None) -> httpx.Response:
            self.gets.append(url)
            body = (
                self.next_get_responses.pop(0)
                if self.next_get_responses
                else {"status": "applied", "mutation_id": "m1", "message": "ok"}
            )
            return httpx.Response(
                status_code=200,
                json=body,
                headers={"content-type": "application/json"},
            )

    fake = FakeRouter()
    monkeypatch.setattr(cli_mutate, "_http_post", fake.post)
    monkeypatch.setattr(cli_mutate, "_http_get", fake.get)
    monkeypatch.setenv("PIPELINE_DASHBOARD_BASE_URL", "http://test.local")
    monkeypatch.setenv("PIPELINE_JOB_ID", "job-xyz")
    return fake


def test_apply_posts_proposal_and_exits_zero_when_applied(fake_dashboard):
    fake_dashboard.next_post_response = {
        "status": "applied",
        "mutation_id": "m1",
        "message": "subtitle s1: set",
    }
    runner = CliRunner()
    result = runner.invoke(mutate_app, ["apply", "subtitle set", "--scene", "s1", "--text", "hello"])
    assert result.exit_code == 0, result.output
    assert "subtitle s1: set" in result.output

    url, body = fake_dashboard.posts[0]
    assert url == "http://test.local/api/mutations/job-xyz/propose"
    assert body["verb"] == "subtitle set"
    assert body["args"] == {"scene": "s1", "text": "hello"}
    assert body["job_id"] == "job-xyz"


def test_apply_long_polls_when_proposed_then_returns_after_apply(fake_dashboard):
    fake_dashboard.next_post_response = {
        "status": "proposed",
        "mutation_id": "m99",
        "proposal_message": "Awaiting approval",
    }
    fake_dashboard.next_get_responses = [
        {"status": "applied", "mutation_id": "m99", "message": "image s9 regenerated"},
    ]
    runner = CliRunner()
    result = runner.invoke(
        mutate_app,
        ["apply", "image regen", "--scene", "s9", "--prompt", "x", "--tier", "draft"],
    )
    assert result.exit_code == 0, result.output
    assert "image s9 regenerated" in result.output

    assert len(fake_dashboard.gets) == 1
    assert "/api/mutations/m99/await" in fake_dashboard.gets[0]


def test_apply_returns_exit_1_when_cancelled(fake_dashboard):
    fake_dashboard.next_post_response = {
        "status": "proposed",
        "mutation_id": "m99",
        "proposal_message": "Awaiting approval",
    }
    fake_dashboard.next_get_responses = [
        {"status": "cancelled", "mutation_id": "m99", "message": "user cancelled"},
    ]
    runner = CliRunner()
    result = runner.invoke(mutate_app, ["apply", "subtitle set", "--scene", "s1", "--text", "x"])
    assert result.exit_code == 1
    assert "cancelled" in result.output.lower()


def test_apply_returns_exit_2_when_failed(fake_dashboard):
    fake_dashboard.next_post_response = {
        "status": "failed",
        "mutation_id": None,
        "message": "scene 's99' not found",
    }
    runner = CliRunner()
    result = runner.invoke(mutate_app, ["apply", "subtitle set", "--scene", "s99", "--text", "x"])
    assert result.exit_code == 2
    assert "s99" in result.output


def test_apply_errors_when_job_id_missing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("PIPELINE_JOB_ID", raising=False)
    monkeypatch.delenv("PIPELINE_DASHBOARD_BASE_URL", raising=False)
    runner = CliRunner()
    result = runner.invoke(mutate_app, ["apply", "subtitle set", "--scene", "s1", "--text", "x"])
    assert result.exit_code != 0
    assert "PIPELINE_JOB_ID" in result.output


def test_apply_passes_explicit_job_id_flag_over_env(fake_dashboard):
    runner = CliRunner()
    runner.invoke(
        mutate_app,
        [
            "apply",
            "subtitle set",
            "--job-id",
            "explicit-id",
            "--scene",
            "s1",
            "--text",
            "x",
        ],
    )
    url, body = fake_dashboard.posts[0]
    assert "explicit-id" in url
    assert body["job_id"] == "explicit-id"
