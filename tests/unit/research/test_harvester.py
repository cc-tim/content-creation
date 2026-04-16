from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from pipeline.research.harvester import Harvester
from pipeline.research.models import Document
from pipeline.research.store import ResearchStore


class _StubAdapter:
    def __init__(self, source: str, docs: list[Document]) -> None:
        self.source_id = source
        self._docs = docs

    def search_raw(
        self, topic: str, limit: int
    ) -> Iterable[tuple[Document, bytes, str]]:
        for d in self._docs:
            yield d, b"{}", "json"


def _doc(source: str, ext_id: str, body: str) -> Document:
    return Document(
        source=source,
        external_id=ext_id,
        title="T",
        url=f"https://x/{ext_id}",
        abstract="a",
        cleaned_text=body,
        topics=["sleep"],
        fetched_at=datetime(2026, 4, 15),
    )


def test_harvester_writes_new_and_counts_dups(tmp_path: Path) -> None:
    store = ResearchStore(data_dir=tmp_path)
    adapter = _StubAdapter(
        "openalex",
        [
            _doc("openalex", "W1", "body A"),
            _doc("openalex", "W2", "body B"),
            _doc("openalex", "W1", "body A"),  # source dup
        ],
    )
    h = Harvester(store=store, adapters=[adapter])
    results = h.harvest_topic("sleep", limit=10)
    assert len(results) == 1
    assert results[0].ok == 2
    assert results[0].duplicates == 1


def test_harvester_runs_all_configured_topics(tmp_path: Path) -> None:
    store = ResearchStore(data_dir=tmp_path)
    adapter = _StubAdapter("openalex", [_doc("openalex", "W1", "b")])
    h = Harvester(store=store, adapters=[adapter])
    results = h.harvest(topics=["sleep", "discipline"], limit=5)
    assert len(results) == 2
    assert {r.topic for r in results} == {"sleep", "discipline"}
