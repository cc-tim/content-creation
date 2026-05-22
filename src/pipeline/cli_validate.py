"""pipeline validate — re-runs the storyboard validator on a saved project.

Wraps `pipeline.director.storyboard_validator.format_visual_decision_table`
+ `validate_storyboard` so an edited storyboard can be re-checked without
rerunning `direct`. Exit codes match lint convention:

  0 — clean
  1 — load failure (missing project / missing storyboard / bad CLI usage)
  2 — validation errors found
"""
from __future__ import annotations

from pathlib import Path

import typer

from pipeline.config import PipelineConfig

validate_app = typer.Typer(help="Re-run the storyboard validator on a saved project.")


def _output_dir() -> Path:
    """Resolve OUTPUT_DIR at call time (env-overridable in tests)."""
    return PipelineConfig().OUTPUT_DIR


def _project_dir(project_id: str) -> Path:
    return _output_dir() / "projects" / project_id


def _discover_storyboard(pdir: Path, locale: str | None) -> Path | None:
    """Find the storyboard file to validate.

    Order of resolution:
    - Explicit ``--locale`` → ``storyboard_<locale>.json`` if it exists.
    - Otherwise prefer ``storyboard.json`` (canonical name used by compose).
    - Otherwise, if exactly one ``storyboard_*.json`` exists, use it.
    - If multiple locale files exist and no override, return None (caller
      raises with a "--locale required" message).
    - If nothing matches, return None (caller raises "no storyboard").
    """
    if locale is not None:
        candidate = pdir / f"storyboard_{locale}.json"
        return candidate if candidate.exists() else None

    canonical = pdir / "storyboard.json"
    if canonical.exists():
        return canonical

    locale_files = sorted(pdir.glob("storyboard_*.json"))
    if len(locale_files) == 1:
        return locale_files[0]
    if len(locale_files) > 1:
        return None  # signal "multiple, need --locale"
    return None  # signal "no storyboard at all"


@validate_app.callback(invoke_without_command=True)
def run(
    project_id: str = typer.Option(
        ..., "--project-id", help="Project ID (folder name under output/projects/)"
    ),
    locale: str | None = typer.Option(
        None,
        "--locale",
        help="Locale suffix when multiple storyboard_<locale>.json exist.",
    ),
) -> None:
    """Validate the saved storyboard for a project and print the decision table."""
    pdir = _project_dir(project_id)
    if not pdir.exists():
        typer.echo(f"Project not found: {pdir}", err=True)
        raise typer.Exit(1)

    sb_path = _discover_storyboard(pdir, locale)
    if sb_path is None:
        if locale is not None:
            candidate = pdir / f"storyboard_{locale}.json"
            typer.echo(f"Storyboard not found: {candidate}", err=True)
            raise typer.Exit(1)
        # Distinguish "multiple, need --locale" from "no storyboard at all"
        locale_files = sorted(pdir.glob("storyboard_*.json"))
        if len(locale_files) > 1:
            names = ", ".join(p.name for p in locale_files)
            typer.echo(
                f"Multiple storyboard files in {pdir}: {names}\n"
                f"Pass --locale <code> to pick one.",
                err=True,
            )
        else:
            typer.echo(f"No storyboard file in {pdir}.", err=True)
        raise typer.Exit(1)

    from pipeline.director.storyboard_validator import (
        format_visual_decision_table,
        validate_storyboard,
    )
    from pipeline.storyboard import Storyboard

    sb = Storyboard.load(sb_path)
    typer.echo(format_visual_decision_table(sb, pdir, project_id=project_id))

    errors = [
        issue for issue in validate_storyboard(sb, pdir) if issue.severity == "error"
    ]
    if errors:
        for err in errors:
            typer.echo(f"  {err.scene_id} {err.field}: {err.issue} Fix: {err.suggested_fix}")
        raise typer.Exit(2)
