from unittest.mock import MagicMock, patch

from pipeline.composer.image import _cache_key, render_generated_image
from pipeline.providers.base import ProviderError, ProviderResult


def test_cache_key_deterministic():
    assert _cache_key("hello") == _cache_key("hello")
    assert _cache_key("hello") != _cache_key("world")


def test_render_image_cache_hit(tmp_path):
    """If cached PNG exists, skip provider chain and use the cached file."""
    cache_dir = tmp_path / "image_cache"
    cache_dir.mkdir()
    prompt = "test prompt"
    cached = cache_dir / f"{_cache_key(prompt)}.png"
    cached.write_bytes(b"fake png")

    with (
        patch("pipeline.composer.image.image_to_video") as mock_itv,
        patch("pipeline.composer.image.try_chain") as mock_chain,
    ):
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
    mock_chain.assert_not_called()
    assert result == expected_out


def test_render_image_no_providers_configured(tmp_path):
    """Falls back to text card if neither Gemini nor OpenAI keys are set."""
    with (
        patch("pipeline.composer.image.PipelineConfig") as mock_config_cls,
        patch("pipeline.composer.text_card.render_text_card") as mock_tc,
    ):
        mock_config = MagicMock()
        mock_config.OPENAI_API_KEY = ""
        mock_config.GEMINI_API_KEY = None
        mock_config.IMAGE_PROVIDERS = "gemini,dalle"
        mock_config_cls.return_value = mock_config
        mock_tc.return_value = tmp_path / "s1_visual.mp4"

        render_generated_image(
            visual={"type": "generated_image", "prompt": "some scene"},
            duration_sec=8.0,
            width=1280,
            height=720,
            work_dir=tmp_path,
            scene_id="s1",
        )

    mock_tc.assert_called_once()


def test_render_image_all_providers_fail(tmp_path):
    """Falls back to text card if the provider chain raises ProviderError."""
    with (
        patch("pipeline.composer.image.PipelineConfig") as mock_config_cls,
        patch(
            "pipeline.composer.image.try_chain",
            side_effect=ProviderError("all failed"),
        ),
        patch("pipeline.composer.text_card.render_text_card") as mock_tc,
    ):
        mock_config = MagicMock()
        mock_config.OPENAI_API_KEY = "sk-test"
        mock_config.GEMINI_API_KEY = "gem-test"
        mock_config.IMAGE_PROVIDERS = "gemini,dalle"
        mock_config_cls.return_value = mock_config
        mock_tc.return_value = tmp_path / "s1_visual.mp4"

        render_generated_image(
            visual={"type": "generated_image", "prompt": "failing prompt"},
            duration_sec=8.0,
            width=1280,
            height=720,
            work_dir=tmp_path,
            scene_id="s1",
        )

    mock_tc.assert_called_once()


def test_render_generated_image_uses_provider_chain(tmp_path):
    """Happy path: provider chain is called with cache path and aspect-aware size."""
    captured: dict = {}

    def fake_chain(providers, *, prompt, out_path, size, reference_image=None):
        captured["provider_count"] = len(providers)
        captured["prompt"] = prompt
        captured["out_path"] = out_path
        captured["size"] = size
        captured["reference_image"] = reference_image
        out_path.write_bytes(b"png")
        return ProviderResult(path=out_path, provider="gemini")

    with (
        patch("pipeline.composer.image.PipelineConfig") as mock_config_cls,
        patch("pipeline.composer.image.try_chain", side_effect=fake_chain),
        patch("pipeline.composer.image.image_to_video") as mock_itv,
    ):
        mock_config = MagicMock()
        mock_config.OPENAI_API_KEY = "sk-test"
        mock_config.GEMINI_API_KEY = "gem-test"
        mock_config.IMAGE_PROVIDERS = "gemini,dalle"
        mock_config_cls.return_value = mock_config
        mock_itv.return_value = tmp_path / "s1_visual.mp4"

        render_generated_image(
            visual={"type": "generated_image", "prompt": "neon city skyline"},
            duration_sec=5.0,
            width=1920,
            height=1080,
            work_dir=tmp_path,
            scene_id="s1",
        )

    assert captured["provider_count"] == 2
    assert captured["prompt"] == "neon city skyline"
    assert captured["size"] == "1792x1024"  # landscape
    assert (tmp_path / "image_cache").exists()
    mock_itv.assert_called_once()


def test_dalle_size_aspect_ratios(tmp_path):
    """Portrait, square, and landscape prompts should pick the correct DALL-E size."""
    from pipeline.composer.image import _dalle_size

    assert _dalle_size(1920, 1080) == "1792x1024"
    assert _dalle_size(1080, 1920) == "1024x1792"
    assert _dalle_size(1024, 1024) == "1024x1024"
