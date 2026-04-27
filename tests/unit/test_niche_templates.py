import tomllib
from pathlib import Path
import pytest
from pipeline.niche_templates import NicheTemplate, load_niche_template, save_niche_template


def test_load_parenting_template():
    t = load_niche_template("parenting")
    assert t is not None
    assert t.niche == "parenting"
    assert t.intro_type == "generated_image"
    assert t.visual_style  # non-empty
    assert t.anchor_prompt  # non-empty


def test_load_unknown_niche_returns_none():
    t = load_niche_template("nonexistent_niche_xyz")
    assert t is None


def test_save_and_reload(tmp_path):
    import pipeline.niche_templates as nt_mod
    original = nt_mod.TEMPLATES_PATH
    nt_mod.TEMPLATES_PATH = tmp_path / "test_templates.toml"
    try:
        t = NicheTemplate(
            niche="test",
            intro_type="text_card",
            intro_prompt_hint="A test hint",
            visual_style="minimal sketch",
            anchor_prompt="simple scene",
            rationale="testing",
        )
        save_niche_template(t)
        loaded = load_niche_template("test")
        assert loaded is not None
        assert loaded.intro_type == "text_card"
        assert loaded.visual_style == "minimal sketch"
    finally:
        nt_mod.TEMPLATES_PATH = original


def test_save_preserves_existing(tmp_path):
    import pipeline.niche_templates as nt_mod
    original = nt_mod.TEMPLATES_PATH
    nt_mod.TEMPLATES_PATH = tmp_path / "test_templates.toml"
    try:
        t1 = NicheTemplate("a", "generated_image", "hint a", "style a", "anchor a")
        t2 = NicheTemplate("b", "text_card", "hint b", "style b", "anchor b")
        save_niche_template(t1)
        save_niche_template(t2)
        assert load_niche_template("a") is not None
        assert load_niche_template("b") is not None
    finally:
        nt_mod.TEMPLATES_PATH = original
