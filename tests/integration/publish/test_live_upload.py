"""Live integration test against a sandbox YouTube channel.

Marker: network. Opt in with `pytest -m network`.

Setup requirements (documented in README.md):
- A dedicated "sandbox" channel
- Profile "sandbox" in configs/youtube_channels.toml
- Token at ~/.config/content-creation/youtube/sandbox.json (via `pipeline publish auth`)
- Env var `YT_PUBLISH_SANDBOX=1` to opt in
- Fixtures: `tests/fixtures/sample_final.mp4` (10s) + `sample_thumbnail.png`

The test uploads a minimal video → verifies via videos.list → DELETES it.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pipeline.publish.auth import load_credentials, token_path_for
from pipeline.publish.channels import load_channel_config
from pipeline.publish.client import YouTubeClient
from pipeline.publish.metadata import Metadata
from pipeline.publish.stage import PublishStage
from pipeline.stages.base import PipelineContext

pytestmark = pytest.mark.network


@pytest.fixture(scope="module")
def sandbox_enabled() -> None:
    if not os.getenv("YT_PUBLISH_SANDBOX"):
        pytest.skip("set YT_PUBLISH_SANDBOX=1 to run live sandbox tests")


@pytest.fixture
def sandbox_project(tmp_path: Path) -> Path:
    fixtures = Path(__file__).parents[2] / "fixtures"
    video = fixtures / "sample_final.mp4"
    thumb = fixtures / "sample_thumbnail.png"
    if not video.exists() or not thumb.exists():
        pytest.skip("sandbox fixtures missing; see README")

    d = tmp_path / "sandbox_project"
    d.mkdir()
    (d / "final.mp4").write_bytes(video.read_bytes())
    (d / "thumbnail.png").write_bytes(thumb.read_bytes())
    meta = Metadata(
        title="[SANDBOX] pipeline integration test",
        description="Auto-deleted test upload.",
        tags=["test"],
        category_id=27,
        default_language="en",
        default_audio_language="en",
    )
    from pipeline.publish.metadata import save_metadata

    save_metadata(meta, d / "metadata.json", source_url="https://example.com", profile="sandbox")
    return d


def test_live_upload_and_cleanup(sandbox_enabled: None, sandbox_project: Path) -> None:
    cfg = load_channel_config(Path("configs/youtube_channels.toml"))
    assert "sandbox" in cfg.profiles, "add a [profiles.sandbox] entry first"

    creds = load_credentials(token_path_for("sandbox"))
    client = YouTubeClient.from_credentials(credentials=creds)

    stage = PublishStage(
        client_factory=lambda _: client,
        channel_config=cfg,
        privacy="private",
    )
    ctx = PipelineContext(
        project_id=99999,
        source_url="https://example.com",
        locale="en",
        work_dir=sandbox_project,
        niche="sandbox",
        final_video_path=sandbox_project / "final.mp4",
    )
    try:
        stage.publish(ctx, profile_override="sandbox")
        assert ctx.youtube_video_id is not None
        items = client.videos_list(video_id=ctx.youtube_video_id, part="status,snippet")
        assert items, "uploaded video missing from videos.list"
        assert items[0]["status"]["privacyStatus"] == "private"
    finally:
        if ctx.youtube_video_id:
            client.api.videos().delete(id=ctx.youtube_video_id).execute()
