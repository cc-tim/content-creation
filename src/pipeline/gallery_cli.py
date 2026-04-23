# src/pipeline/gallery_cli.py
"""CLI subcommand: `pipeline gallery search`."""
from __future__ import annotations

import typer

from pipeline.utils.gallery import search_gallery

gallery_app = typer.Typer(name="gallery", help="Asset gallery management")


@gallery_app.command("search")
def gallery_search(
    query: str = typer.Argument(..., help="Search query (space-separated keywords)"),
    niche: str | None = typer.Option(None, "--niche", help="Filter by niche (e.g. bodycam)"),
    asset_type: str | None = typer.Option(
        None, "--type", help="Asset type: image or clip"
    ),
) -> None:
    """Search gallery for an asset. Falls through tiers: local → Pexels → Pixabay → generate."""
    terms = query.split()
    result = search_gallery(terms, niche=niche, asset_type=asset_type)

    if result.tier == "generate":
        typer.echo(f'tier=generate  suggested_prompt="{result.suggested_prompt}"')
    else:
        entry = result.entry
        assert entry is not None
        tags_str = ",".join(entry.tags)
        typer.echo(
            f"tier={result.tier:<10} score=matched  {entry.path}  tags=[{tags_str}]"
        )
