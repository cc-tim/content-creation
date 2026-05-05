from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from pipeline.publish.cli import publish_app
from pipeline.stages.base import PipelineContext

META_FIXTURE = Path(__file__).parents[2] / "fixtures" / "sample_metadata.json"
CHANNELS_FIXTURE = Path(__file__).parents[2] / "fixtures" / "sample_youtube_channels.toml"


@pytest.fixture
def project_with_context(tmp_path: Path) -> Path:
    d = tmp_path / "projects" / "42"
    d.mkdir(parents=True)
    (d / "final.mp4").write_bytes(b"x" * 1024)
    (d / "thumbnail.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 500)
    meta = json.loads(META_FIXTURE.read_text())
    (d / "metadata.json").write_text(json.dumps(meta))
    ctx = PipelineContext(
        project_id=42,
        source_url="https://example.com",
        locale="zh-TW",
        work_dir=d,
        niche="parenting",
        final_video_path=d / "final.mp4",
    )
    ctx.save()
    return d


def test_publish_dry_run(project_with_context: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PIPELINE_OUTPUT_DIR", str(project_with_context.parent.parent))
    runner = CliRunner()
    with patch("pipeline.publish.cli._load_channel_config_path", return_value=CHANNELS_FIXTURE):
        result = runner.invoke(publish_app, ["42", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "snippet" in result.output
    assert "privacyStatus" in result.output


def test_publish_happy_path(project_with_context: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PIPELINE_OUTPUT_DIR", str(project_with_context.parent.parent))
    runner = CliRunner()

    fake_client = MagicMock()
    fake_client.videos_insert.return_value = "V1"

    with (
        patch("pipeline.publish.cli._load_channel_config_path", return_value=CHANNELS_FIXTURE),
        patch("pipeline.publish.cli._build_youtube_client", return_value=fake_client),
    ):
        result = runner.invoke(publish_app, ["42"])

    assert result.exit_code == 0, result.output
    assert "V1" in result.output
    ctx = PipelineContext.load(project_with_context / "context.json")
    assert ctx.youtube_video_id == "V1"


def test_publish_missing_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PIPELINE_OUTPUT_DIR", str(tmp_path))
    runner = CliRunner()
    with patch("pipeline.publish.cli._load_channel_config_path", return_value=CHANNELS_FIXTURE):
        result = runner.invoke(publish_app, ["999"])
    assert result.exit_code != 0
    assert "project" in result.output.lower() or "not found" in result.output.lower()


def test_auth_command_runs_flow_and_verifies_channel(tmp_path: Path) -> None:
    runner = CliRunner()

    fake_creds = MagicMock()
    fake_creds.to_json.return_value = '{"refresh_token":"rt"}'
    fake_api = MagicMock()
    fake_api.channels().list().execute.return_value = {"items": [{"id": "UC_parenting_tw"}]}

    with (
        patch("pipeline.publish.cli._load_channel_config_path", return_value=CHANNELS_FIXTURE),
        patch("pipeline.publish.cli.run_oauth_flow", return_value=fake_creds),
        patch("pipeline.publish.cli._token_dir", return_value=tmp_path),
        patch("pipeline.publish.cli._client_secret_file", return_value=tmp_path / "cs.json"),
        patch("pipeline.publish.cli.YouTubeClient.from_credentials") as from_creds,
    ):
        from_creds.return_value = MagicMock(api=fake_api)
        (tmp_path / "cs.json").write_text('{"installed":{"client_id":"x","client_secret":"y"}}')
        result = runner.invoke(publish_app, ["auth", "--profile", "parenting-tw"])

    assert result.exit_code == 0, result.output
    assert (tmp_path / "parenting-tw.json").exists()


def test_auth_command_channel_mismatch(tmp_path: Path) -> None:
    runner = CliRunner()

    fake_creds = MagicMock()
    fake_api = MagicMock()
    fake_api.channels().list().execute.return_value = {"items": [{"id": "UC_WRONG"}]}

    with (
        patch("pipeline.publish.cli._load_channel_config_path", return_value=CHANNELS_FIXTURE),
        patch("pipeline.publish.cli.run_oauth_flow", return_value=fake_creds),
        patch("pipeline.publish.cli._token_dir", return_value=tmp_path),
        patch("pipeline.publish.cli._client_secret_file", return_value=tmp_path / "cs.json"),
        patch("pipeline.publish.cli.YouTubeClient.from_credentials") as from_creds,
    ):
        from_creds.return_value = MagicMock(api=fake_api)
        (tmp_path / "cs.json").write_text('{"installed":{"client_id":"x","client_secret":"y"}}')
        result = runner.invoke(publish_app, ["auth", "--profile", "parenting-tw"])

    assert result.exit_code != 0
    assert "mismatch" in result.output.lower() or "expected" in result.output.lower()
    assert not (tmp_path / "parenting-tw.json").exists()


def test_accounts_list(tmp_path: Path) -> None:
    (tmp_path / "parenting-tw.json").write_text('{"refresh_token":"x"}')
    runner = CliRunner()
    with (
        patch("pipeline.publish.cli._load_channel_config_path", return_value=CHANNELS_FIXTURE),
        patch("pipeline.publish.cli._token_dir", return_value=tmp_path),
    ):
        result = runner.invoke(publish_app, ["accounts", "list"])
    assert result.exit_code == 0, result.output
    assert "parenting-tw" in result.output
    assert "authenticated" in result.output.lower() or "✓" in result.output
    assert "tech-en" in result.output
    assert "missing" in result.output.lower() or "✗" in result.output


def test_accounts_revoke(tmp_path: Path) -> None:
    (tmp_path / "parenting-tw.json").write_text('{"refresh_token":"x"}')
    runner = CliRunner()
    with (
        patch("pipeline.publish.cli._load_channel_config_path", return_value=CHANNELS_FIXTURE),
        patch("pipeline.publish.cli._token_dir", return_value=tmp_path),
    ):
        result = runner.invoke(publish_app, ["accounts", "revoke", "parenting-tw"])
    assert result.exit_code == 0, result.output
    assert not (tmp_path / "parenting-tw.json").exists()


def test_status_local_not_uploaded(
    project_with_context: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PIPELINE_OUTPUT_DIR", str(project_with_context.parent.parent))
    runner = CliRunner()
    with patch("pipeline.publish.cli._load_channel_config_path", return_value=CHANNELS_FIXTURE):
        result = runner.invoke(publish_app, ["status", "42"])
    assert result.exit_code == 0, result.output
    assert "video" in result.output.lower()
    assert "✗" in result.output or "pending" in result.output.lower()


def test_status_local_partially_uploaded(
    project_with_context: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = PipelineContext.load(project_with_context / "context.json")
    ctx.youtube_video_id = "V1"
    ctx.save()

    monkeypatch.setenv("PIPELINE_OUTPUT_DIR", str(project_with_context.parent.parent))
    runner = CliRunner()
    with patch("pipeline.publish.cli._load_channel_config_path", return_value=CHANNELS_FIXTURE):
        result = runner.invoke(publish_app, ["status", "42"])
    assert result.exit_code == 0, result.output
    assert "V1" in result.output
    assert "thumbnail" in result.output.lower()


def test_status_remote(project_with_context: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = PipelineContext.load(project_with_context / "context.json")
    ctx.youtube_video_id = "V1"
    ctx.thumbnail_uploaded = True
    ctx.disclosure_set = True
    ctx.publish_profile = "parenting-tw"
    ctx.save()

    monkeypatch.setenv("PIPELINE_OUTPUT_DIR", str(project_with_context.parent.parent))
    runner = CliRunner()

    fake_client = MagicMock()
    fake_client.videos_list.return_value = [
        {"id": "V1", "status": {"privacyStatus": "unlisted"}, "snippet": {"title": "T"}}
    ]
    with (
        patch("pipeline.publish.cli._load_channel_config_path", return_value=CHANNELS_FIXTURE),
        patch("pipeline.publish.cli._build_youtube_client", return_value=fake_client),
    ):
        result = runner.invoke(publish_app, ["status", "42", "--remote"])
    assert result.exit_code == 0, result.output
    assert "unlisted" in result.output.lower()
