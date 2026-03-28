import json
from pathlib import Path
from unittest.mock import patch

import pytest

from pipeline.stages.acquire import AcquireStage


@pytest.fixture
def transcript_fixture() -> list[dict]:
    path = Path(__file__).parent.parent / "fixtures" / "transcript.json"
    return json.loads(path.read_text())


async def test_acquire_downloads_video_and_transcript(sample_context, transcript_fixture):
    stage = AcquireStage()
    assert stage.name == "acquire"

    with (
        patch("pipeline.stages.acquire.download_video") as mock_dl,
        patch("pipeline.stages.acquire.extract_transcript") as mock_tr,
    ):
        def fake_download(url, output_dir, resolution):
            video_path = output_dir / "video.mp4"
            video_path.write_bytes(b"fake video")
            return video_path

        mock_dl.side_effect = fake_download
        mock_tr.return_value = (
            "On the night of March 15th, Officer Johnson responded"
            " to a disturbance call in downtown Austin, Texas.",
            transcript_fixture,
        )

        ctx = await stage.run(sample_context)

    assert ctx.video_path is not None
    assert ctx.video_path.exists()
    assert ctx.transcript_text is not None
    assert "March 15th" in ctx.transcript_text


async def test_acquire_creates_source_directory(sample_context, transcript_fixture):
    stage = AcquireStage()
    with (
        patch("pipeline.stages.acquire.download_video") as mock_dl,
        patch("pipeline.stages.acquire.extract_transcript") as mock_tr,
    ):
        def fake_download(url, output_dir, resolution):
            video_path = output_dir / "video.mp4"
            video_path.write_bytes(b"fake")
            return video_path

        mock_dl.side_effect = fake_download
        mock_tr.return_value = ("transcript text", [])

        await stage.run(sample_context)

    source_dir = sample_context.work_dir / "source"
    assert source_dir.exists()
