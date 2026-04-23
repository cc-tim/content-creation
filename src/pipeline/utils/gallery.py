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

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import httpx

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


@dataclass
class GalleryResult:
    tier: str                   # "local" | "pexels" | "pixabay" | "generate"
    entry: GalleryEntry | None  # None when tier == "generate"
    suggested_prompt: str       # populated for tier == "generate"


class GallerySearcher:
    """Tiered gallery lookup: local → Pexels → Pixabay → generate signal."""

    def __init__(
        self,
        index_path: Path = GALLERY_INDEX_PATH,
        gallery_dir: Path = GALLERY_DIR,
        pexels_api_key: str | None = None,
        pixabay_api_key: str | None = None,
    ):
        self._index_path = index_path
        self._gallery_dir = gallery_dir
        self._pexels_key = pexels_api_key
        self._pixabay_key = pixabay_api_key

    def search(
        self,
        query_terms: list[str],
        niche: str | None,
        asset_type: str | None,
    ) -> GalleryResult:
        idx = GalleryIndex.load(self._index_path)

        # Tier 1: local gallery
        hits = idx.search(query_terms, niche=niche, asset_type=asset_type)
        if hits:
            return GalleryResult(tier="local", entry=hits[0], suggested_prompt="")

        query_str = " ".join(query_terms)

        # Tier 2a: Pexels (images)
        if self._pexels_key and asset_type in (None, "image"):
            entry = self._pexels_search(query_str, niche or "")
            if entry:
                idx.append(entry)
                idx.save()
                return GalleryResult(tier="pexels", entry=entry, suggested_prompt="")

        # Tier 2b: Pixabay (clips)
        if self._pixabay_key and asset_type in (None, "clip"):
            entry = self._pixabay_search(query_str, niche or "")
            if entry:
                idx.append(entry)
                idx.save()
                return GalleryResult(tier="pixabay", entry=entry, suggested_prompt="")

        # Tier 3: signal to generate
        suggested = (
            f"flat minimalist illustration, {query_str}, "
            "simple clean lines, limited color palette"
        )
        return GalleryResult(tier="generate", entry=None, suggested_prompt=suggested)

    def _pexels_search(self, query: str, niche: str) -> GalleryEntry | None:
        if not self._pexels_key:
            return None
        query_hash = hashlib.md5(f"pexels:{query}".encode()).hexdigest()[:12]
        images_dir = self._gallery_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        out_path = images_dir / f"{query_hash}.jpg"

        if out_path.exists():
            return self._make_entry(query_hash, str(out_path), "image", "pexels", query, niche)

        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(
                    "https://api.pexels.com/v1/search",
                    params={"query": query, "per_page": 3},
                    headers={"Authorization": self._pexels_key},
                )
                resp.raise_for_status()
                photos = resp.json().get("photos", [])
                if not photos:
                    return None
                img_url = photos[0]["src"]["original"]
                img_resp = client.get(img_url)
                img_resp.raise_for_status()
                out_path.write_bytes(img_resp.content)
        except Exception:
            return None

        return self._make_entry(query_hash, str(out_path), "image", "pexels", query, niche)

    def _pixabay_search(self, query: str, niche: str) -> GalleryEntry | None:
        if not self._pixabay_key:
            return None
        query_hash = hashlib.md5(f"pixabay:{query}".encode()).hexdigest()[:12]
        clips_dir = self._gallery_dir / "clips"
        clips_dir.mkdir(parents=True, exist_ok=True)
        out_path = clips_dir / f"{query_hash}.mp4"

        if out_path.exists():
            return self._make_entry(query_hash, str(out_path), "clip", "pixabay", query, niche)

        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(
                    "https://pixabay.com/api/videos/",
                    params={"key": self._pixabay_key, "q": query, "per_page": 3},
                )
                resp.raise_for_status()
                hits = resp.json().get("hits", [])
                if not hits:
                    return None
                videos = hits[0].get("videos", {})
                url = (
                    videos.get("small", {}).get("url")
                    or videos.get("medium", {}).get("url")
                )
                if not url:
                    return None
                vid_resp = client.get(url)
                vid_resp.raise_for_status()
                out_path.write_bytes(vid_resp.content)
        except Exception:
            return None

        return self._make_entry(query_hash, str(out_path), "clip", "pixabay", query, niche)

    @staticmethod
    def _make_entry(
        entry_id: str, path: str, asset_type: str, origin: str, query: str, niche: str
    ) -> GalleryEntry:
        tags = [t.lower() for t in query.split()]
        return GalleryEntry(
            id=entry_id, path=path, type=asset_type, origin=origin,
            prompt=None, query=query,
            tags=tags, niche=[niche] if niche else [],
            created_at=date.today().isoformat(),
        )


def search_gallery(
    query_terms: list[str],
    niche: str | None = None,
    asset_type: str | None = None,
    pexels_api_key: str | None = None,
    pixabay_api_key: str | None = None,
) -> GalleryResult:
    """Public API for gallery lookup. Reads keys from env when not provided."""
    import os
    pexels_key = pexels_api_key or os.getenv("PEXELS_API_KEY")
    pixabay_key = pixabay_api_key or os.getenv("PIXABAY_API_KEY")
    searcher = GallerySearcher(
        pexels_api_key=pexels_key,
        pixabay_api_key=pixabay_key,
    )
    return searcher.search(query_terms, niche=niche, asset_type=asset_type)
