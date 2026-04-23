from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pipeline.publish.channels import ChannelProfile
from pipeline.stages.direct import write_metadata_for_project


@pytest.fixture
def sample_profile() -> ChannelProfile:
    return ChannelProfile(
        name="parenting-tw",
        niche="parenting",
        locale="zh-TW",
        channel_id="UC_parenting_tw",
        voice_guide="Warm parental tone.",
        default_tags=["育兒"],
        category_id=27,
    )


@pytest.fixture
def storyboard_synopsis() -> str:
    return "Scene 1: hook. Scene 2: context."


def test_write_metadata_creates_file(
    tmp_path: Path,
    sample_profile: ChannelProfile,
    storyboard_synopsis: str,
) -> None:
    work_dir = tmp_path / "project"
    work_dir.mkdir()

    fake_response = MagicMock()
    fake_response.content = [
        MagicMock(
            type="tool_use",
            input={
                "title": "T",
                "description": "D",
                "tags": ["a"],
                "category_id": 27,
                "default_language": "zh-TW",
                "default_audio_language": "zh-TW",
                "made_for_kids": False,
                "altered_or_synthetic_content": "synthetic_voice",
            },
        )
    ]
    fake_response.stop_reason = "tool_use"

    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response

    with patch("pipeline.stages.direct.get_anthropic_client", return_value=fake_client):
        path = write_metadata_for_project(
            work_dir=work_dir,
            profile=sample_profile,
            locale="zh-TW",
            source_url="https://example.com",
            storyboard_synopsis=storyboard_synopsis,
            knowledge_facts=[],
        )

    assert path.exists()
    payload = json.loads(path.read_text())
    assert payload["title"] == "T"
    assert "育兒" in payload["tags"]  # default tag prepended
    assert payload["category_id"] == 27
    assert payload["_profile"] == "parenting-tw"
    assert payload["_source_url"] == "https://example.com"


def test_write_metadata_does_not_overwrite_existing(
    tmp_path: Path,
    sample_profile: ChannelProfile,
    storyboard_synopsis: str,
) -> None:
    work_dir = tmp_path / "project"
    work_dir.mkdir()
    existing = work_dir / "metadata.json"
    existing.write_text(
        json.dumps(
            {
                "title": "USER EDITED",
                "description": "...",
                "tags": [],
                "category_id": 27,
                "default_language": "zh-TW",
                "default_audio_language": "zh-TW",
                "made_for_kids": False,
                "altered_or_synthetic_content": "synthetic_voice",
            }
        ),
        encoding="utf-8",
    )

    with patch("pipeline.stages.direct.get_anthropic_client") as get_client:
        path = write_metadata_for_project(
            work_dir=work_dir,
            profile=sample_profile,
            locale="zh-TW",
            source_url="https://example.com",
            storyboard_synopsis=storyboard_synopsis,
            knowledge_facts=[],
        )
        get_client.assert_not_called()

    assert json.loads(path.read_text())["title"] == "USER EDITED"


def test_write_metadata_regenerate_forces_overwrite(
    tmp_path: Path,
    sample_profile: ChannelProfile,
    storyboard_synopsis: str,
) -> None:
    work_dir = tmp_path / "project"
    work_dir.mkdir()
    existing = work_dir / "metadata.json"
    existing.write_text('{"title":"OLD"}', encoding="utf-8")

    fake_response = MagicMock()
    fake_response.content = [
        MagicMock(
            type="tool_use",
            input={
                "title": "NEW",
                "description": "D",
                "tags": [],
                "category_id": 27,
                "default_language": "zh-TW",
                "default_audio_language": "zh-TW",
                "made_for_kids": False,
                "altered_or_synthetic_content": "synthetic_voice",
            },
        )
    ]
    fake_response.stop_reason = "tool_use"

    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response

    with patch("pipeline.stages.direct.get_anthropic_client", return_value=fake_client):
        write_metadata_for_project(
            work_dir=work_dir,
            profile=sample_profile,
            locale="zh-TW",
            source_url="https://example.com",
            storyboard_synopsis=storyboard_synopsis,
            knowledge_facts=[],
            regenerate=True,
        )

    assert json.loads(existing.read_text())["title"] == "NEW"
