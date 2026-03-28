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
