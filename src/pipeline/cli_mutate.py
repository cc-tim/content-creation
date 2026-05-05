"""Trust-gate proxy for storyboard mutations.

The agent runtime calls ``pipeline mutate apply <verb>`` instead of raw mutation
commands. This proxy forwards the mutation to the dashboard, then exits with the
dashboard's terminal status code.
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx
import typer

mutate_app = typer.Typer(name="mutate", help="Trust-gate proxy for storyboard mutations")

_DEFAULT_DASHBOARD_BASE_URL = "http://127.0.0.1:8000"
_AWAIT_POLL_TIMEOUT_SEC = 60.0
_AWAIT_TOTAL_TIMEOUT_SEC = 30 * 60


@mutate_app.callback()
def mutate_callback() -> None:
    """Trust-gate proxy for storyboard mutations."""


def _http_post(url: str, *, json: dict, timeout: float | None = None) -> httpx.Response:
    return httpx.post(url, json=json, timeout=timeout or 30.0)


def _http_get(url: str, *, timeout: float | None = None) -> httpx.Response:
    return httpx.get(url, timeout=timeout or _AWAIT_POLL_TIMEOUT_SEC)


def _resolve_base_url() -> str:
    return os.getenv("PIPELINE_DASHBOARD_BASE_URL", _DEFAULT_DASHBOARD_BASE_URL).rstrip("/")


def _resolve_job_id(explicit: str | None) -> str:
    if explicit:
        return explicit
    env = os.getenv("PIPELINE_JOB_ID")
    if not env:
        typer.echo(
            "PIPELINE_JOB_ID not set and --job-id not provided; mutate proxy needs the job context.",
            err=True,
        )
        raise typer.Exit(code=2)
    return env


@mutate_app.command("apply")
def apply_command(
    verb: str = typer.Argument(..., help="Verb name, for example 'subtitle set'"),
    job_id: str | None = typer.Option(None, "--job-id", help="Override PIPELINE_JOB_ID env"),
    scene: str | None = typer.Option(None, "--scene"),
    text: str | None = typer.Option(None, "--text"),
    prompt: str | None = typer.Option(None, "--prompt"),
    tier: str | None = typer.Option(None, "--tier"),
    from_scene: str | None = typer.Option(None, "--from"),
    to_scene: str | None = typer.Option(None, "--to"),
    style: str | None = typer.Option(None, "--style"),
    duration_sec: float | None = typer.Option(None, "--duration"),
    sfx: str | None = typer.Option(None, "--sfx"),
    engine: str | None = typer.Option(None, "--engine"),
    voice: str | None = typer.Option(None, "--voice"),
    file: str | None = typer.Option(None, "--file"),
) -> None:
    """Apply a mutation through the dashboard trust gate."""
    args: dict[str, Any] = {}
    for key, value in [
        ("scene", scene),
        ("text", text),
        ("prompt", prompt),
        ("tier", tier),
        ("from", from_scene),
        ("to", to_scene),
        ("style", style),
        ("duration_sec", duration_sec),
        ("sfx", sfx),
        ("engine", engine),
        ("voice", voice),
        ("file", file),
    ]:
        if value is not None:
            args[key] = value

    base = _resolve_base_url()
    resolved_job_id = _resolve_job_id(job_id)
    response = _http_post(
        f"{base}/api/mutations/{resolved_job_id}/propose",
        json={"job_id": resolved_job_id, "verb": verb, "args": args},
    )
    if response.status_code >= 400:
        typer.echo(f"propose failed: HTTP {response.status_code} {response.text[:200]}", err=True)
        raise typer.Exit(code=2)

    payload = response.json()
    status = payload.get("status")
    if status == "applied":
        typer.echo(payload.get("message", "applied"))
        raise typer.Exit(code=0)
    if status == "failed":
        typer.echo(payload.get("message", "mutation failed"), err=True)
        raise typer.Exit(code=2)
    if status == "proposed":
        mutation_id = payload["mutation_id"]
        if payload.get("proposal_message"):
            typer.echo(payload["proposal_message"])
        _await_proposal(base, mutation_id)
        return

    typer.echo(f"unexpected propose response: {payload!r}", err=True)
    raise typer.Exit(code=2)


def _await_proposal(base: str, mutation_id: str) -> None:
    """Long-poll until the proposal resolves to applied, cancelled, or failed."""
    deadline = time.monotonic() + _AWAIT_TOTAL_TIMEOUT_SEC
    while time.monotonic() < deadline:
        response = _http_get(f"{base}/api/mutations/{mutation_id}/await")
        if response.status_code == 504:
            continue
        if response.status_code >= 400:
            typer.echo(f"await failed: HTTP {response.status_code}", err=True)
            raise typer.Exit(code=2)

        payload = response.json()
        status = payload.get("status")
        if status == "applied":
            typer.echo(payload.get("message", "applied"))
            raise typer.Exit(code=0)
        if status == "cancelled":
            typer.echo(payload.get("message", "cancelled by user"))
            raise typer.Exit(code=1)
        if status == "failed":
            typer.echo(payload.get("message", "mutation failed"), err=True)
            raise typer.Exit(code=2)

    typer.echo("proposal timed out waiting for user decision", err=True)
    raise typer.Exit(code=2)
