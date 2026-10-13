"""`pipeline toon …` — validate, render and review own-show 2.5D scenes."""
from __future__ import annotations

import math
from pathlib import Path

import typer
import yaml
from PIL import Image

toon_app = typer.Typer(help="Own-show 2.5D doodle animation: validate, render, model sheets.")
_REPO = Path(__file__).resolve().parents[2]


def _load(scene: str, narration: str | None, duration: float | None):
    """Bank + validated scene, or ERROR lines and exit 1 — never a traceback."""
    from toon.bank import load_bank
    from toon.scene import NeedsNarration, SceneError, load_scene, read_scene

    try:
        bank = load_bank()
        return bank, load_scene(read_scene(scene), bank, narration=narration, duration=duration)
    except (ValueError, yaml.YAMLError) as exc:  # SceneError and BankError are ValueErrors
        # A problem's own text may hold "; ", so a SceneError prints its problems one by one.
        lines = ([f"{exc.source}: {p}" if exc.source else p for p in exc.problems]
                 if isinstance(exc, SceneError) else str(exc).split("; "))
        for line in lines:
            typer.echo(f"ERROR  {line}")
        if isinstance(exc, NeedsNarration):
            typer.echo("ERROR  this scene is anchored to sentences: pass --narration TEXT "
                       "(and --duration SEC when the scene has no duration)")
        raise typer.Exit(code=1) from exc


@toon_app.command("validate")
def validate(scene: str = typer.Argument(..., help="scene id or path to a scene YAML"),
             narration: str = typer.Option(None, help="the narration: resolves sentence anchors, prints the split"),
             duration: float = typer.Option(None, help="narration length in seconds (default: the scene's duration)"),
             ) -> None:
    """Load a scene against the bank. With --narration, print how its sentences and shots time
    out; warnings print as WARN lines (exit 0), errors as ERROR lines (exit 1)."""
    from toon.scene import (
        anchor_text,
        drift_warnings,
        scene_warnings,
        sentence_starts,
        split_sentences,
    )

    _, s = _load(scene, narration, duration)
    typer.echo(f"ok  {s.id}: {len(s.shots)} shots, {sum(len(sh.beats) for sh in s.shots)} beats")
    if narration and s.duration is None:
        typer.echo("WARN  the scene has no duration: pass --duration SEC (the narration's length) "
                   "to time its sentences and shots")
    elif narration:
        typer.echo(f"sentences (narration {s.duration:.2f} s):")
        for n, (t, text) in enumerate(zip(sentence_starts(narration, s.duration), split_sentences(narration),
                                          strict=True), 1):
            typer.echo(f"  {n:>3}  {t:6.2f}s  {text}")
    # each shot's window at this narration, so a retake's margin shows before recording
    ends = [float(sh.at) for sh in s.shots[1:]] + [s.duration if s.duration is not None else math.inf]
    typer.echo("shots (start – end, as authored):")
    for i, (sh, at, end) in enumerate(zip(s.shots, s.authored_shot_starts, ends, strict=True), 1):
        until = f"{end:6.2f}" if math.isfinite(end) else "   end"
        typer.echo(f"  {i:>3}  {float(sh.at):6.2f} – {until} s  {anchor_text(at):<24}  {sh.set} / {sh.camera}")
    if s.duration is not None:
        for w in scene_warnings(s, s.duration) + drift_warnings(s, s.duration):
            typer.echo(f"WARN  {w}")


@toon_app.command("render")
def render(scene: str = typer.Argument(...), out: Path = typer.Option(None),
           width: int = typer.Option(1920), height: int = typer.Option(1080),
           stills: str = typer.Option("", help="comma-separated times → PNGs instead of an mp4"),
           narration: str = typer.Option(None), duration: float = typer.Option(None)) -> None:
    from toon.render import frame, render_clip

    bank, s = _load(scene, narration, duration)
    out = out or _REPO / "output" / "own-show" / "scenes" / s.id
    out.mkdir(parents=True, exist_ok=True)
    if stills:
        for t in (float(x) for x in stills.split(",")):
            Image.fromarray(frame(s, bank, t, width, height)[..., [2, 1, 0]]).save(out / f"{s.id}_{t:05.2f}.png")
        typer.echo(f"stills → {out}")
        return
    if s.duration is None:
        typer.echo("ERROR  scene has no duration; pass --duration")
        raise typer.Exit(code=1)
    typer.echo(render_clip(s, bank, out / f"{s.id}.mp4", s.duration, width, height))


@toon_app.command("sheet")
def sheet(character: str = typer.Argument(...), out: Path = typer.Option(None)) -> None:
    from toon.bank import load_bank
    from toon.sheets import model_sheet

    out = out or _REPO / "output" / "own-show" / "bank"
    typer.echo(model_sheet(load_bank(), character, out))
