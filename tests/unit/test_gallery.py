# tests/unit/test_gallery.py
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from pipeline.utils.gallery import GalleryEntry, GalleryIndex, GallerySearcher


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


def test_search_gallery_hits_local_first(tmp_path):
    index_path = tmp_path / "gallery_index.json"
    idx = GalleryIndex(index_path=index_path)
    entry = GalleryEntry(
        id="local1", path=str(tmp_path / "img.png"), type="image", origin="dalle",
        prompt="courtroom", query=None, tags=["courtroom"],
        niche=["courtroom"], created_at="2026-04-23",
    )
    (tmp_path / "img.png").write_bytes(b"fake")
    idx.append(entry)
    idx.save()

    searcher = GallerySearcher(index_path=index_path, gallery_dir=tmp_path)
    result = searcher.search(["courtroom"], niche="courtroom", asset_type="image")

    assert result.tier == "local"
    assert result.entry is not None
    assert result.entry.id == "local1"


def test_search_gallery_falls_through_to_generate_when_no_keys(tmp_path):
    index_path = tmp_path / "gallery_index.json"
    GalleryIndex(index_path=index_path).save()  # empty index

    searcher = GallerySearcher(
        index_path=index_path, gallery_dir=tmp_path,
        pexels_api_key=None, pixabay_api_key=None,
    )
    result = searcher.search(["alien landscape"], niche=None, asset_type="image")

    assert result.tier == "generate"
    assert result.entry is None
    assert "alien" in result.suggested_prompt.lower()


def test_search_gallery_pexels_downloads_on_miss(tmp_path):
    index_path = tmp_path / "gallery_index.json"
    GalleryIndex(index_path=index_path).save()

    fake_image_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.content = fake_image_bytes
    mock_response.json.return_value = {
        "photos": [{"src": {"original": "https://example.com/photo.jpg"}}]
    }

    with patch("httpx.Client") as mock_client:
        instance = mock_client.return_value.__enter__.return_value
        instance.get.return_value = mock_response

        searcher = GallerySearcher(
            index_path=index_path, gallery_dir=tmp_path,
            pexels_api_key="fake_key", pixabay_api_key=None,
        )
        result = searcher.search(["courtroom"], niche=None, asset_type="image")

    assert result.tier == "pexels"
    assert result.entry is not None
    assert Path(result.entry.path).exists()
