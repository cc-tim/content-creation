"""Output paths derive from PipelineConfig().OUTPUT_DIR at call time (Sprint 8 audit)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner


def test_gallery_dir_follows_output_dir(monkeypatch, tmp_path):
    from pipeline.utils.gallery import gallery_dir, gallery_index_path

    monkeypatch.setenv("PIPELINE_OUTPUT_DIR", str(tmp_path / "out"))
    assert gallery_dir() == tmp_path / "out" / "gallery"
    assert gallery_index_path() == tmp_path / "out" / "gallery" / "gallery_index.json"


def test_gallery_dir_is_resolved_at_call_time_not_import(monkeypatch, tmp_path):
    from pipeline.utils.gallery import gallery_dir

    monkeypatch.setenv("PIPELINE_OUTPUT_DIR", str(tmp_path / "a"))
    first = gallery_dir()
    monkeypatch.setenv("PIPELINE_OUTPUT_DIR", str(tmp_path / "b"))
    assert gallery_dir() != first


def test_gallery_searcher_defaults_follow_output_dir(monkeypatch, tmp_path):
    from pipeline.utils.gallery import GallerySearcher

    monkeypatch.setenv("PIPELINE_OUTPUT_DIR", str(tmp_path))
    s = GallerySearcher()
    assert s._index_path == tmp_path / "gallery" / "gallery_index.json"
    assert s._gallery_dir == tmp_path / "gallery"


def test_no_import_time_gallery_constant():
    import pipeline.utils.gallery as g

    assert not hasattr(g, "GALLERY_DIR")
    assert not hasattr(g, "GALLERY_INDEX_PATH")


def test_render_scene_generated_image_uses_output_dir_gallery(monkeypatch, tmp_path):
    from pipeline.composer.base import render_scene

    monkeypatch.setenv("PIPELINE_OUTPUT_DIR", str(tmp_path))
    scene = {"id": "s1", "visual": {"type": "generated_image", "prompt": "p"}}
    with patch("pipeline.composer.image.render_generated_image") as rgi:
        render_scene(scene, 3.0, "16:9", tmp_path, theme={})
    assert rgi.call_args.kwargs["gallery_path"] == tmp_path / "gallery" / "gallery_index.json"


def test_render_scene_image_sequence_uses_output_dir_gallery(monkeypatch, tmp_path):
    from pipeline.composer.base import render_scene

    monkeypatch.setenv("PIPELINE_OUTPUT_DIR", str(tmp_path))
    scene = {"id": "s1", "visual": {"type": "image_sequence", "images": []}}
    with patch("pipeline.composer.image_sequence.render_image_sequence") as ris:
        render_scene(scene, 3.0, "16:9", tmp_path, theme={})
    assert ris.call_args.kwargs["gallery_path"] == tmp_path / "gallery" / "gallery_index.json"


def test_write_to_gallery_uses_output_dir(monkeypatch, tmp_path):
    from PIL import Image

    from pipeline.composer.image import _write_to_gallery

    monkeypatch.setenv("PIPELINE_OUTPUT_DIR", str(tmp_path / "out"))
    img = tmp_path / "i.png"
    Image.new("RGB", (4, 4)).save(img)
    index = tmp_path / "out" / "gallery" / "gallery_index.json"
    _write_to_gallery(img, "a prompt", index, "parenting", "narration")
    assert list((tmp_path / "out" / "gallery" / "images").glob("*.png"))


def test_storyboard_migrate_uses_output_dir(monkeypatch, tmp_path):
    from pipeline.cli import app

    out = tmp_path / "out"
    proj = out / "projects" / "p2"
    proj.mkdir(parents=True)
    (proj / "storyboard.json").write_text(json.dumps({"scenes": []}), encoding="utf-8")
    (proj / "context.json").write_text(json.dumps({"locale": "zh-TW"}), encoding="utf-8")
    monkeypatch.setenv("PIPELINE_OUTPUT_DIR", str(out))
    with patch("pipeline.cli_storyboard.migrate_storyboard_file", return_value=True) as m:
        result = CliRunner().invoke(app, ["storyboard", "migrate", "--project-id", "p2"])
    assert result.exit_code == 0, result.output
    assert Path(m.call_args.args[0]) == proj / "storyboard.json"


def test_storyboard_migrate_all_scans_output_dir(monkeypatch, tmp_path):
    from pipeline.cli import app

    out = tmp_path / "out"
    proj = out / "projects" / "p1"
    proj.mkdir(parents=True)
    (proj / "storyboard.json").write_text(json.dumps({"scenes": []}), encoding="utf-8")
    (proj / "context.json").write_text(json.dumps({"locale": "zh-TW"}), encoding="utf-8")
    monkeypatch.setenv("PIPELINE_OUTPUT_DIR", str(out))
    with patch("pipeline.cli_storyboard.migrate_storyboard_file", return_value=False) as m:
        result = CliRunner().invoke(app, ["storyboard", "migrate", "--all"])
    assert result.exit_code == 0, result.output
    m.assert_called_once()
    assert Path(m.call_args.args[0]) == proj / "storyboard.json"
