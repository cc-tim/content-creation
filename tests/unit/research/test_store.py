from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from pipeline.research.models import Document
from pipeline.research.store import ResearchStore


def _doc(
    *,
    source: str = "openalex",
    external_id: str = "W1",
    cleaned_text: str = "body A",
    topics: list[str] | None = None,
) -> Document:
    return Document(
        source=source,
        external_id=external_id,
        title="T",
        url="https://example.org/" + external_id,
        abstract="abs",
        cleaned_text=cleaned_text,
        topics=topics or ["sleep"],
        fetched_at=datetime(2026, 4, 15, 12, 0, 0),
    )


@pytest.fixture()
def store(tmp_path: Path) -> ResearchStore:
    return ResearchStore(data_dir=tmp_path)


def test_store_creates_schema(store: ResearchStore) -> None:
    tables = {row[0] for row in store.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert {"documents", "document_topics", "fetch_log"}.issubset(tables)


def test_insert_returns_inserted(store: ResearchStore) -> None:
    result = store.upsert(_doc(), raw_bytes=b"{}", raw_ext="json")
    assert result.status == "inserted"
    row = store.conn.execute(
        "SELECT source, external_id, content_hash FROM documents"
    ).fetchone()
    assert row == ("openalex", "W1", _doc().content_hash)


def test_insert_writes_raw_file(store: ResearchStore, tmp_path: Path) -> None:
    store.upsert(_doc(), raw_bytes=b'{"hello":true}', raw_ext="json")
    raw = tmp_path / "raw" / "openalex" / "W1.json"
    assert raw.read_bytes() == b'{"hello":true}'


def test_same_source_and_external_id_is_source_dup(store: ResearchStore) -> None:
    store.upsert(_doc(topics=["sleep"]), raw_bytes=b"{}", raw_ext="json")
    result = store.upsert(
        _doc(topics=["sleep", "toddler"]), raw_bytes=b"{}", raw_ext="json"
    )
    assert result.status == "source_duplicate"
    topics = {
        t for (t,) in store.conn.execute(
            "SELECT topic FROM document_topics"
        ).fetchall()
    }
    assert topics == {"sleep", "toddler"}
