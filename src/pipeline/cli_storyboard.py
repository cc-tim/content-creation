from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from pipeline.config import PipelineConfig
from pipeline.storyboard import Storyboard
from pipeline.voices.base import VoiceProfile
from pipeline.voices.registry import VoiceRegistry

storyboard_app = typer.Typer(help="Inspect and edit storyboard.json.")
_console = Console()

_RECORDING_EXTS = (".wav", ".mp3", ".m4a")

_ALLOWED_FIELDS = {"narration", "narration_est_sec", "pause_after_sec", "section"}
_ALLOWED_SECTIONS = {
    "hook",
    "context",
    "rising",
    "climax",
    "aftermath",
    "analysis",
    "content",
    "punchline",
}


def _load_storyboard(work_dir: Path) -> Storyboard:
    path = work_dir / "storyboard.json"
    if not path.exists():
        raise typer.BadParameter(
            f"no storyboard.json at {path}; pass --work-dir pointing to a project directory"
        )
    return Storyboard.load(path)


def _find_recording(rec_dir: Path, scene_id: str) -> Path | None:
    for ext in _RECORDING_EXTS:
        p = rec_dir / f"{scene_id}{ext}"
        if p.exists():
            return p
    return None


def _classify(rec_dir: Path, scene_id: str, live_text: str) -> tuple[str, str]:
    src = _find_recording(rec_dir, scene_id)
    if src is None:
        return "missing", ""
    snapshot = rec_dir / f"{scene_id}.txt"
    if not snapshot.exists():
        return "stale", "no snapshot"
    recorded = snapshot.read_text(encoding="utf-8").strip()
    if recorded != live_text.strip():
        return "stale", "text changed since record"
    return "recorded", ""


def _resolve_voice_profile(registry: VoiceRegistry, voice_id: str | None) -> VoiceProfile:
    if voice_id is not None:
        return registry.get(voice_id)
    prerecorded = [p for p in registry.list() if p.engine == "prerecorded"]
    if len(prerecorded) == 1:
        return prerecorded[0]
    if not prerecorded:
        raise typer.BadParameter("no prerecorded voice in registry; pass --voice <id>")
    raise typer.BadParameter("multiple prerecorded voices in registry; pass --voice <id>")


def _coerce_value(field: str, raw: str) -> object:
    if field in {"narration_est_sec", "pause_after_sec"}:
        try:
            return float(raw)
        except ValueError as exc:
            raise typer.BadParameter(f"{field} must be a number, got {raw!r}") from exc
    if field == "section":
        if raw not in _ALLOWED_SECTIONS:
            raise typer.BadParameter(
                f"section must be one of {sorted(_ALLOWED_SECTIONS)}, got {raw!r}"
            )
        return raw
    return raw  # narration: free text


@storyboard_app.command("show")
def show(
    scene: str | None = typer.Option(None, "--scene", help="Scene id to focus"),
    work_dir: Path = typer.Option(Path("."), "--work-dir"),
) -> None:
    """List scenes or print one scene's full narration."""
    sb = _load_storyboard(work_dir)

    if scene is None:
        table = Table(title=f"Storyboard: {len(sb.scenes)} scenes")
        table.add_column("id")
        table.add_column("section")
        table.add_column("narration (first 60)")
        table.add_column("est_sec", justify="right")
        table.add_column("pause", justify="right")
        for s in sb.scenes:
            preview = s.narration[:60] + ("…" if len(s.narration) > 60 else "")
            table.add_row(
                s.id,
                s.section,
                preview,
                f"{s.narration_est_sec:.1f}",
                f"{s.pause_after_sec:.1f}",
            )
        _console.print(table)
        return

    match = sb.get_scene(scene)
    if match is None:
        typer.echo(f"scene '{scene}' not found")
        raise typer.Exit(code=1)
    _console.print(
        f"[bold]{match.id}[/bold]  section={match.section}  "
        f"est_sec={match.narration_est_sec}  pause={match.pause_after_sec}"
    )
    if match.visual:
        _console.print(f"visual: {match.visual.get('type', '?')}")
    if match.overlay:
        _console.print(f"overlay: {match.overlay.get('type', '?')}")
    _console.print()
    _console.print(match.narration)


@storyboard_app.command("recordings")
def recordings(
    voice: str | None = typer.Option(None, "--voice", help="Voice id"),
    work_dir: Path = typer.Option(Path("."), "--work-dir"),
) -> None:
    """Show per-scene recording status for a prerecorded voice."""
    sb = _load_storyboard(work_dir)
    cfg = PipelineConfig()
    registry = VoiceRegistry(cfg.VOICES_DIR)
    profile = _resolve_voice_profile(registry, voice)
    if profile.engine != "prerecorded":
        raise typer.BadParameter(
            f"voice '{profile.id}' is engine '{profile.engine}', not 'prerecorded'"
        )
    rec_dir = Path(profile.params["recording_dir"])

    table = Table(title=f"Recordings for {profile.id}  ({rec_dir})")
    table.add_column("scene_id")
    table.add_column("status")
    table.add_column("note")

    known_ids: set[str] = set()
    for scene in sb.scenes:
        known_ids.add(scene.id)
        status, note = _classify(rec_dir, scene.id, scene.narration)
        table.add_row(scene.id, status, note)
    _console.print(table)

    if not rec_dir.exists():
        return
    orphans: list[str] = []
    for f in sorted(rec_dir.iterdir()):
        if f.suffix not in _RECORDING_EXTS:
            continue
        if f.stem not in known_ids:
            orphans.append(f.name)
    if orphans:
        _console.print("\n[yellow]Orphans (no matching scene):[/yellow]")
        for name in orphans:
            _console.print(f"  - {name}")


@storyboard_app.command("set")
def set_field(
    scene_id: str = typer.Argument(...),
    assignment: str = typer.Argument(..., help="field=value"),
    work_dir: Path = typer.Option(Path("."), "--work-dir"),
) -> None:
    """Set a safe field on a scene. Use storyboard.json directly for visual/overlay/compartment."""
    if "=" not in assignment:
        raise typer.BadParameter("expected field=value, got " + assignment)
    field, raw_value = assignment.split("=", 1)
    if field not in _ALLOWED_FIELDS:
        raise typer.BadParameter(
            f"'{field}' is not a safe field; allowed: {sorted(_ALLOWED_FIELDS)}. "
            "Edit storyboard.json directly for complex fields."
        )
    value = _coerce_value(field, raw_value)

    sb = _load_storyboard(work_dir)
    scene = sb.get_scene(scene_id)
    if scene is None:
        raise typer.BadParameter(f"scene '{scene_id}' not found")
    setattr(scene, field, value)

    sb_path = work_dir / "storyboard.json"
    sb.save(sb_path)
    typer.echo(f"updated {scene_id}.{field}")
