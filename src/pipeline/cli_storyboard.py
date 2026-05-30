from __future__ import annotations

import json
from datetime import datetime
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
_ALLOWED_VISUAL_FIELDS = {
    "style_modifier",
    "edit_mode",
    "edit_type",
    "edit_instruction",
    "edit_strength",
    "refit_path",
}
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


def _coerce_visual_value(field: str, raw: str) -> object:
    if field == "refit_path":
        if raw.lower() in ("null", "none", ""):
            return None
        return raw
    if field == "edit_mode":
        if raw.lower() in ("true", "1", "yes"):
            return True
        if raw.lower() in ("false", "0", "no"):
            return False
        raise typer.BadParameter(f"edit_mode must be true/false, got {raw!r}")
    if field == "edit_strength":
        try:
            v = float(raw)
        except ValueError as exc:
            raise typer.BadParameter(f"edit_strength must be a float 0.0–1.0, got {raw!r}") from exc
        if not 0.0 <= v <= 1.0:
            raise typer.BadParameter(f"edit_strength must be 0.0–1.0, got {v}")
        return v
    if field == "edit_type":
        if raw not in ("img2img", "inpaint"):
            raise typer.BadParameter(f"edit_type must be 'img2img' or 'inpaint', got {raw!r}")
        return raw
    return raw


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
    assignment: str = typer.Argument(..., help="field=value or visual.subfield=value"),
    work_dir: Path = typer.Option(Path("."), "--work-dir"),
) -> None:
    """Set a safe field on a scene. Use visual.subfield=value for visual sub-fields."""
    if "=" not in assignment:
        raise typer.BadParameter("expected field=value, got " + assignment)
    field, raw_value = assignment.split("=", 1)

    sb = _load_storyboard(work_dir)
    scene = sb.get_scene(scene_id)
    if scene is None:
        raise typer.BadParameter(f"scene '{scene_id}' not found")

    if field.startswith("visual."):
        subfield = field[len("visual."):]
        if subfield not in _ALLOWED_VISUAL_FIELDS:
            raise typer.BadParameter(
                f"'{subfield}' is not a safe visual field; allowed: {sorted(_ALLOWED_VISUAL_FIELDS)}. "
                "Edit storyboard.json directly for other fields."
            )
        value = _coerce_visual_value(subfield, raw_value)
        if scene.visual is None:
            scene.visual = {}
        if subfield == "refit_path" and value is None:
            scene.visual.pop(subfield, None)
        else:
            scene.visual[subfield] = value
        label = f"{scene_id}.visual.{subfield}"
    else:
        if field not in _ALLOWED_FIELDS:
            raise typer.BadParameter(
                f"'{field}' is not a safe field; allowed: {sorted(_ALLOWED_FIELDS)}. "
                "Edit storyboard.json directly for complex fields."
            )
        value = _coerce_value(field, raw_value)
        setattr(scene, field, value)
        label = f"{scene_id}.{field}"

    sb_path = work_dir / "storyboard.json"
    sb.save(sb_path)
    typer.echo(f"updated {label}")

    from pipeline.director.storyboard_validator import raise_for_validation_errors

    try:
        raise_for_validation_errors(sb, work_dir, scene_ids={scene_id})
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    from pipeline.session_log import SessionEntry, append_session, new_session_id
    append_session(work_dir, SessionEntry(
        session_id=new_session_id(),
        timestamp=datetime.now().isoformat(timespec="seconds"),
        command=f"storyboard set {scene_id} {field}=...",
        summary=f"storyboard set: {label}",
    ))


