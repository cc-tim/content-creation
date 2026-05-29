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


def test_resolve_variant_defaults_to_plain(tmp_path: Path):
    assert resolve_variant(tmp_path) == "plain"  # no context.json => safe default
