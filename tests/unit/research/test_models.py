from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from pipeline.research.models import Document, FetchResult


def test_document_computes_content_hash_when_missing() -> None:
    doc = Document(
        source="openalex",
        external_id="W1",
        title="Sleep in toddlers",
        url="https://example.org/w1",
        abstract="A study of toddler sleep.",
        cleaned_text="Sleep in toddlers\n\nA study of toddler sleep.",
        fetched_at=datetime(2026, 4, 15, 12, 0, 0),
    )
    assert len(doc.content_hash) == 64  # sha256 hex


def test_document_same_cleaned_text_gives_same_hash() -> None:
    kwargs = dict(
        source="openalex",
        external_id="W1",
        title="T",
        url="https://example.org/w1",
        cleaned_text="identical body",
        fetched_at=datetime(2026, 4, 15, 12, 0, 0),
    )
    assert Document(**kwargs).content_hash == Document(**kwargs).content_hash


def test_document_requires_cleaned_text() -> None:
    with pytest.raises(ValidationError):
        Document(
            source="openalex",
            external_id="W1",
            title="T",
            url="https://example.org/w1",
            fetched_at=datetime(2026, 4, 15, 12, 0, 0),
        )  # type: ignore[call-arg]


def test_fetch_result_counts() -> None:
    r = FetchResult(source="openalex", topic="sleep", ok=3, duplicates=2)
    assert r.total == 5
