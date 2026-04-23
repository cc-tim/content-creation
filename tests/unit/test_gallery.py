# tests/unit/test_gallery.py
from __future__ import annotations

from pipeline.utils.gallery import GalleryEntry, GalleryIndex


def test_gallery_index_empty_on_missing_file(tmp_path):
    index_path = tmp_path / "gallery_index.json"
    idx = GalleryIndex.load(index_path)
    assert idx.entries == []


def test_gallery_index_round_trip(tmp_path):
    index_path = tmp_path / "gallery_index.json"
    idx = GalleryIndex(index_path=index_path)
    entry = GalleryEntry(
        id="abc123",
        path=str(tmp_path / "images" / "abc123.png"),
        type="image",
        origin="dalle",
        prompt="courtroom illustration",
        query=None,
        tags=["courtroom", "legal"],
        niche=["bodycam"],
        created_at="2026-04-23",
    )
    idx.append(entry)
    idx.save()

    reloaded = GalleryIndex.load(index_path)
    assert len(reloaded.entries) == 1
    assert reloaded.entries[0].id == "abc123"
    assert reloaded.entries[0].tags == ["courtroom", "legal"]


def test_gallery_index_search_by_tags(tmp_path):
    index_path = tmp_path / "gallery_index.json"
    idx = GalleryIndex(index_path=index_path)
    e1 = GalleryEntry(
        id="e1", path="images/e1.png", type="image", origin="dalle",
        prompt="courtroom", query=None, tags=["courtroom", "legal"],
        niche=["courtroom"], created_at="2026-04-23",
    )
    e2 = GalleryEntry(
        id="e2", path="images/e2.png", type="image", origin="pexels",
        prompt=None, query="police car", tags=["police", "car"],
        niche=["bodycam"], created_at="2026-04-23",
    )
    idx.append(e1)
    idx.append(e2)

    results = idx.search(["courtroom"], niche="courtroom", asset_type="image")
    assert len(results) == 1
    assert results[0].id == "e1"


def test_gallery_index_search_score_threshold(tmp_path):
    index_path = tmp_path / "gallery_index.json"
    idx = GalleryIndex(index_path=index_path)
    entry = GalleryEntry(
        id="e1", path="images/e1.png", type="image", origin="dalle",
        prompt="courtroom illustration", query=None,
        tags=["courtroom", "legal", "interior"],
        niche=["courtroom"], created_at="2026-04-23",
    )
    idx.append(entry)

    # "courtroom" matches 1/1 query terms → score 1.0 > threshold
    hits = idx.search(["courtroom"], niche=None, asset_type=None)
    assert len(hits) == 1

    # "office" doesn't match any tag → score 0.0 < threshold
    misses = idx.search(["office"], niche=None, asset_type=None)
    assert len(misses) == 0
