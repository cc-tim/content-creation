"""`pipeline toon …` — validate, render and review own-show 2.5D scenes."""
from __future__ import annotations

from pathlib import Path

import typer
from PIL import Image

toon_app = typer.Typer(help="Own-show 2.5D doodle animation: validate, render, model sheets.")
_REPO = Path(__file__).resolve().parents[2]


def _load(scene: str, narration: str | None, duration: float | None):
    from toon.bank import load_bank
    from toon.scene import load_scene, read_scene

    bank = load_bank()
    return bank, load_scene(read_scene(scene), bank, narration=narration, duration=duration)


@toon_app.command("validate")
def validate(scene: str = typer.Argument(..., help="scene id or path to a scene YAML")) -> None:
    try:
        _, s = _load(scene, None, None)
    except ValueError as exc:
        for line in str(exc).split("; "):
            typer.echo(f"ERROR  {line}")
        raise typer.Exit(code=1) from exc
    typer.echo(f"ok  {s.id}: {len(s.shots)} shots, {sum(len(sh.beats) for sh in s.shots)} beats")


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
