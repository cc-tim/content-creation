from __future__ import annotations

import re
import time
from collections.abc import Iterable
from datetime import UTC, datetime
from urllib.parse import urlsplit, urlunsplit

import httpx
import structlog
from selectolax.parser import HTMLParser

from pipeline.research.models import Document

log = structlog.get_logger(__name__)

_SEARCH_URL = "https://www.healthychildren.org/English/search-results/Pages/results.aspx"


class AAPAdapter:
    source_id = "aap"

    def __init__(
        self,
        *,
        user_agent: str = "content-creation-research-bot "
                         "(contact: creditcardtim@gmail.com)",
        rate_limit_rps: float = 1.0,
        max_result_pages: int = 2,
        client: httpx.Client | None = None,
    ) -> None:
        self.user_agent = user_agent
        self.rate_delay = 1.0 / rate_limit_rps if rate_limit_rps > 0 else 0.0
        self.max_result_pages = max_result_pages
        self._client = client or httpx.Client(
            timeout=20.0,
            headers={"User-Agent": user_agent},
            follow_redirects=True,
        )

    def search_raw(
        self, topic: str, limit: int
    ) -> Iterable[tuple[Document, bytes, str]]:
        log.info("aap.search", topic=topic, limit=limit)
        yielded = 0
        for page in range(1, self.max_result_pages + 1):
            try:
                resp = self._client.get(
                    _SEARCH_URL,
                    params={"k": topic, "pg": str(page)},
                )
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                log.warning("aap.search_failed", page=page, error=str(exc))
                break
            urls = self.parse_search_results(resp.text)
            if not urls:
                break
            for url in urls:
                if yielded >= limit:
                    return
                time.sleep(self.rate_delay)
                try:
                    article_resp = self._client.get(url)
                    article_resp.raise_for_status()
                except httpx.HTTPError as exc:
                    log.warning("aap.article_failed", url=url, error=str(exc))
                    continue
                try:
                    yield self.parse_article(
                        url=url,
                        html=article_resp.text,
                        topic=topic,
                        fetched_at=datetime.now(UTC),
                    )
                except Exception as exc:  # noqa: BLE001
                    log.warning("aap.parse_failed", url=url, error=str(exc))
                    continue
                yielded += 1
            time.sleep(self.rate_delay)

    def parse_search_results(self, html: str) -> list[str]:
        tree = HTMLParser(html)
        out: list[str] = []
        for node in tree.css("a.srch-Title"):
            href = node.attributes.get("href")
            if href:
                out.append(_canonicalize(href))
        return out

    def parse_article(
        self,
        *,
        url: str,
        html: str,
        topic: str,
        fetched_at: datetime,
    ) -> tuple[Document, bytes, str]:
        tree = HTMLParser(html)

        title_node = tree.css_first("h1") or tree.css_first("title")
        title = (title_node.text(strip=True) if title_node else "").split(" — ")[0]

        desc_node = tree.css_first('meta[name="description"]')
        abstract = (
            desc_node.attributes.get("content") if desc_node is not None else None
        )

        article = tree.css_first("article") or tree.body
        body_text = article.text(separator="\n", strip=True) if article else ""

        published_at: str | None = None
        reviewed = tree.css_first(".last-reviewed")
        if reviewed is not None:
            m = re.search(r"(\d{4}-\d{2}-\d{2})", reviewed.text())
            if m:
                published_at = m.group(1)

        cleaned_text = f"{title}\n\n{body_text}".strip()
        doc = Document(
            source=self.source_id,
            external_id=_canonicalize(url),
            title=title,
            url=_canonicalize(url),
            abstract=abstract,
            cleaned_text=cleaned_text,
            authors=[],
            published_at=published_at,
            language="en",
            raw_meta={},
            topics=[topic],
            fetched_at=fetched_at,
        )
        return doc, html.encode("utf-8"), "html"


def _canonicalize(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
