from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from pipeline.research.models import Document


@runtime_checkable
class Adapter(Protocol):
    """A source-specific fetcher. Does NOT touch the store or filesystem.

    Adapters yield Document objects with cleaned_text populated and the
    raw payload available via .raw_meta (for JSON sources) or by
    returning (Document, raw_bytes, raw_ext) tuples via `search_raw`.
    """

    source_id: str

    def search_raw(
        self, topic: str, limit: int
    ) -> Iterable[tuple[Document, bytes, str]]:
        """Yield (doc, raw_bytes, raw_ext) for each result.

        raw_ext is the file extension to store raw_bytes under
        (e.g. 'json' for API payloads, 'html' for scraped pages).
        """
        ...
