from pathlib import Path

from PIL import Image

from pipeline.director.still_gate.render import render_scene_still, resolve_variant
from tests.director.still_gate.conftest import make_article_scene


def test_render_scene_still_produces_a_png(tmp_path: Path, busy_png: Path):
    scene = make_article_scene("s1", busy_png)
    out = render_scene_still(scene, variant="no_overlay", work_dir=tmp_path, theme={})
    assert out.exists() and out.suffix == ".png"
    with Image.open(out) as im:
        assert im.size == (1280, 720)  # 16:9 canvas


def test_render_scene_still_is_deterministic(tmp_path: Path, busy_png: Path):
    scene = make_article_scene("s1", busy_png)
    a = render_scene_still(scene, variant="no_overlay", work_dir=tmp_path / "a", theme={})
    b = render_scene_still(scene, variant="no_overlay", work_dir=tmp_path / "b", theme={})
    assert a.read_bytes() == b.read_bytes()  # byte-identical => dup-hash is stable


def test_resolve_variant_reads_context_json(tmp_path: Path):
    (tmp_path / "context.json").write_text('{"preferred_variant": "no_overlay"}')
    assert resolve_variant(tmp_path) == "no_overlay"


def test_resolve_variant_defaults_to_no_overlay(tmp_path: Path):
    # No context.json (the usual pre-TTS gate state) => judge the BARE frame, so
    # overlay-faked reuse/blankness is caught. Defaulting to a burning variant
    # (plain) would mask the very defect the gate exists to catch.
    assert resolve_variant(tmp_path) == "no_overlay"


def test_render_scene_still_forwards_project_root(tmp_path: Path, monkeypatch):
    """The still-gate resolves clip/image paths like validate and compose do: it must hand
    the project dir to render_scene."""
    from pipeline.director.still_gate import render as still_render

    seen: dict[str, object] = {}

    def fake_render_scene(scene, duration, aspect_ratio, work_dir, source_video=None,
                          theme=None, project_root=None):
        seen["project_root"] = project_root
        out = work_dir / "visual.mp4"
        out.write_bytes(b"visual")
        return out

    def fake_frame(src, out, *, frame_style, width, height, fps=30):
        out.write_bytes(b"framed")
        return out

    monkeypatch.setattr(still_render, "render_scene", fake_render_scene)
    monkeypatch.setattr(still_render, "composite_scene_frame", fake_frame)
    monkeypatch.setattr(still_render, "run_ffmpeg", lambda cmd: Path(cmd[-1]).write_bytes(b"png"))

    project = tmp_path / "project"
    still_render.render_scene_still(
        {"id": "s1", "visual": {"type": "text_card", "text": "x"}},
        variant="no_overlay", work_dir=tmp_path / "work", theme={}, project_root=project,
    )
    assert seen["project_root"] == project
