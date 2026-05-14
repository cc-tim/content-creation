from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from PIL import Image

from pipeline.composer.base import render_scene


def _image(path: Path, color: str = "white") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (80, 60), color).save(path)
    return path


def test_article_image_uses_existing_refit_path(tmp_path: Path):
    raw = _image(tmp_path / "raw.png")
    refit = _image(tmp_path / "refit.png", "blue")
    output = tmp_path / "scene.mp4"

    with patch("pipeline.composer.base.image_to_video", return_value=output) as mock_image_to_video:
        result = render_scene(
            {
                "id": "s1",
                "visual": {
                    "type": "article_image",
                    "path": str(raw),
                    "refit_path": str(refit),
                },
            },
            duration_sec=3,
            aspect_ratio="16:9",
            work_dir=tmp_path,
            theme={},
        )

    assert result == output
    assert mock_image_to_video.call_args.args[0] == refit
    assert mock_image_to_video.call_args.args[3:5] == (1280, 720)


def test_article_image_renders_to_open_book_inset_size(tmp_path: Path):
    raw = _image(tmp_path / "raw.png")
    refit = _image(tmp_path / "refit.png", "blue")
    output = tmp_path / "scene.mp4"

    with patch("pipeline.composer.base.image_to_video", return_value=output) as mock_image_to_video:
        render_scene(
            {
                "id": "s1",
                "visual": {
                    "type": "article_image",
                    "path": str(raw),
                    "refit_path": str(refit),
                },
            },
            duration_sec=3,
            aspect_ratio="16:9",
            work_dir=tmp_path,
            theme={"frame_style": "open_book_page"},
        )

    assert mock_image_to_video.call_args.args[0] == refit
    assert mock_image_to_video.call_args.args[3:5] == (947, 484)


def test_article_image_falls_back_when_refit_path_missing(tmp_path: Path):
    raw = _image(tmp_path / "raw.png")
    output = tmp_path / "scene.mp4"

    with patch("pipeline.composer.base.image_to_video", return_value=output) as mock_image_to_video:
        render_scene(
            {
                "id": "s1",
                "visual": {
                    "type": "article_image",
                    "path": str(raw),
                    "refit_path": str(tmp_path / "missing.png"),
                },
            },
            duration_sec=3,
            aspect_ratio="16:9",
            work_dir=tmp_path,
            theme={},
        )

    assert mock_image_to_video.call_args.args[0] == raw


def test_image_visual_type_uses_same_file_backed_branch(tmp_path: Path):
    raw = _image(tmp_path / "raw.png")
    refit = _image(tmp_path / "refit.png", "green")
    output = tmp_path / "scene.mp4"

    with patch("pipeline.composer.base.image_to_video", return_value=output) as mock_image_to_video:
        result = render_scene(
            {"id": "s2", "visual": {"type": "image", "path": str(raw), "refit_path": str(refit)}},
            duration_sec=3,
            aspect_ratio="16:9",
            work_dir=tmp_path,
            theme={},
        )

    assert result == output
    assert mock_image_to_video.call_args.args[0] == refit
