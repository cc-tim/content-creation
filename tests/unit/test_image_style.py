from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest


# Minimal valid 1x1 white PNG bytes
_FAKE_PNG = (
    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
    b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00'
    b'\x00\x11\x00\x01\x1b\xb0\xa4G\x00\x00\x00\x00IEND\xaeB`\x82'
)


def test_style_prefix_prepended_to_prompt(tmp_path):
    from pipeline.composer.image import render_generated_image

    captured = {}

    def fake_try_chain(providers, prompt, out_path, size):
        captured["prompt"] = prompt
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(_FAKE_PNG)
        return MagicMock(provider="test")

    visual = {"type": "generated_image", "prompt": "parent and child"}
    with patch("pipeline.composer.image.try_chain", side_effect=fake_try_chain), \
         patch("pipeline.composer.image.image_to_video"):
        render_generated_image(
            visual, 5.0, 1280, 720, tmp_path, "s1",
            style_prefix="clean sketch style",
        )
    assert "clean sketch style" in captured["prompt"]
    assert "parent and child" in captured["prompt"]
    # style prefix comes before the original prompt
    assert captured["prompt"].index("clean sketch style") < captured["prompt"].index("parent and child")


def test_seed_included_in_cache_key():
    from pipeline.composer.image import _cache_key_with_seed

    key_no_seed = _cache_key_with_seed("hello", None)
    key_seed_1 = _cache_key_with_seed("hello", 42)
    key_seed_2 = _cache_key_with_seed("hello", 99)

    assert key_no_seed != key_seed_1
    assert key_seed_1 != key_seed_2
    assert _cache_key_with_seed("hello", 42) == key_seed_1  # deterministic


def test_no_style_prefix_uses_original_prompt(tmp_path):
    from pipeline.composer.image import render_generated_image

    captured = {}

    def fake_try_chain(providers, prompt, out_path, size):
        captured["prompt"] = prompt
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(_FAKE_PNG)
        return MagicMock(provider="test")

    visual = {"type": "generated_image", "prompt": "original prompt"}
    with patch("pipeline.composer.image.try_chain", side_effect=fake_try_chain), \
         patch("pipeline.composer.image.image_to_video"):
        render_generated_image(visual, 5.0, 1280, 720, tmp_path, "s2")
    assert captured["prompt"] == "original prompt"


def test_production_tier_used_when_style_prefix_set(tmp_path):
    from pipeline.composer.image import render_generated_image
    from pipeline.providers.gen_image import GenImageProvider

    created_tiers = []
    original_init = GenImageProvider.__init__

    def spy_init(self, tier="draft"):
        created_tiers.append(tier)
        original_init(self, tier)

    def fake_chain(providers, prompt, out_path, size):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(_FAKE_PNG)
        return MagicMock(provider="test")

    visual = {"type": "generated_image", "prompt": "test scene"}
    with patch.object(GenImageProvider, "__init__", spy_init), \
         patch("pipeline.composer.image.try_chain", side_effect=fake_chain), \
         patch("pipeline.composer.image.image_to_video"):
        render_generated_image(
            visual, 5.0, 1280, 720, tmp_path, "s3",
            style_prefix="clean sketch",
            seed=12345,
        )
    assert "production" in created_tiers


def test_draft_tier_used_without_style_prefix(tmp_path):
    from pipeline.composer.image import render_generated_image
    from pipeline.providers.gen_image import GenImageProvider

    created_tiers = []
    original_init = GenImageProvider.__init__

    def spy_init(self, tier="draft"):
        created_tiers.append(tier)
        original_init(self, tier)

    def fake_chain(providers, prompt, out_path, size):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(_FAKE_PNG)
        return MagicMock(provider="test")

    visual = {"type": "generated_image", "prompt": "test scene"}
    with patch.object(GenImageProvider, "__init__", spy_init), \
         patch("pipeline.composer.image.try_chain", side_effect=fake_chain), \
         patch("pipeline.composer.image.image_to_video"):
        render_generated_image(visual, 5.0, 1280, 720, tmp_path, "s4")
    assert "draft" in created_tiers


def test_theme_visual_style_roundtrip():
    from pipeline.storyboard import Theme
    t = Theme(visual_style="warm semi-realistic, soft digital painting")
    d = t.to_dict()
    assert d["visual_style"] == "warm semi-realistic, soft digital painting"
    t2 = Theme.from_dict(d)
    assert t2.visual_style == "warm semi-realistic, soft digital painting"


def test_theme_visual_style_default_empty():
    from pipeline.storyboard import Theme
    assert Theme().visual_style == ""


def test_theme_from_dict_ignores_unknown_fields():
    from pipeline.storyboard import Theme
    t = Theme.from_dict({"background": "#fff", "visual_style": "warm", "unknown_field": "x"})
    assert t.visual_style == "warm"
