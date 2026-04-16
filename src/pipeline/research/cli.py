from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import typer

from pipeline.research.adapters.aap import AAPAdapter
from pipeline.research.adapters.base import Adapter
from pipeline.research.adapters.openalex import OpenAlexAdapter
from pipeline.research.config import ResearchConfig
from pipeline.research.harvester import Harvester
from pipeline.research.query import render_context_pack, rows_to_documents
from pipeline.research.store import ResearchStore

app = typer.Typer(name="research", help="Local parenting-research corpus.")


def _build_adapters(cfg: ResearchConfig, only: str | None) -> list[Adapter]:
    out: list[Adapter] = []
    if cfg.sources.openalex.enabled and only in (None, "openalex"):
        out.append(
            OpenAlexAdapter(
                mailto=cfg.sources.openalex.mailto,
                from_publication_date=cfg.sources.openalex.from_publication_date,
                sort=cfg.sources.openalex.sort,
            )
        )
    if cfg.sources.aap.enabled and only in (None, "aap"):
        out.append(
            AAPAdapter(
                user_agent=cfg.sources.aap.user_agent,
                rate_limit_rps=cfg.sources.aap.rate_limit_rps,
                max_result_pages=cfg.sources.aap.max_result_pages,
            )
        )
    return out


@app.command()
def fetch(
    topic: str = typer.Option(..., "--topic"),
    source: str | None = typer.Option(
        None, "--source", help="openalex | aap (default: all)"
    ),
    limit: int = typer.Option(10, "--limit"),
) -> None:
    """Fetch one topic from one or all configured sources."""
    cfg = ResearchConfig()
    store = ResearchStore(data_dir=cfg.data_dir)
    adapters = _build_adapters(cfg, only=source)
    if not adapters:
        raise typer.BadParameter(f"no enabled source matches --source={source}")
    results = Harvester(store=store, adapters=adapters).harvest_topic(
        topic, limit=limit
    )
    for r in results:
        suffix = f" errors={len(r.errors)}" if r.errors else ""
        typer.echo(
            f"{r.source} / {r.topic}: ok={r.ok} dup={r.duplicates}{suffix}"
        )


@app.command()
def harvest(
    limit: int | None = typer.Option(None, "--limit"),
) -> None:
    """Run all configured topics × all enabled sources."""
    cfg = ResearchConfig()
    store = ResearchStore(data_dir=cfg.data_dir)
    adapters = _build_adapters(cfg, only=None)
    if not adapters:
        raise typer.BadParameter("no sources enabled in config")
    results = Harvester(store=store, adapters=adapters).harvest(
        topics=cfg.topics,
        limit=limit or cfg.default_limit_per_topic,
    )
    for r in results:
        typer.echo(f"{r.source} / {r.topic}: ok={r.ok} dup={r.duplicates}")


@app.command(name="list")
def list_docs(
    topic: str | None = typer.Option(None, "--topic"),
    limit: int = typer.Option(50, "--limit"),
) -> None:
    """Browse the corpus."""
    cfg = ResearchConfig()
    store = ResearchStore(data_dir=cfg.data_dir)
    rows = store.list_documents(topic=topic, limit=limit)
    for row in rows:
        typer.echo(
            f"[{row['id']}] ({row['source']}) {row['published_at'] or '    '} "
            f"{row['title']}"
        )


@app.command()
def show(doc_id: int = typer.Argument(...)) -> None:
    """Show one document's details."""
    cfg = ResearchConfig()
    store = ResearchStore(data_dir=cfg.data_dir)
    cursor = store.conn.execute(
        "SELECT * FROM documents WHERE id = ?", (doc_id,)
    )
    row = cursor.fetchone()
    if row is None:
        raise typer.Exit(code=1)
    cols = [c[0] for c in cursor.description]
    rec = dict(zip(cols, row, strict=True))
    typer.echo(f"Title:   {rec['title']}")
    typer.echo(f"Source:  {rec['source']}  ({rec['external_id']})")
    typer.echo(f"URL:     {rec['url']}")
    typer.echo(f"Pub:     {rec['published_at']}")
    typer.echo(f"Abstract:\n{rec['abstract'] or '(none)'}")


@app.command()
def stats() -> None:
    """Summarize corpus size by source and topic."""
    cfg = ResearchConfig()
    store = ResearchStore(data_dir=cfg.data_dir)
    s = store.stats()
    typer.echo(f"total: {s['total']}")
    typer.echo(f"by source: {s['by_source']}")
    typer.echo(f"by topic:  {s['by_topic']}")


@app.command()
def query(
    question: str = typer.Argument(...),
    topic: str | None = typer.Option(None, "--topic"),
    limit: int = typer.Option(10, "--limit"),
    output: Path = typer.Option(..., "--output"),  # noqa: B008
    fmt: str = typer.Option("context-pack", "--format"),
) -> None:
    """Produce a context pack markdown file for scriptwriting."""
    if fmt != "context-pack":
        raise typer.BadParameter(
            "only --format context-pack is supported in MVP"
        )
    cfg = ResearchConfig()
    store = ResearchStore(data_dir=cfg.data_dir)
    rows = store.list_documents(topic=topic, limit=limit)
    docs = rows_to_documents(rows)
    md = render_context_pack(
        question=question,
        documents=docs,
        now=datetime.now(UTC),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(md, encoding="utf-8")
    typer.echo(f"wrote {len(docs)} documents to {output}")
