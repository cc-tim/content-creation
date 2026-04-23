# src/pipeline/utils/gallery.py
"""Tiered gallery for image and video clip asset reuse.

Lookup order:
  Tier 1 — local gallery_index.json (keyword match, $0 cost)
  Tier 2 — Pexels API (photos) + Pixabay API (video clips), free tiers
  Tier 3 — signal to generate new (DALL-E via existing flow)

Generated images from /produce are written back to the gallery by the
compose stage so they are available for future videos.
"""
from __future__ import annotations

import hashlib  # noqa: F401
import json
from dataclasses import asdict, dataclass, field
from datetime import date  # noqa: F401
from pathlib import Path
from typing import Any

import httpx  # noqa: F401

GALLERY_DIR = Path("output/gallery")
GALLERY_INDEX_PATH = GALLERY_DIR / "gallery_index.json"
MATCH_THRESHOLD = 0.6


@dataclass
class GalleryEntry:
    id: str
    path: str           # relative or absolute path to file
    type: str           # "image" or "clip"
    origin: str         # "dalle" | "gemini" | "pexels" | "pixabay"
    prompt: str | None  # for generated assets
    query: str | None   # for stock API assets
    tags: list[str]
    niche: list[str]
    created_at: str     # ISO date string

    def match_score(self, query_terms: list[str]) -> float:
        """Fraction of query_terms found in self.tags."""
        if not query_terms:
            return 0.0
        hits = sum(
            1 for t in query_terms if t.lower() in [tag.lower() for tag in self.tags]
        )
        return hits / len(query_terms)


@dataclass
class GalleryIndex:
    index_path: Path
    entries: list[GalleryEntry] = field(default_factory=list)

    @classmethod
    def load(cls, index_path: Path) -> GalleryIndex:
        if not index_path.exists():
            return cls(index_path=index_path)
        data = json.loads(index_path.read_text(encoding="utf-8"))
        entries = [GalleryEntry(**e) for e in data.get("entries", [])]
        return cls(index_path=index_path, entries=entries)

    def save(self) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        data: dict[str, Any] = {
            "version": 1,
            "entries": [asdict(e) for e in self.entries],
        }
        self.index_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def append(self, entry: GalleryEntry) -> None:
        self.entries.append(entry)

    def search(
        self,
        query_terms: list[str],
        niche: str | None,
        asset_type: str | None,
    ) -> list[GalleryEntry]:
        """Return entries matching query_terms above MATCH_THRESHOLD.

        Filters by niche and asset_type when specified.
        Sorted by match score descending.
        """
        results: list[tuple[float, GalleryEntry]] = []
        for entry in self.entries:
            if asset_type and entry.type != asset_type:
                continue
            if niche and niche not in entry.niche:
                continue
            score = entry.match_score(query_terms)
            if score >= MATCH_THRESHOLD:
                results.append((score, entry))
        results.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in results]
