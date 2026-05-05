from unittest.mock import patch

from pipeline.composer.image import _cache_key, _size_arg, render_generated_image
from pipeline.providers.base import ProviderError, ProviderResult


def test_cache_key_deterministic():
    assert _cache_key("hello") == _cache_key("hello")
    assert _cache_key("hello") != _cache_key("world")


def test_size_arg_aspect_ratios():
    assert _size_arg(1920, 1080) == "1792x1024"
    assert _size_arg(1080, 1920) == "1024x1792"
    assert _size_arg(1024, 1024) == "1024x1024"


def test_render_image_cache_hit(tmp_path):
    """If cached PNG exists, skip provider and use the cached file."""
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


def test_render_image_provider_failure_falls_back_to_text_card(tmp_path):
    """Falls back to themed text card if GenImageProvider raises ProviderError."""
    with (
        patch(
            "pipeline.composer.image.try_chain",
            side_effect=ProviderError("gen-image failed"),
        ),
        patch("pipeline.composer.text_card.render_text_card") as mock_tc,
    ):
        mock_tc.return_value = tmp_path / "s1_visual.mp4"

        render_generated_image(
            visual={"type": "generated_image", "prompt": "failing prompt"},
            duration_sec=8.0,
            width=1280,
            height=720,
            work_dir=tmp_path,
            scene_id="s1",
            scene_narration="這是場景旁白",
        )

    mock_tc.assert_called_once()
    # fallback uses narration text, not the English prompt
    call_visual = mock_tc.call_args[0][0]
    assert "這是場景旁白" in call_visual["text"]


def test_render_generated_image_uses_gen_image_provider(tmp_path):
    """Happy path: GenImageProvider is called with correct size and prompt."""
    captured: dict = {}

    def fake_chain(providers, *, prompt, out_path, size, reference_image=None):
        captured["provider_name"] = providers[0].name
        captured["prompt"] = prompt
        captured["size"] = size
        out_path.write_bytes(b"png")
        return ProviderResult(path=out_path, provider=providers[0].name)

    with (
        patch("pipeline.composer.image.try_chain", side_effect=fake_chain),
        patch("pipeline.composer.image.image_to_video") as mock_itv,
    ):
        mock_itv.return_value = tmp_path / "s1_visual.mp4"

        render_generated_image(
            visual={"type": "generated_image", "prompt": "pencil sketch child alone"},
            duration_sec=5.0,
            width=1920,
            height=1080,
            work_dir=tmp_path,
            scene_id="s1",
        )

    assert "gen-image" in captured["provider_name"]
    assert captured["prompt"] == "pencil sketch child alone"
    assert captured["size"] == "1792x1024"
    mock_itv.assert_called_once()


def test_render_generated_image_respects_tier(tmp_path):
    """image_tier in visual dict flows through to GenImageProvider."""
    captured: dict = {}

    def fake_chain(providers, *, prompt, out_path, size, reference_image=None):
        captured["tier"] = providers[0]._tier
        out_path.write_bytes(b"png")
        return ProviderResult(path=out_path, provider=providers[0].name)

    with (
        patch("pipeline.composer.image.try_chain", side_effect=fake_chain),
        patch("pipeline.composer.image.image_to_video"),
    ):
        render_generated_image(
            visual={"type": "generated_image", "prompt": "test", "image_tier": "production"},
            duration_sec=5.0,
            width=1280,
            height=720,
            work_dir=tmp_path,
            scene_id="s1",
        )

    assert captured["tier"] == "production"
