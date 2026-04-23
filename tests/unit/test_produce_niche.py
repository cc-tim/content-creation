from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from pipeline.cli import app

CHANNELS_FIXTURE = (
    Path(__file__).parents[1] / "fixtures" / "sample_youtube_channels.toml"
)


@pytest.fixture
def no_stages(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Stub out actual stage execution so we can inspect only the ctx construction."""
    captured: dict = {}

    class StubOrchestrator:
        def __init__(self, stages):
            self.stages = stages

        async def run(self, ctx, start_from=None):
            captured["ctx"] = ctx
            res = MagicMock()
            res.success = True
            res.ctx = ctx
            return res

    monkeypatch.setattr("pipeline.cli.Orchestrator", StubOrchestrator)
    return captured


def test_produce_uses_explicit_niche(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_stages: dict
) -> None:
    monkeypatch.setenv("PIPELINE_OUTPUT_DIR", str(tmp_path))
    runner = CliRunner()
    with patch("pipeline.cli._channel_config_path", return_value=CHANNELS_FIXTURE):
        result = runner.invoke(
            app,
            [
                "produce",
                "--url", "https://example.com",
                "--locale", "zh-TW",
                "--niche", "drama",
                "--skip-review",
            ],
        )
    assert result.exit_code == 0, result.output
    assert no_stages["ctx"].niche == "drama"


def test_produce_auto_detects_when_locale_unambiguous(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_stages: dict
) -> None:
    monkeypatch.setenv("PIPELINE_OUTPUT_DIR", str(tmp_path))
    runner = CliRunner()
    with patch("pipeline.cli._channel_config_path", return_value=CHANNELS_FIXTURE):
        # Fixture has only tech/en — auto-detect to "tech"
        result = runner.invoke(
            app,
            [
                "produce",
                "--url", "https://example.com",
                "--locale", "en",
                "--skip-review",
            ],
        )
    assert result.exit_code == 0, result.output
    assert no_stages["ctx"].niche == "tech"


def test_produce_niche_none_skips_routing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_stages: dict
) -> None:
    monkeypatch.setenv("PIPELINE_OUTPUT_DIR", str(tmp_path))
    runner = CliRunner()
    with patch("pipeline.cli._channel_config_path", return_value=CHANNELS_FIXTURE):
        result = runner.invoke(
            app,
            [
                "produce",
                "--url", "https://example.com",
                "--locale", "es-MX",
                "--niche", "none",
                "--skip-review",
            ],
        )
    assert result.exit_code == 0, result.output
    assert no_stages["ctx"].niche == "none"


def test_produce_ambiguous_locale_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_stages: dict
) -> None:
    monkeypatch.setenv("PIPELINE_OUTPUT_DIR", str(tmp_path))
    runner = CliRunner()
    with patch("pipeline.cli._channel_config_path", return_value=CHANNELS_FIXTURE):
        # zh-TW maps to both parenting and drama
        result = runner.invoke(
            app,
            [
                "produce",
                "--url", "https://example.com",
                "--locale", "zh-TW",
                "--skip-review",
            ],
        )
    assert result.exit_code != 0
    assert "ambiguous" in result.output.lower()
