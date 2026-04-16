from __future__ import annotations

import json
import time
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

from pipeline.research.models import Document

log = structlog.get_logger(__name__)

_BASE = "https://api.openalex.org/works"


class OpenAlexAdapter:
    source_id = "openalex"

    def __init__(
        self,
        *,
        mailto: str,
        from_publication_date: str = "2018-01-01",
        sort: str = "cited_by_count:desc",
        client: httpx.Client | None = None,
    ) -> None:
        self.mailto = mailto
        self.from_publication_date = from_publication_date
        self.sort = sort
        self._client = client or httpx.Client(
            timeout=20.0,
            headers={"User-Agent": f"content-creation-research-bot ({mailto})"},
        )

    def search_raw(
        self, topic: str, limit: int
    ) -> Iterable[tuple[Document, bytes, str]]:
        params = {
            "search": topic,
            "per_page": str(min(limit, 50)),
            "filter": (
                f"type:article,language:en,"
                f"from_publication_date:{self.from_publication_date}"
            ),
            "sort": self.sort,
            "mailto": self.mailto,
        }
        log.info("openalex.search", topic=topic, limit=limit)
        resp = self._client.get(_BASE, params=params)
        resp.raise_for_status()
        payload = resp.json()
        fetched_at = datetime.now(UTC)
        for work in payload.get("results", [])[:limit]:
            try:
                yield self.parse_work(work, topic=topic, fetched_at=fetched_at)
            except Exception as exc:  # noqa: BLE001
                log.warning("openalex.parse_failed",
                            id=work.get("id"), error=str(exc))
            time.sleep(0.1)  # polite pool headroom

    def parse_work(
        self,
        work: dict[str, Any],
        *,
        topic: str,
        fetched_at: datetime,
    ) -> tuple[Document, bytes, str]:
        external_id = work["id"].rsplit("/", 1)[-1]
        title = work.get("title") or ""
        authors = [
            a["author"]["display_name"]
            for a in work.get("authorships", [])
            if a.get("author", {}).get("display_name")
        ]
        abstract = _reconstruct_abstract(work.get("abstract_inverted_index"))
        url = (
            work.get("primary_location", {}).get("landing_page_url")
            or work["id"]
        )
        cleaned_text = f"{title}\n\n{abstract or ''}".strip()
        raw_meta = {
            "cited_by_count": work.get("cited_by_count", 0),
            "is_oa": work.get("open_access", {}).get("is_oa"),
            "oa_url": work.get("open_access", {}).get("oa_url"),
        }
        doc = Document(
            source=self.source_id,
            external_id=external_id,
            title=title,
            url=url,
            abstract=abstract,
            cleaned_text=cleaned_text,
            authors=authors,
            published_at=work.get("publication_date"),
            language=work.get("language") or "en",
            raw_meta=raw_meta,
            topics=[topic],
            fetched_at=fetched_at,
        )
        raw_bytes = json.dumps(work, ensure_ascii=False).encode("utf-8")
        return doc, raw_bytes, "json"


def _reconstruct_abstract(inv: dict[str, list[int]] | None) -> str | None:
    if not inv:
        return None
    positions: dict[int, str] = {}
    for word, idxs in inv.items():
        for i in idxs:
            positions[i] = word
    ordered = [positions[i] for i in sorted(positions)]
    return " ".join(ordered)
