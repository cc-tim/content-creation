from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from pipeline.research.models import Document


def rank(documents: list[Document], *, question: str) -> list[Document]:
    """MVP ranking: source priority, then citation count, then recency.

    OpenAlex peer-reviewed work outranks AAP for the "insightful research"
    slot, but both always show up. Within each bucket, higher citation count
    wins; ties broken by newer publication date.
    """

    def key(d: Document) -> tuple[int, int, str]:
        source_rank = 0 if d.source == "openalex" else 1
        cited = int(d.raw_meta.get("cited_by_count", 0) or 0)
        pub = d.published_at or ""
        return (source_rank, -cited, _neg_date(pub))

    return sorted(documents, key=key)


def _neg_date(iso: str) -> str:
    # Sort newest first lexicographically by inverting components.
    if not iso:
        return "~"
    return "".join(chr(255 - ord(c)) if c.isdigit() else c for c in iso)


def render_context_pack(
    *,
    question: str,
    documents: list[Document],
    now: datetime,
) -> str:
    ordered = rank(documents, question=question)
    lines: list[str] = [
        f"# Research context: {question}",
        f"({len(ordered)} documents, retrieved {now.date().isoformat()})",
        "",
    ]
    for i, doc in enumerate(ordered, start=1):
        lines.append(f"## [{i}] {doc.title}")
        if doc.source == "openalex":
            year = (doc.published_at or "").split("-")[0]
            authors = ", ".join(doc.authors) or "Unknown"
            lines.append(
                f"{authors}, {year}. Source: OpenAlex. URL: {doc.url}"
            )
            if doc.abstract:
                lines.append(f"Abstract: {doc.abstract}")
        elif doc.source == "aap":
            reviewed = doc.published_at or "n/a"
            lines.append(
                f"AAP healthychildren.org, last reviewed {reviewed}. "
                f"URL: {doc.url}"
            )
            if doc.abstract:
                lines.append(f"Summary: {doc.abstract}")
        else:
            lines.append(f"Source: {doc.source}. URL: {doc.url}")
            if doc.abstract:
                lines.append(f"Summary: {doc.abstract}")
        lines.append("")
    lines.append("---")
    return "\n".join(lines) + "\n"


def rows_to_documents(rows: list[dict[str, Any]]) -> list[Document]:
    """Adapt store rows (see ResearchStore.list_documents) to Document models."""
    out: list[Document] = []
    for row in rows:
        out.append(
            Document(
                source=row["source"],
                external_id=row["external_id"],
                title=row["title"],
                url=row["url"],
                abstract=row.get("abstract"),
                cleaned_text=row.get("title", "") + "\n\n" +
                (row.get("abstract") or ""),
                authors=json.loads(row.get("authors") or "[]"),
                published_at=row.get("published_at"),
                language=row.get("language") or "en",
                full_text_path=row.get("full_text_path"),
                raw_meta=json.loads(row.get("raw_meta_json") or "{}"),
                topics=[],
                fetched_at=datetime.fromisoformat(row["fetched_at"]),
                content_hash=row["content_hash"],
            )
        )
    return out
