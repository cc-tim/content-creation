from __future__ import annotations

from pathlib import Path

import typer

from pipeline.config import PipelineConfig
from pipeline.voices.base import VoiceNotFound
from pipeline.voices.registry import VoiceRegistry

voice_app = typer.Typer(help="Manage voice profiles for TTS.")


def _registry() -> VoiceRegistry:
    cfg = PipelineConfig()
    return VoiceRegistry(cfg.VOICES_DIR)


@voice_app.command("list")
def list_voices() -> None:
    """List all voice profiles in the registry."""
    registry = _registry()
    profiles = registry.list()
    if not profiles:
        typer.echo("(no voices configured)")
        raise typer.Exit()
    for p in profiles:
        label = p.display_name or p.id
        typer.echo(f"- {p.id}  [{p.engine}/{p.locale}]  {label}")


@voice_app.command("add")
def add_voice(
    id: str = typer.Option(..., "--id"),
    engine: str = typer.Option(..., "--engine", help="edge | prerecorded"),
    locale: str = typer.Option(..., "--locale"),
    reference: Path | None = typer.Option(None, "--reference"),
    reference_text: str | None = typer.Option(None, "--reference-text"),
    display_name: str | None = typer.Option(None, "--display-name"),
    param: list[str] = typer.Option([], "--param", help="key=value, repeatable"),
    recording_dir: Path | None = typer.Option(
        None,
        "--recording-dir",
        help="Directory of per-scene recordings (prerecorded engine).",
    ),
    fallback_voice: str | None = typer.Option(
        None,
        "--fallback-voice",
        help="Voice id to use when a scene recording is missing (prerecorded engine).",
    ),
) -> None:
    """Add a new voice profile to the registry."""
    params: dict[str, str] = {}
    for p in param:
        if "=" not in p:
            raise typer.BadParameter(f"--param must be key=value, got {p!r}")
        k, v = p.split("=", 1)
        params[k] = v

    if engine == "prerecorded":
        if recording_dir is None:
            raise typer.BadParameter(
                "--recording-dir is required when --engine prerecorded"
            )
        params["recording_dir"] = str(recording_dir)
        if fallback_voice is not None:
            params["fallback_voice_id"] = fallback_voice

    registry = _registry()
    entry: dict = {
        "id": id,
        "engine": engine,
        "locale": locale,
        "params": params,
    }
    if reference is not None:
        entry["reference"] = str(reference)
    if reference_text is not None:
        entry["reference_text"] = reference_text
    if display_name is not None:
        entry["display_name"] = display_name

    registry.add(entry)
    registry.save()
    typer.echo(f"added {id}")


@voice_app.command("remove")
def remove_voice(voice_id: str) -> None:
    """Remove a voice profile from the registry."""
    registry = _registry()
    try:
        registry.remove(voice_id)
    except VoiceNotFound as exc:
        raise typer.BadParameter(str(exc)) from exc
    registry.save()
    typer.echo(f"removed {voice_id}")


@voice_app.command("test")
def test_voice(
    voice_id: str,
    text: str = typer.Option("測試一二三", "--text"),
    out: Path = typer.Option(Path("voice_test.mp3"), "--out"),
) -> None:
    """Synthesize a short sample for a voice profile."""
    registry = _registry()
    engine, profile = registry.resolve(voice_id)
    engine.synthesize(text, out, profile)
    typer.echo(f"wrote {out}")
