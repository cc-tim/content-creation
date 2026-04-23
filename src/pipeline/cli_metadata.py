from __future__ import annotations

import json
from pathlib import Path

import typer
from pydantic import ValidationError
from rich.console import Console

from pipeline.publish.metadata import Metadata, load_metadata

metadata_app = typer.Typer(help="Inspect and edit metadata.json.")
_console = Console()

_ALLOWED_FIELDS = {
    "title",
    "description",
    "tags",
    "category_id",
    "default_language",
    "default_audio_language",
    "made_for_kids",
    "altered_or_synthetic_content",
}


def _metadata_path(work_dir: Path) -> Path:
    path = work_dir / "metadata.json"
    if not path.exists():
        raise typer.BadParameter(f"no metadata.json at {path}")
    return path


def _coerce_value(field: str, raw: str) -> object:
    if field == "tags":
        try:
            v = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise typer.BadParameter(f"tags must be JSON list, got {raw!r}") from exc
        if not isinstance(v, list):
            raise typer.BadParameter("tags must be a JSON list")
        return v
    if field == "category_id":
        try:
            return int(raw)
        except ValueError as exc:
            raise typer.BadParameter(f"category_id must be int, got {raw!r}") from exc
    if field == "made_for_kids":
        if raw.lower() in ("true", "1", "yes"):
            return True
        if raw.lower() in ("false", "0", "no"):
            return False
        raise typer.BadParameter("made_for_kids must be true|false")
    return raw


@metadata_app.command("show")
def show(
    work_dir: Path = typer.Option(Path("."), "--work-dir"),
) -> None:
    """Pretty-print metadata.json."""
    path = _metadata_path(work_dir)
    raw = json.loads(path.read_text(encoding="utf-8"))
    for key in (
        "title",
        "description",
        "tags",
        "category_id",
        "default_language",
        "default_audio_language",
        "made_for_kids",
        "altered_or_synthetic_content",
    ):
        if key in raw:
            _console.print(f"[bold]{key}[/bold]: {raw[key]}")
    for key in sorted(k for k in raw if k.startswith("_")):
        _console.print(f"[dim]{key}: {raw[key]}[/dim]")


@metadata_app.command("set")
def set_field(
    assignment: str = typer.Argument(..., help="field=value"),
    work_dir: Path = typer.Option(Path("."), "--work-dir"),
) -> None:
    """Set a safe field on metadata.json."""
    if "=" not in assignment:
        raise typer.BadParameter("expected field=value, got " + assignment)
    field, raw = assignment.split("=", 1)
    if field not in _ALLOWED_FIELDS:
        raise typer.BadParameter(
            f"'{field}' is not a safe field; allowed: {sorted(_ALLOWED_FIELDS)}"
        )
    value = _coerce_value(field, raw)

    path = _metadata_path(work_dir)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload[field] = value

    try:
        clean = {k: v for k, v in payload.items() if not k.startswith("_")}
        Metadata(**clean)
    except ValidationError as exc:
        raise typer.BadParameter(f"validation failed: {exc}") from exc

    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    typer.echo(f"updated {field}")


@metadata_app.command("validate")
def validate(
    work_dir: Path = typer.Option(Path("."), "--work-dir"),
) -> None:
    """Validate metadata.json against Pydantic + YouTube limits."""
    path = _metadata_path(work_dir)
    try:
        load_metadata(path)
    except ValidationError as exc:
        typer.echo(f"INVALID: {exc}", err=True)
        raise typer.Exit(code=1)
    typer.echo("ok")


@metadata_app.command("regenerate")
def regenerate(
    work_dir: Path = typer.Option(Path("."), "--work-dir"),
    project_id: int | None = typer.Option(None, "--project-id"),
) -> None:
    """Re-run Claude to regenerate metadata.json. Clobbers hand edits."""
    from pipeline.knowledge import Knowledge
    from pipeline.publish.channels import load_channel_config, resolve_profile
    from pipeline.stages.base import PipelineContext
    from pipeline.stages.direct import write_metadata_for_project
    from pipeline.storyboard import Storyboard

    ctx_path = work_dir / "context.json"
    if not ctx_path.exists():
        raise typer.BadParameter(f"no context.json at {ctx_path}")
    ctx = PipelineContext.load(ctx_path)

    if not ctx.niche or ctx.niche == "none":
        raise typer.BadParameter(
            "context has no niche set; cannot route to a profile. Re-run produce with --niche NAME."
        )

    cfg = load_channel_config(Path("configs/youtube_channels.toml"))
    profile = resolve_profile(cfg, niche=ctx.niche, locale=ctx.locale, override=None)

    storyboard = Storyboard.load(ctx.storyboard_path or work_dir / "storyboard.json")
    synopsis = "\n".join(f"{s.section}: {s.narration[:120]}" for s in storyboard.scenes)

    facts: list[dict[str, str]] = []
    if ctx.knowledge_path and ctx.knowledge_path.exists():
        knowledge = Knowledge.load(ctx.knowledge_path)
        facts = [{"id": f.id, "text": f.text} for f in knowledge.facts[:10]]

    write_metadata_for_project(
        work_dir=work_dir,
        profile=profile,
        locale=ctx.locale,
        source_url=ctx.source_url,
        storyboard_synopsis=synopsis,
        knowledge_facts=facts,
        regenerate=True,
    )
    typer.echo("metadata regenerated")
