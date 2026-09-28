from typer.testing import CliRunner

from pipeline import cli_doctor
from pipeline.cli import app

runner = CliRunner()


def test_validate_ok_and_fail(tmp_path):
    ok = runner.invoke(app, ["toon", "validate", "001-lioness-dishes"])
    assert ok.exit_code == 0 and "ok" in ok.stdout
    bad = tmp_path / "bad.yaml"
    bad.write_text("id: b\ncast: {tim: tim}\nshots: []\n")
    res = runner.invoke(app, ["toon", "validate", str(bad)])
    assert res.exit_code == 1


def test_validate_unknown_scene_id():
    res = runner.invoke(app, ["toon", "validate", "does-not-exist-anywhere"])
    assert res.exit_code == 1
    assert "ERROR" in res.stdout


def test_render_stills_writes_pngs(tmp_path):
    res = runner.invoke(app, ["toon", "render", "001-lioness-dishes", "--out", str(tmp_path),
                              "--width", "320", "--height", "180", "--stills", "1.5,4.7"])
    assert res.exit_code == 0, res.stdout
    assert sorted(p.name for p in tmp_path.glob("*.png")) == ["001-lioness-dishes_01.50.png",
                                                               "001-lioness-dishes_04.70.png"]


def test_sheet_writes_png(tmp_path):
    res = runner.invoke(app, ["toon", "sheet", "tim", "--out", str(tmp_path)])
    assert res.exit_code == 0 and (tmp_path / "tim_model_sheet.png").exists()


def test_check_toon_passes_here():
    (r,) = cli_doctor.check_toon()
    assert r.ok, r.detail


def test_validate_invalid_yaml_prints_errors_not_a_traceback(tmp_path):
    bad = tmp_path / "broken.yaml"
    bad.write_text("id: b\ncast: {tim: tim\nshots: [\n")
    res = runner.invoke(app, ["toon", "validate", str(bad)])
    assert res.exit_code == 1 and isinstance(res.exception, SystemExit), res.exception
    assert "ERROR" in res.stdout and "broken.yaml" in res.stdout


def test_render_invalid_scene_prints_errors_not_a_traceback(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("id: b\ncast: {tim: tim}\nshots: []\n")
    res = runner.invoke(app, ["toon", "render", str(bad), "--out", str(tmp_path)])
    assert res.exit_code == 1 and isinstance(res.exception, SystemExit), res.exception
    assert "ERROR" in res.stdout and "shots" in res.stdout


def test_a_missing_scene_path_is_named_as_given(tmp_path):
    missing = tmp_path / "nope.yaml"
    res = runner.invoke(app, ["toon", "validate", str(missing)])
    assert res.exit_code == 1 and isinstance(res.exception, SystemExit), res.exception
    assert str(missing) in res.stdout and ".yaml.yaml" not in res.stdout