def migrate_storyboard_file(path: Path, primary_locale: str) -> bool:
    """Migrate one storyboard.json to the beat/narration_alt schema in place.

    Returns True if the file was changed, False if it was already migrated.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    already = "primary_locale" in data and all(
        "narration_en" not in s for s in data.get("scenes", [])
    )
    if already:
        return False
    data["primary_locale"] = data.get("primary_locale", primary_locale)
    for scene in data.get("scenes", []):
        scene.setdefault("beat", "")
        old_en = scene.pop("narration_en", None)
        if old_en is not None:
            alt = scene.setdefault("narration_alt", {})
            alt.setdefault("en", old_en)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return True


def _generate_beats(scenes: list[dict]) -> dict[str, str]:
    """Ask Claude for a one-line language-neutral beat per scene."""
    from pipeline.stages.analyze import get_anthropic_client

    client = get_anthropic_client()
    config = PipelineConfig()
    scene_lines = "\n".join(
        f"{s['id']} [{s['section']}]: {s['narration'][:200]}" for s in scenes
    )
    prompt = (
        "For each scene below, write a one-line, language-neutral 'beat' — a short "
        "statement of what the scene accomplishes in the story (its intent), NOT a "
        "summary of its wording. Return ONLY valid JSON mapping scene id to beat string.\n\n"
        f"{scene_lines}"
    )
    response = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise typer.BadParameter(f"Claude response could not be parsed as JSON: {e}") from e


def backfill_beats_file(path: Path) -> bool:
    """Fill empty `beat` fields in a storyboard via one LLM call. Returns True if changed."""
    data = json.loads(path.read_text(encoding="utf-8"))
    scenes = data.get("scenes", [])
    if not scenes or all(s.get("beat") for s in scenes):
        return False
    beats = _generate_beats(scenes)
    if not beats:
        return False
    for scene in scenes:
        if not scene.get("beat"):
            scene["beat"] = beats.get(scene["id"], "")
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return True


@storyboard_app.command("still-gate")
def still_gate(
    project_id: str = typer.Argument(..., help="Project folder under output/projects/."),
) -> None:
    """Render a still per scene + run render-truth checks BEFORE TTS/compose."""
    import tempfile

    from pipeline.director.still_gate import (
        build_contact_sheet,
        render_scene_still,
        resolve_variant,
        run_checks,
    )

    pdir = PipelineConfig().OUTPUT_DIR / "projects" / project_id
    if not pdir.exists():
        typer.echo(f"Project not found: {pdir}", err=True)
        raise typer.Exit(1)
    sb_path = pdir / "storyboard.json"
    if not sb_path.exists():
        typer.echo(f"No storyboard.json in {pdir}", err=True)
        raise typer.Exit(1)

    variant = resolve_variant(pdir)
    scenes = json.loads(sb_path.read_text())["scenes"]
    work = Path(tempfile.mkdtemp(prefix=f"stillgate_{project_id}_"))

    stills: list[tuple[str, Path, dict]] = []
    sheet_items: list[tuple[str, Path, str]] = []
    for scene in scenes:
        sid = scene.get("id", "scene")
        png = render_scene_still(scene, variant=variant, work_dir=work / sid, theme={})
        stills.append((sid, png, scene))
        vis = scene.get("visual", {})
        meta = vis.get("type", "?")
        if vis.get("path"):
            meta = f"{meta} · {Path(vis['path']).name}"
        sheet_items.append((sid, png, meta))

    sheet = build_contact_sheet(sheet_items, pdir / "still_gate_sheet.png")
    findings = run_checks(stills)

    typer.echo(f"Contact sheet: {sheet}  (variant={variant}, {len(scenes)} scenes)")
    if findings:
        for f in findings:
            typer.echo(f"  [{f.check}] {f.scene_id}: {f.message}  Fix: {f.suggested_fix}")
        raise typer.Exit(2)
    typer.echo("Still-gate clean — no render-truth findings.")


@storyboard_app.command("migrate")
def migrate(
    project_id: str = typer.Option(None, "--project-id", help="Migrate one project"),
    all_projects: bool = typer.Option(False, "--all", help="Migrate every project"),
    backfill_beats: bool = typer.Option(False, "--backfill-beats", help="Backfill empty beats via LLM"),
) -> None:
    """Migrate storyboard.json files to the beat/narration_alt schema."""
    # Check mutual exclusion
    if all_projects and project_id:
        raise typer.BadParameter("Pass --project-id or --all, not both")

    projects_root = Path("output/projects")
    if all_projects:
        targets = sorted(projects_root.glob("*/"))
    elif project_id:
        # Validate that the project exists before attempting migration
        target_path = projects_root / project_id
        if not (target_path / "storyboard.json").exists():
            raise typer.BadParameter(f"project '{project_id}' not found at {target_path}")
        targets = [target_path]
    else:
        raise typer.BadParameter("Pass --project-id <id> or --all")

    for project_dir in targets:
        sb_path = project_dir / "storyboard.json"
        ctx_path = project_dir / "context.json"
        if not sb_path.exists() or not ctx_path.exists():
            continue
        ctx = json.loads(ctx_path.read_text(encoding="utf-8"))
        primary_locale = ctx.get("locale", "zh-TW")
        changed = migrate_storyboard_file(sb_path, primary_locale=primary_locale)
        status = "migrated" if changed else "already current"
        typer.echo(f"{project_dir.name}: {status}")
        if backfill_beats and backfill_beats_file(sb_path):
            typer.echo(f"{project_dir.name}: beats backfilled")
