from __future__ import annotations

from datetime import datetime

from pipeline.research.models import Document
from pipeline.research.query import rank, render_context_pack


def _doc(ext_id: str, *, cited: int, year: str,
         source: str = "openalex", topic: str = "sleep") -> Document:
    return Document(
        source=source,
        external_id=ext_id,
        title=f"Title {ext_id}",
        url=f"https://x/{ext_id}",
        abstract="Abstract text.",
        cleaned_text=f"body {ext_id}",
        topics=[topic],
        published_at=f"{year}-01-01",
        raw_meta={"cited_by_count": cited},
        authors=["Anon"],
        fetched_at=datetime(2026, 4, 15),
    )


def test_rank_prefers_openalex_high_citations_then_recency() -> None:
    a = _doc("W1", cited=5, year="2020")
    b = _doc("W2", cited=100, year="2019")
    c = _doc("https://aap/x", cited=0, year="2024", source="aap")
    ordered = rank([a, b, c], question="sleep")
    assert [d.external_id for d in ordered] == ["W2", "W1", "https://aap/x"]


def test_context_pack_renders_citations_and_topics() -> None:
    docs = [
        _doc("W1", cited=10, year="2022"),
        _doc("https://aap/sleep", cited=0, year="2024", source="aap"),
    ]
    md = render_context_pack(
        question="toddler sleep regression",
        documents=docs,
        now=datetime(2026, 4, 15),
    )
    assert md.startswith("# Research context: toddler sleep regression")
    assert "## [1] Title W1" in md
    assert "## [2] " in md
    assert "Source: OpenAlex" in md
    assert "AAP healthychildren.org" in md
