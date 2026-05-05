from unittest.mock import patch

from pipeline.composer.style_anchor import (
    _derive_seed,
    _synthesize_style,
    extract_style_anchor,
)
from pipeline.niche_templates import NicheTemplate


def test_derive_seed_is_deterministic():
    s1 = _derive_seed("1777161293")
    s2 = _derive_seed("1777161293")
    assert s1 == s2
    assert isinstance(s1, int)
    assert 0 <= s1 < 2**32


def test_derive_seed_differs_by_project():
    assert _derive_seed("111") != _derive_seed("222")


def test_synthesize_style_niche_takes_priority():
    template = NicheTemplate(
        niche="parenting",
        intro_type="generated_image",
        intro_prompt_hint="...",
        visual_style="clean educational sketch",
        anchor_prompt="...",
    )
    result = _synthesize_style(template, source_hint="anime style")
    assert "clean educational sketch" in result
    assert result.startswith("clean educational sketch")


def test_synthesize_style_falls_back_without_template():
    result = _synthesize_style(None, source_hint="")
    assert result  # non-empty fallback


def test_extract_style_anchor_uses_cached_anchor(tmp_path):
    anchor_dir = tmp_path / "niche_anchors" / "parenting"
    anchor_dir.mkdir(parents=True)
    anchor_img = anchor_dir / "style_anchor.png"
    anchor_img.write_bytes(b"fake")

    template = NicheTemplate("parenting", "generated_image", "", "clean sketch", "...", "")

    with patch("pipeline.composer.style_anchor.NICHE_ANCHOR_DIR", tmp_path / "niche_anchors"), \
         patch("pipeline.composer.style_anchor._extract_source_frame", return_value=None), \
         patch("pipeline.composer.style_anchor._generate_anchor_image") as mock_gen:
        result = extract_style_anchor(
            project_id="123", niche="parenting", template=template, source_video=None, work_dir=tmp_path
        )
    mock_gen.assert_not_called()  # cache hit — no generation
    assert result.anchor_image == anchor_img
    assert result.style_descriptor == "clean sketch"


def test_extract_style_anchor_generates_anchor_when_missing(tmp_path):
    fake_anchor = tmp_path / "niche_anchors" / "parenting" / "style_anchor.png"
    template = NicheTemplate("parenting", "generated_image", "", "clean sketch", "simple scene", "")

    with patch("pipeline.composer.style_anchor.NICHE_ANCHOR_DIR", tmp_path / "niche_anchors"), \
         patch("pipeline.composer.style_anchor._extract_source_frame", return_value=None), \
         patch("pipeline.composer.style_anchor._generate_anchor_image", return_value=fake_anchor) as mock_gen:
        result = extract_style_anchor(
            project_id="123", niche="parenting", template=template, source_video=None, work_dir=tmp_path
        )
    mock_gen.assert_called_once()
    assert result.anchor_image == fake_anchor
