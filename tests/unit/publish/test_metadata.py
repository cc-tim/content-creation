from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from pipeline.publish.metadata import Metadata, load_metadata, save_metadata


def _valid_payload() -> dict:
    return {
        "title": "Test title",
        "description": "A description.",
        "tags": ["a", "b"],
        "category_id": 27,
        "default_language": "zh-TW",
        "default_audio_language": "zh-TW",
        "made_for_kids": False,
        "altered_or_synthetic_content": "synthetic_voice",
    }


def test_metadata_accepts_valid_payload() -> None:
    m = Metadata(**_valid_payload())
    assert m.title == "Test title"
    assert m.altered_or_synthetic_content == "synthetic_voice"


def test_metadata_rejects_too_long_title() -> None:
    payload = _valid_payload() | {"title": "x" * 101}
    with pytest.raises(ValidationError):
        Metadata(**payload)


def test_metadata_rejects_too_long_description() -> None:
    payload = _valid_payload() | {"description": "x" * 5001}
    with pytest.raises(ValidationError):
        Metadata(**payload)


def test_metadata_tags_total_length_counts_commas() -> None:
    # Each tag 100 chars, 5 tags -> 500 chars + 4 commas = 504 => reject
    payload = _valid_payload() | {"tags": ["x" * 100] * 5}
    with pytest.raises(ValidationError):
        Metadata(**payload)


def test_metadata_tags_empty_allowed() -> None:
    payload = _valid_payload() | {"tags": []}
    m = Metadata(**payload)
    assert m.tags == []


def test_metadata_rejects_invalid_disclosure() -> None:
    payload = _valid_payload() | {"altered_or_synthetic_content": "bogus"}
    with pytest.raises(ValidationError):
        Metadata(**payload)


def test_load_and_save_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "metadata.json"
    m = Metadata(**_valid_payload())
    save_metadata(m, path, source_url="https://example.com", profile="test-profile")
    loaded = load_metadata(path)
    assert loaded.title == m.title
    # Underscore-prefixed fields preserved in file but not on model
    raw = json.loads(path.read_text())
    assert raw["_source_url"] == "https://example.com"
    assert raw["_profile"] == "test-profile"
    assert "_generated_at" in raw


def test_load_metadata_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_metadata(tmp_path / "nope.json")
