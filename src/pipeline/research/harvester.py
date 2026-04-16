from __future__ import annotations

from collections.abc import Sequence

import structlog

from pipeline.research.adapters.base import Adapter
from pipeline.research.models import FetchResult
from pipeline.research.store import ResearchStore

log = structlog.get_logger(__name__)


class Harvester:
    def __init__(self, *, store: ResearchStore, adapters: Sequence[Adapter]) -> None:
        self.store = store
        self.adapters = list(adapters)

    def harvest(self, *, topics: Sequence[str], limit: int) -> list[FetchResult]:
        results: list[FetchResult] = []
        for topic in topics:
            results.extend(self.harvest_topic(topic, limit=limit))
        return results

    def harvest_topic(self, topic: str, *, limit: int) -> list[FetchResult]:
        results: list[FetchResult] = []
        for adapter in self.adapters:
            fetch_id = self.store.start_fetch(adapter.source_id, topic)
            ok = 0
            dups = 0
            errors: list[str] = []
            try:
                for doc, raw_bytes, raw_ext in adapter.search_raw(topic, limit):
                    try:
                        res = self.store.upsert(
                            doc, raw_bytes=raw_bytes, raw_ext=raw_ext
                        )
                    except Exception as exc:  # noqa: BLE001
                        errors.append(f"{doc.external_id}: {exc}")
                        continue
                    if res.status == "inserted":
                        ok += 1
                    else:
                        dups += 1
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "harvester.adapter_failed",
                    source=adapter.source_id,
                    topic=topic,
                    error=str(exc),
                )
                errors.append(str(exc))
            self.store.finish_fetch(
                fetch_id,
                ok=ok,
                duplicates=dups,
                error="; ".join(errors) if errors else None,
            )
            results.append(
                FetchResult(
                    source=adapter.source_id, topic=topic,
                    ok=ok, duplicates=dups, errors=errors,
                )
            )
        return results
