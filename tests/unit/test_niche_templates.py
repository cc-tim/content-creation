from pipeline.niche_templates import NicheTemplate, load_niche_template, save_niche_template


def test_load_parenting_template():
    t = load_niche_template("parenting")
    assert t is not None
    assert t.niche == "parenting"
    assert t.intro_type == "generated_image"
    assert t.visual_style  # non-empty
    assert t.medium_hint == "soft sketch lines, hand-drawn warmth"
    assert t.palette == "cream background, muted earth tones"
    assert (
        t.subject_bias
        == "cozy domestic scenes, consistent warm family home, "
        "same parent-child duo across scenes in everyday moments"
    )
    assert t.universal_rules == "no clutter, no text in images"
    assert t.anchor_prompt  # non-empty


def test_load_true_crime_template_split_fields():
    t = load_niche_template("true-crime")
    assert t is not None
    assert t.medium_hint == "cinematic still, documentary aesthetic"
    assert t.palette == "dramatic lighting, high contrast, desaturated"
    assert t.subject_bias == ""
    assert t.universal_rules == ""
    assert t.visual_style == "dramatic lighting, high contrast, desaturated"


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
            medium_hint="minimal sketch",
            palette="warm gray",
            subject_bias="same narrator",
            universal_rules="no text in images",
        )
        save_niche_template(t)
        loaded = load_niche_template("test")
        assert loaded is not None
        assert loaded.intro_type == "text_card"
        assert loaded.visual_style == "minimal sketch"
        assert loaded.medium_hint == "minimal sketch"
        assert loaded.palette == "warm gray"
        assert loaded.subject_bias == "same narrator"
        assert loaded.universal_rules == "no text in images"
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


def test_legacy_parenting_visual_style_auto_split(tmp_path):
    import pipeline.niche_templates as nt_mod
    original = nt_mod.TEMPLATES_PATH
    nt_mod.TEMPLATES_PATH = tmp_path / "legacy_templates.toml"
    nt_mod.TEMPLATES_PATH.write_text(
        """
[parenting]
intro_type = "generated_image"
intro_prompt_hint = "parenting hint"
visual_style = "cozy domestic scenes, consistent warm family home, soft sketch lines, cream background, muted earth tones, same parent-child duo across scenes in everyday moments, hand-drawn warmth, no clutter, no text in images"
anchor_prompt = "anchor"
""",
        encoding="utf-8",
    )
    try:
        loaded = load_niche_template("parenting")
        assert loaded is not None
        assert loaded.medium_hint == "soft sketch lines, hand-drawn warmth"
        assert loaded.palette == "cream background, muted earth tones"
        assert (
            loaded.subject_bias
            == "cozy domestic scenes, consistent warm family home, "
            "same parent-child duo across scenes in everyday moments"
        )
        assert loaded.universal_rules == "no clutter, no text in images"
    finally:
        nt_mod.TEMPLATES_PATH = original


def test_legacy_true_crime_visual_style_auto_split(tmp_path):
    import pipeline.niche_templates as nt_mod
    original = nt_mod.TEMPLATES_PATH
    nt_mod.TEMPLATES_PATH = tmp_path / "legacy_templates.toml"
    nt_mod.TEMPLATES_PATH.write_text(
        """
[true-crime]
intro_type = "text_card"
intro_prompt_hint = "crime hint"
visual_style = "cinematic still, dramatic lighting, documentary aesthetic, high contrast, desaturated"
anchor_prompt = "anchor"
""",
        encoding="utf-8",
    )
    try:
        loaded = load_niche_template("true-crime")
        assert loaded is not None
        assert loaded.medium_hint == "cinematic still, documentary aesthetic"
        assert loaded.palette == "dramatic lighting, high contrast, desaturated"
        assert loaded.subject_bias == ""
        assert loaded.universal_rules == ""
    finally:
        nt_mod.TEMPLATES_PATH = original
