from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import httpx

from pipeline.research.adapters.openalex import OpenAlexAdapter

FIXTURE = Path(__file__).parent / "fixtures" / "openalex_sleep_sample.json"


def test_parse_work_builds_document() -> None:
    payload = json.loads(FIXTURE.read_text())
    work = payload["results"][0]
    adapter = OpenAlexAdapter(mailto="test@example.com")
    doc, raw_bytes, raw_ext = adapter.parse_work(work, topic="sleep",
                                                 fetched_at=datetime(2026, 4, 15))
    assert doc.source == "openalex"
    assert doc.external_id == "W2741809807"
    assert doc.title == "Sleep regulation in early childhood"
    assert doc.published_at == "2022-03-15"
    assert doc.authors == ["Jane Smith", "Carlos Ruiz"]
    assert doc.abstract == "Sleep patterns in toddlers vary widely."
    assert "sleep" in doc.topics
    assert doc.raw_meta["cited_by_count"] == 42
    assert raw_ext == "json"
    assert json.loads(raw_bytes)["id"].endswith("W2741809807")


def test_search_raw_yields_documents_via_mock_transport() -> None:
    payload = json.loads(FIXTURE.read_text())

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/works"
        assert "mailto=test%40example.com" in str(request.url)
        assert "search=sleep" in str(request.url)
        return httpx.Response(200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = OpenAlexAdapter(mailto="test@example.com", client=client)
    results = list(adapter.search_raw("sleep", limit=10))
    assert len(results) == 1
    doc, _raw, ext = results[0]
    assert doc.external_id == "W2741809807"
    assert ext == "json"
