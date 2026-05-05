from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class LocalizedMeta(BaseModel):
    """Title and description for a single locale (used in YouTube localizations)."""

    title: str = Field(max_length=100)
    description: str = Field(max_length=5000)


class Metadata(BaseModel):
    """YouTube video metadata. Validated against YouTube's server-side limits."""

    title: str = Field(max_length=100)
    description: str = Field(max_length=5000)
    tags: list[str] = Field(default_factory=list)
    category_id: int
    default_language: str
    default_audio_language: str
    made_for_kids: bool = False
    altered_or_synthetic_content: Literal["synthetic_voice", "altered", "none"] = "synthetic_voice"
    localizations: dict[str, LocalizedMeta] = Field(default_factory=dict)

    @field_validator("tags")
    @classmethod
    def _tags_total_length(cls, v: list[str]) -> list[str]:
        # YouTube counts separators between tags.
        total = sum(len(t) for t in v) + max(len(v) - 1, 0)
        if total > 500:
            raise ValueError(f"tags total length {total} exceeds YouTube limit of 500")
        return v


def load_metadata(path: Path) -> Metadata:
    """Load metadata.json, ignoring underscore-prefixed trace fields."""
    if not path.exists():
        raise FileNotFoundError(f"metadata.json not found at {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    clean = {k: v for k, v in raw.items() if not k.startswith("_")}
    return Metadata(**clean)


def save_metadata(
    metadata: Metadata,
    path: Path,
    *,
    source_url: str,
    profile: str,
) -> None:
    """Write metadata.json including underscore-prefixed trace fields."""
    payload = metadata.model_dump()
    payload["_generated_at"] = datetime.now(tz=UTC).isoformat()
    payload["_source_url"] = source_url
    payload["_profile"] = profile
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
