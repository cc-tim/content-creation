from __future__ import annotations

from datetime import datetime
from pathlib import Path

import httpx

from pipeline.research.adapters.aap import AAPAdapter

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_article_extracts_fields() -> None:
    html = (FIXTURES / "aap_article.html").read_text()
    adapter = AAPAdapter()
    doc, raw, ext = adapter.parse_article(
        url="https://www.healthychildren.org/English/ages-stages/toddler/"
            "Pages/Healthy-Sleep-Habits.aspx",
        html=html,
        topic="sleep",
        fetched_at=datetime(2026, 4, 15),
    )
    assert doc.source == "aap"
    assert doc.external_id.startswith("https://www.healthychildren.org/")
    assert doc.title.startswith("Healthy Sleep Habits")
    assert "Toddlers need 11 to 14 hours" in doc.cleaned_text
    assert doc.published_at == "2024-07-12"
    assert doc.abstract == "Consistent routines support toddler sleep."
    assert ext == "html"
    assert raw == html.encode("utf-8")


def test_parse_search_results_extracts_urls() -> None:
    html = (FIXTURES / "aap_search_results.html").read_text()
    adapter = AAPAdapter()
    urls = adapter.parse_search_results(html)
    assert urls == [
        "https://www.healthychildren.org/English/ages-stages/toddler/Pages/Healthy-Sleep-Habits.aspx",
        "https://www.healthychildren.org/English/ages-stages/baby/sleep/Pages/Getting-Your-Baby-to-Sleep.aspx",
    ]


def test_search_raw_fetches_article_pages_via_mock_transport() -> None:
    search_html = (FIXTURES / "aap_search_results.html").read_text()
    article_html = (FIXTURES / "aap_article.html").read_text()

    def handler(request: httpx.Request) -> httpx.Response:
        if "search-results" in request.url.path or "search" in request.url.path:
            return httpx.Response(200, text=search_html)
        return httpx.Response(200, text=article_html)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = AAPAdapter(client=client, rate_limit_rps=1000.0)
    results = list(adapter.search_raw("sleep", limit=2))
    assert len(results) == 2
    for doc, raw, ext in results:
        assert doc.source == "aap"
        assert ext == "html"
        assert raw == article_html.encode("utf-8")
