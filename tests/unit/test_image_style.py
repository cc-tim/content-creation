from unittest.mock import MagicMock, patch

# Minimal valid 1x1 white PNG bytes
_FAKE_PNG = (
    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
    b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00'
    b'\x00\x11\x00\x01\x1b\xb0\xa4G\x00\x00\x00\x00IEND\xaeB`\x82'
)


def test_style_prefix_not_double_prepended(tmp_path):
    """render_generated_image does NOT prepend style_prefix — base.py does that upstream.
    Style is passed in visual.prompt already; style_prefix param is for tier selection only."""
    from pipeline.composer.image import render_generated_image

    captured = {}

    def fake_try_chain(providers, prompt, out_path, size):
        captured["prompt"] = prompt
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(_FAKE_PNG)
        return MagicMock(provider="test")

    # Simulate what base.py does: fold style into the prompt before calling render
    visual = {"type": "generated_image", "prompt": "clean sketch style, parent and child"}
    with patch("pipeline.composer.image.try_chain", side_effect=fake_try_chain), \
         patch("pipeline.composer.image.image_to_video"):
        render_generated_image(
            visual, 5.0, 1280, 720, tmp_path, "s1",
            style_prefix="clean sketch style",
        )
    # prompt is used as-is; no double-prepending
    assert captured["prompt"] == "clean sketch style, parent and child"


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


def test_visual_style_overrides_style_prefix(tmp_path):
    """theme.visual_style wins over theme.style_prefix (niche template)."""
    from unittest.mock import patch
    captured = {}

    def fake_render(visual, duration, width, height, work_dir, scene_id, **kwargs):
        captured["prompt"] = visual.get("prompt", "")
        out = work_dir / f"{scene_id}_visual.mp4"
        out.write_bytes(b"fake")
        return out

    with patch("pipeline.composer.image.render_generated_image", side_effect=fake_render):
        from pipeline.composer.base import render_scene
        render_scene(
            {"id": "s1", "visual": {"type": "generated_image", "prompt": "parent and child"}},
            5.0, "16:9", tmp_path,
            theme={"visual_style": "warm semi-realistic", "style_prefix": "clean sketch"},
        )
    assert "warm semi-realistic" in captured["prompt"]
    assert "clean sketch" not in captured["prompt"]
    assert "parent and child" in captured["prompt"]


def test_style_modifier_appended_after_base_style(tmp_path):
    from unittest.mock import patch
    captured = {}

    def fake_render(visual, duration, width, height, work_dir, scene_id, **kwargs):
        captured["prompt"] = visual.get("prompt", "")
        out = work_dir / f"{scene_id}_visual.mp4"
        out.write_bytes(b"fake")
        return out

    with patch("pipeline.composer.image.render_generated_image", side_effect=fake_render):
        from pipeline.composer.base import render_scene
        render_scene(
            {"id": "s7", "visual": {
                "type": "generated_image",
                "prompt": "parent at door",
                "style_modifier": "darker, tense atmosphere",
            }},
            5.0, "16:9", tmp_path,
            theme={"visual_style": "warm semi-realistic"},
        )
    p = captured["prompt"]
    assert "warm semi-realistic" in p
    assert "darker, tense atmosphere" in p
    assert "parent at door" in p
    # order: base_style, modifier, content
    assert p.index("warm semi-realistic") < p.index("darker, tense atmosphere") < p.index("parent at door")


def test_fallback_to_style_prefix_when_no_visual_style(tmp_path):
    from unittest.mock import patch
    captured = {}

    def fake_render(visual, duration, width, height, work_dir, scene_id, **kwargs):
        captured["prompt"] = visual.get("prompt", "")
        out = work_dir / f"{scene_id}_visual.mp4"
        out.write_bytes(b"fake")
        return out

    with patch("pipeline.composer.image.render_generated_image", side_effect=fake_render):
        from pipeline.composer.base import render_scene
        render_scene(
            {"id": "s1", "visual": {"type": "generated_image", "prompt": "content here"}},
            5.0, "16:9", tmp_path,
            theme={"style_prefix": "clean educational sketch"},
        )
    assert "clean educational sketch" in captured["prompt"]




def test_sidecar_png_written_after_generation(tmp_path):
    from pipeline.composer.image import render_generated_image

    def fake_chain(providers, prompt, out_path, size):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(_FAKE_PNG)
        return MagicMock(provider="test")

    visual = {"type": "generated_image", "prompt": "parent and child"}
    with patch("pipeline.composer.image.try_chain", side_effect=fake_chain), \
         patch("pipeline.composer.image.image_to_video"):
        render_generated_image(visual, 5.0, 1280, 720, tmp_path, "s5")
    assert (tmp_path / "s5_source.png").exists()


def test_restore_override_used_when_present(tmp_path):
    """If {scene_id}_restore.png exists, it's used directly without API call."""
    from pipeline.composer.image import render_generated_image

    restore = tmp_path / "s5_restore.png"
    restore.write_bytes(_FAKE_PNG)
    called = []

    def fake_chain(*a, **kw):
        called.append(True)
        return MagicMock(provider="test")

    with patch("pipeline.composer.image.try_chain", side_effect=fake_chain), \
         patch("pipeline.composer.image.image_to_video"):
        render_generated_image(
            {"type": "generated_image", "prompt": "test"},
            5.0, 1280, 720, tmp_path, "s5",
        )
    assert not called, "API should not be called when restore.png present"
    assert not restore.exists(), "restore.png should be consumed"
    assert (tmp_path / "s5_source.png").exists()


def test_edit_mode_calls_edit_provider(tmp_path):
    from pipeline.composer.image import render_generated_image

    source = tmp_path / "s5_source.png"
    source.write_bytes(_FAKE_PNG)
    captured = {}

    def fake_edit_img2img(image_path, prompt, strength, out_path, size):
        captured["called"] = True
        captured["strength"] = strength
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(_FAKE_PNG)
        from pipeline.providers.base import ProviderResult
        return ProviderResult(path=out_path, provider="fal-img2img")

    mock_provider = MagicMock()
    mock_provider.edit_img2img.side_effect = fake_edit_img2img

    visual = {
        "type": "generated_image",
        "prompt": "parent and child",
        "edit_mode": True,
        "edit_type": "img2img",
        "edit_instruction": "keep composition, fix style",
        "edit_strength": 0.25,
    }
    with patch("pipeline.composer.image.EditImageProvider", return_value=mock_provider), \
         patch("pipeline.composer.image.save_to_history"), \
         patch("pipeline.composer.image.image_to_video"):
        render_generated_image(visual, 5.0, 1280, 720, tmp_path, "s5")

    assert captured.get("called"), "EditImageProvider.edit_img2img should be called"
    assert captured["strength"] == 0.25


def test_edit_mode_falls_through_when_no_source(tmp_path):
    """With edit_mode=True but no source PNG, falls through to normal generation."""
    from pipeline.composer.image import render_generated_image

    called = []

    def fake_chain(providers, prompt, out_path, size):
        called.append(True)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(_FAKE_PNG)
        return MagicMock(provider="test")

    visual = {
        "type": "generated_image",
        "prompt": "test",
        "edit_mode": True,
        "edit_instruction": "fix it",
    }
    with patch("pipeline.composer.image.try_chain", side_effect=fake_chain), \
         patch("pipeline.composer.image.image_to_video"):
        render_generated_image(visual, 5.0, 1280, 720, tmp_path, "s5")
    assert called, "should fall through to normal generation"
