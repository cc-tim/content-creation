from unittest.mock import patch, MagicMock
from pathlib import Path

from pipeline.composer.image import render_generated_image, _cache_key


def test_cache_key_deterministic():
    assert _cache_key("hello") == _cache_key("hello")
    assert _cache_key("hello") != _cache_key("world")


def test_render_image_cache_hit(tmp_path):
    """If cached PNG exists, skip API call and use it."""
    cache_dir = tmp_path / "image_cache"
    cache_dir.mkdir()
    prompt = "test prompt"
    from pipeline.composer.image import _cache_key

    cached = cache_dir / f"{_cache_key(prompt)}.png"
    cached.write_bytes(b"fake png")

    with patch("pipeline.composer.image.image_to_video") as mock_itv:
        expected_out = tmp_path / "s1_visual.mp4"
        mock_itv.return_value = expected_out

        result = render_generated_image(
            visual={"type": "generated_image", "prompt": prompt},
            duration_sec=8.0,
            width=1280,
            height=720,
            work_dir=tmp_path,
            scene_id="s1",
        )

    mock_itv.assert_called_once()
    assert result == expected_out


def test_render_image_no_api_key(tmp_path):
    """Falls back to text card if no OpenAI key."""
    with (
        patch("pipeline.composer.image.PipelineConfig") as mock_config_cls,
        patch("pipeline.composer.text_card.render_text_card") as mock_tc,
    ):
        mock_config = MagicMock()
        mock_config.OPENAI_API_KEY = ""
        mock_config_cls.return_value = mock_config
        mock_tc.return_value = tmp_path / "s1_visual.mp4"

        result = render_generated_image(
            visual={"type": "generated_image", "prompt": "some scene"},
            duration_sec=8.0,
            width=1280,
            height=720,
            work_dir=tmp_path,
            scene_id="s1",
        )

    mock_tc.assert_called_once()


def test_render_image_api_failure(tmp_path):
    """Falls back to text card if API call fails."""
    with (
        patch("pipeline.composer.image.PipelineConfig") as mock_config_cls,
        patch(
            "pipeline.composer.image._download_dalle_image",
            side_effect=RuntimeError("API error"),
        ),
        patch("pipeline.composer.text_card.render_text_card") as mock_tc,
    ):
        mock_config = MagicMock()
        mock_config.OPENAI_API_KEY = "sk-test"
        mock_config_cls.return_value = mock_config
        mock_tc.return_value = tmp_path / "s1_visual.mp4"

        result = render_generated_image(
            visual={"type": "generated_image", "prompt": "failing prompt"},
            duration_sec=8.0,
            width=1280,
            height=720,
            work_dir=tmp_path,
            scene_id="s1",
        )

    mock_tc.assert_called_once()
