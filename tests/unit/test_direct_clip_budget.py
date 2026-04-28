from pipeline.stages.direct import build_direct_prompt, _intro_template_block, _validate_clip_budget
from pipeline.niche_templates import NicheTemplate
from pipeline.knowledge import Knowledge, Fact, KnowledgeMeta


def _minimal_knowledge() -> Knowledge:
    meta = KnowledgeMeta(
        source_type="youtube",
        source_url="https://example.com/video",
        title="Test Video",
        locale="zh-TW"
    )
    return Knowledge(meta=meta, facts=[Fact(id="f1", text="test fact", tags=[], source="test")])


def test_clip_budget_instruction_in_prompt():
    k = _minimal_knowledge()
    prompt = build_direct_prompt(
        k, "zh-TW", clip_budget_text="VISUAL BUDGET: at most 12 of 20 scenes may be clip"
    )
    assert "VISUAL BUDGET" in prompt
    assert "12" in prompt


def test_intro_template_block_with_template():
    template = NicheTemplate(
        niche="parenting",
        intro_type="generated_image",
        intro_prompt_hint="parent and child, sketch style",
        visual_style="clean sketch",
        anchor_prompt="...",
    )
    block = _intro_template_block(template)
    assert "s1" in block
    assert "generated_image" in block
    assert "parent and child, sketch style" in block


def test_intro_template_block_without_template():
    block = _intro_template_block(None)
    assert "s1" in block
    assert "clip" in block.lower() or "must not" in block.lower() or "never" in block.lower()


def test_intro_block_in_prompt():
    k = _minimal_knowledge()
    template = NicheTemplate("parenting", "generated_image", "sketch hint", "clean sketch", "...")
    prompt = build_direct_prompt(
        k, "zh-TW",
        intro_template_text=_intro_template_block(template),
    )
    assert "s1" in prompt
    assert "sketch hint" in prompt


def test_validate_clip_budget_returns_warnings():
    scenes = [{"visual": {"type": "clip"}} for _ in range(18)] + \
             [{"visual": {"type": "generated_image"}} for _ in range(2)]
    warnings = _validate_clip_budget(scenes, max_pct=0.60)
    assert warnings
    assert "18" in warnings[0]


def test_validate_clip_budget_ok():
    scenes = [{"visual": {"type": "clip"}} for _ in range(10)] + \
             [{"visual": {"type": "generated_image"}} for _ in range(10)]
    assert _validate_clip_budget(scenes, max_pct=0.60) == []
