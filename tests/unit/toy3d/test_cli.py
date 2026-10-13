"""E11 S12-17 and checkpoint A1: `pipeline toon validate|render` handle a toy3d scene, the engine read
from the file, never the 2.5D bank (the EM's mutation M10: the CLI's `_load` on the 2.5D bank must
go red here). A toy3d scene id resolves in the toy3d library; `pipeline validate` fails a bad toy3d
name at the review gate with exit 2."""
import json
from pathlib import Path

from typer.testing import CliRunner

from pipeline.cli import app

runner = CliRunner()
REPO = Path(__file__).resolve().parents[3]


def test_toon_validate_loads_a_toy3d_scene_against_the_toy3d_catalog(monkeypatch):
    import toon.scene

    engines = []
    real = toon.scene.load_catalog

    def spy(engine):
        engines.append(engine)
        return real(engine)

    monkeypatch.setattr(toon.scene, "load_catalog", spy)
    res = runner.invoke(app, ["toon", "validate", "001-beat2-break-in"])
    assert res.exit_code == 0, res.output
    assert "ok  001-beat2-break-in: 1 shots, 37 beats" in res.output
    assert engines == ["toy3d"]


def test_a_scene_id_resolves_in_the_toy3d_library():
    from toon.scene import scene_path

    assert scene_path("001-beat2-break-in") == REPO / "assets" / "toy3d" / "scenes" / "001-beat2-break-in.yaml"
    assert scene_path("001-lioness-dishes") == REPO / "assets" / "toon" / "scenes" / "001-lioness-dishes.yaml"


def test_a_scene_id_in_both_libraries_is_refused(tmp_path, monkeypatch):
    import pytest

    from toon.scene import SceneError, scene_path

    for lib in ("toon", "toy3d"):
        (tmp_path / lib / "scenes").mkdir(parents=True)
        (tmp_path / lib / "scenes" / "twin.yaml").write_text("id: twin\n")
        (tmp_path / lib / "bank").mkdir()
    monkeypatch.setenv("TOON_ASSETS", str(tmp_path / "toon"))
    monkeypatch.setenv("TOY3D_ASSETS", str(tmp_path / "toy3d"))
    with pytest.raises(SceneError, match="both"):
        scene_path("twin")


def test_toon_render_stills_of_a_toy3d_scene_use_the_toy3d_engine(monkeypatch, tmp_path):
    from contextlib import contextmanager

    from toy3d import runtime

    seen = []

    class Page:
        def init(self, bank, w, h, mode):
            seen.append(("init", w, h, mode))

        def render_state(self, spec):
            seen.append(("frame", spec["frame"]))
            from io import BytesIO

            from PIL import Image
            buf = BytesIO()
            Image.new("RGB", (64, 36), (9, 9, 9)).save(buf, "PNG")
            return buf.getvalue()

    @contextmanager
    def fake_open(w, h, mode="render", **kw):
        yield Page()

    monkeypatch.setattr(runtime, "open_page", fake_open)
    monkeypatch.setattr("toon.render.frame", lambda *a, **k: (_ for _ in ()).throw(AssertionError("2.5D")))
    res = runner.invoke(app, ["toon", "render", "001-beat2-break-in", "--out", str(tmp_path), "--stills", "2.4,4"])
    assert res.exit_code == 0, res.output
    assert seen == [("init", 1920, 1080, "render"), ("frame", 72), ("frame", 120)]
    assert sorted(p.name for p in tmp_path.glob("*.png")) == ["001-beat2-break-in_02.40.png", "001-beat2-break-in_04.00.png"]


def test_toon_render_a_toy3d_clip_uses_the_toy3d_renderer(monkeypatch, tmp_path):
    calls = []

    def fake_clip(scene, bank, out, duration, width, height, **kw):
        calls.append((scene.id, type(bank).__name__, duration, width, height))
        Path(out).write_bytes(b"x")
        return Path(out)

    monkeypatch.setattr("toy3d.render.render_clip", fake_clip)
    res = runner.invoke(app, ["toon", "render", "001-beat2-break-in", "--out", str(tmp_path)])
    assert res.exit_code == 0, res.output
    assert calls == [("001-beat2-break-in", "Toy3DBank", 8.0, 1920, 1080)]


def test_pipeline_validate_fails_a_bad_toy3d_name_with_exit_two(tmp_path, monkeypatch):
    output = tmp_path / "output"
    pdir = output / "projects" / "20990101-000000-toy3d"
    pdir.mkdir(parents=True)
    monkeypatch.setenv("PIPELINE_OUTPUT_DIR", str(output))
    visual = {"type": "toon", "engine": "toy3d", "id": "inline", "cast": {"tim": "tim"},
              "shots": [{"at": 0.0, "set": "office", "camera": "front34_push",
                         "place": {"tim": {"spot": "desk_seat", "pose": "typing"}}}]}
    (pdir / "storyboard.json").write_text(json.dumps({"theme": {}, "scenes": [
        {"id": "s1", "section": "hook", "narration": "One.", "narration_est_sec": 4, "visual": visual}]}))
    res = runner.invoke(app, ["validate", "--project-id", pdir.name])
    assert res.exit_code == 2, res.output
    assert "unknown camera 'front34_push'" in res.output
