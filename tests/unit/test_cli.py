from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from pipeline.cli import app

runner = CliRunner()


def test_cli_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "produce" in result.output


def test_produce_help():
    result = runner.invoke(app, ["produce", "--help"])
    assert result.exit_code == 0
    assert "--url" in result.output
    assert "--locale" in result.output
    assert "--skip-review" in result.output


def test_shorts_help():
    result = runner.invoke(app, ["shorts", "--help"])
    assert result.exit_code == 0
    assert "--project-id" in result.output
    assert "--count" in result.output
    assert "--tone" in result.output


def test_produce_passes_local_transcript_to_acquire_stage(tmp_path):
    """--transcript flag is forwarded to AcquireStage constructor."""
    transcript_file = tmp_path / "t.csv"
    transcript_file.write_text("00:00,0.08,4.16,Hello world.\n", encoding="utf-8")

    captured: list = []

    original_init = __import__(
        "pipeline.stages.acquire", fromlist=["AcquireStage"]
    ).AcquireStage.__init__

    def capturing_init(self, local_transcript=None, local_video=None):
        captured.append({"local_transcript": local_transcript, "local_video": local_video})
        original_init(self, local_transcript=local_transcript, local_video=local_video)

    runner = CliRunner()
    with (
        patch("pipeline.stages.acquire.AcquireStage.__init__", capturing_init),
        patch("pipeline.cli.Orchestrator") as mock_orch_cls,
    ):
        mock_orch = MagicMock()
        mock_orch.run = AsyncMock(
            return_value=MagicMock(success=False, failed_stage="acquire", error="test stop")
        )
        mock_orch_cls.return_value = mock_orch

        runner.invoke(
            app,
            ["produce", "--url", "https://youtube.com/watch?v=test",
             "--transcript", str(transcript_file)],
        )

    assert len(captured) == 1
    assert captured[0]["local_transcript"] == transcript_file
    assert captured[0]["local_video"] is None
