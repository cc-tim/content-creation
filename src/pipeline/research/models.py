from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Document(BaseModel):
    """A single research item landed in the corpus."""

    model_config = ConfigDict(frozen=True)

    source: str
    external_id: str
    title: str
    url: str
    cleaned_text: str = Field(
        ...,
        min_length=1,
        description="Normalized text used for content_hash (title + abstract/body).",
    )
    abstract: str | None = None
    authors: list[str] = Field(default_factory=list)
    published_at: str | None = None  # ISO date
    language: str = "en"
    full_text_path: str | None = None
    raw_meta: dict[str, Any] = Field(default_factory=dict)
    topics: list[str] = Field(default_factory=list)
    fetched_at: datetime
    content_hash: str = ""

    @model_validator(mode="after")
    def _fill_hash(self) -> Document:
        if not self.content_hash:
            digest = hashlib.sha256(self.cleaned_text.encode("utf-8")).hexdigest()
            object.__setattr__(self, "content_hash", digest)
        return self


class FetchResult(BaseModel):
    """Summary of one (source, topic) fetch pass."""

    source: str
    topic: str
    ok: int = 0
    duplicates: int = 0
    errors: list[str] = Field(default_factory=list)

    @property
    def total(self) -> int:
        return self.ok + self.duplicates
