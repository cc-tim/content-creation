import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pipeline.knowledge import Knowledge
from pipeline.stages.direct import DirectStage, build_direct_prompt
from pipeline.storyboard import Storyboard

# generate_shorts_storyboards is imported inside the test to avoid top-level import issues


@pytest.fixture
def direct_fixture() -> dict:
    path = Path(__file__).parent.parent / "fixtures" / "sample_direct_response.json"
    return json.loads(path.read_text())


@pytest.fixture
def sample_knowledge() -> Knowledge:
    path = Path(__file__).parent.parent / "fixtures" / "sample_knowledge.json"
    return Knowledge.load(path)


def test_build_direct_prompt_standard(sample_knowledge):
    prompt = build_direct_prompt(sample_knowledge, "zh-TW", "standard", "dramatic")
    assert "Traditional Chinese" in prompt
    assert "hook" in prompt
    assert "climax" in prompt
    assert "facts" in prompt.lower()


def test_build_direct_prompt_short(sample_knowledge):
    prompt = build_direct_prompt(sample_knowledge, "zh-TW", "short", "educational")
    assert "Shorts" in prompt or "30-60" in prompt
    assert "punchline" in prompt
    assert "2-4 scenes" in prompt


async def test_direct_outputs_storyboard(sample_context, direct_fixture):
    # Set up knowledge.json
    knowledge_path = sample_context.work_dir / "knowledge.json"
    fixture_path = Path(__file__).parent.parent / "fixtures" / "sample_knowledge.json"
    knowledge_path.write_text(fixture_path.read_text())
    sample_context.knowledge_path = knowledge_path

    stage = DirectStage()
    assert stage.name == "direct"

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps(direct_fixture))]

    with patch("pipeline.stages.direct.get_anthropic_client") as mock_client_fn:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_client_fn.return_value = mock_client

        ctx = await stage.run(sample_context)

    # Storyboard output
    assert ctx.storyboard_path is not None
    assert ctx.storyboard_path.exists()
    assert ctx.storyboard_path.name == "storyboard_zh-TW.json"
    sb = Storyboard.load(ctx.storyboard_path)
    assert len(sb.scenes) == 4
    assert sb.scenes[0].section == "hook"
    assert sb.format == "standard"

    # Script derived from storyboard
    assert ctx.script_path is not None
    assert ctx.script_path.exists()
    script = ctx.script_path.read_text()
    assert "[HOOK]" in script
    assert "時速超過160" in script
    # Script should NOT contain visual data
    assert '"type": "clip"' not in script

    # Backwards compat
    assert ctx.story_structure is not None

    assert sb.title == "美國警匪追逐全記錄"
    assert sb.description.startswith("芝加哥街頭")


async def test_generate_shorts_storyboards(sample_knowledge):
    mock_response_data = {
        "shorts": [
            {
                "fact_id": "f1",
                "scenes": [
                    {
                        "id": "s1",
                        "section": "hook",
                        "narration": "你知道嗎？",
                        "narration_est_sec": 3,
                        "facts_ref": ["f1"],
                        "visual": {"type": "text_card", "text": "冷知識", "background": "#1a1a2e"},
                        "overlay": None,
                        "pause_after_sec": 0,
                    },
                    {
                        "id": "s2",
                        "section": "content",
                        "narration": "解釋內容。",
                        "narration_est_sec": 12,
                        "facts_ref": ["f1"],
                        "visual": {
                            "type": "generated_image",
                            "prompt": "robbery scene",
                            "style": "cinematic",
                        },
                        "overlay": None,
                        "pause_after_sec": 0,
                    },
                    {
                        "id": "s3",
                        "section": "punchline",
                        "narration": "追蹤看更多！",
                        "narration_est_sec": 3,
                        "facts_ref": ["f1"],
                        "visual": {"type": "text_card", "text": "追蹤", "background": "#1a1a2e"},
                        "overlay": None,
                        "pause_after_sec": 0,
                    },
                ],
            },
            {
                "fact_id": "f2",
                "scenes": [
                    {
                        "id": "s1",
                        "section": "hook",
                        "narration": "時速160公里！",
                        "narration_est_sec": 3,
                        "facts_ref": ["f2"],
                        "visual": {
                            "type": "clip",
                            "source": "primary",
                            "start_sec": 90,
                            "end_sec": 100,
                        },
                        "overlay": None,
                        "pause_after_sec": 0,
                    },
                    {
                        "id": "s2",
                        "section": "punchline",
                        "narration": "按讚訂閱！",
                        "narration_est_sec": 3,
                        "facts_ref": ["f2"],
                        "visual": {"type": "text_card", "text": "訂閱", "background": "#1a1a2e"},
                        "overlay": None,
                        "pause_after_sec": 0,
                    },
                ],
            },
        ]
    }

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps(mock_response_data))]

    with patch("pipeline.stages.direct.get_anthropic_client") as mock_client_fn:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_client_fn.return_value = mock_client

        from pipeline.stages.direct import generate_shorts_storyboards

        storyboards = await generate_shorts_storyboards(sample_knowledge, "zh-TW", count=2)

    assert len(storyboards) == 2
    assert storyboards[0].format == "short"
    assert storyboards[0].aspect_ratio == "9:16"
    assert len(storyboards[0].scenes) == 3
    assert storyboards[0].scenes[0].section == "hook"
    assert len(storyboards[1].scenes) == 2


from pathlib import Path as _Path


def test_build_direct_prompt_includes_strategies(sample_knowledge):
    strategies_text = "LOADED STRATEGIES\n\n### test — desc\nHello strategy"
    prompt = build_direct_prompt(
        sample_knowledge, "ja", "standard", "dramatic",
        strategies_text=strategies_text,
    )
    assert "LOADED STRATEGIES" in prompt
    assert "Hello strategy" in prompt


def test_build_direct_prompt_omits_strategies_when_empty(sample_knowledge):
    prompt = build_direct_prompt(
        sample_knowledge, "ja", "standard", "dramatic",
        strategies_text="",
    )
    assert "LOADED STRATEGIES" not in prompt


async def test_direct_stage_injects_reference_storyboard(
    sample_context, direct_fixture, tmp_path
):
    kb = _Path(__file__).parent.parent / "fixtures" / "sample_knowledge.json"
    (sample_context.work_dir / "knowledge.json").write_text(kb.read_text())
    sample_context.knowledge_path = sample_context.work_dir / "knowledge.json"
    sample_context.locale = "ja"

    ref_path = sample_context.work_dir / "storyboard_en.json"
    ref_path.write_text(json.dumps({
        "version": 1,
        "format": "standard",
        "target_duration_sec": 720,
        "aspect_ratio": "16:9",
        "scenes": [
            {"id": "s1", "section": "hook", "narration": "English hook",
             "narration_est_sec": 5, "facts_ref": [], "visual": {"type": "clip"},
             "overlay": None, "pause_after_sec": 0}
        ],
    }))
    sample_context.reference_storyboard_path = ref_path

    stage = DirectStage()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps(direct_fixture))]
    captured = {}

    with patch("pipeline.stages.direct.get_anthropic_client") as mock_client_fn:
        mock_client = MagicMock()

        def _create(**kwargs):
            captured["messages"] = kwargs["messages"]
            return mock_response

        mock_client.messages.create.side_effect = _create
        mock_client_fn.return_value = mock_client
        await stage.run(sample_context)

    prompt_text = captured["messages"][0]["content"]
    assert "REFERENCE STORYBOARD" in prompt_text
    assert "English hook" in prompt_text


async def test_direct_stage_loads_and_injects_strategies(
    sample_context, direct_fixture, tmp_path, monkeypatch
):
    # Minimal knowledge
    kb = _Path(__file__).parent.parent / "fixtures" / "sample_knowledge.json"
    (sample_context.work_dir / "knowledge.json").write_text(kb.read_text())
    sample_context.knowledge_path = sample_context.work_dir / "knowledge.json"
    sample_context.locale = "ja"
    sample_context.source_locale = "US"

    strat_dir = tmp_path / "promos"
    strat_dir.mkdir()
    (strat_dir / "t.md").write_text(
        "---\n"
        "name: test-strat\n"
        "description: test strat desc\n"
        "applies_when:\n"
        "  target_locale_differs_from_source: true\n"
        "---\n"
        "Body of strategy visible in prompt.\n"
    )

    # Patch the DEFAULT_STRATEGIES_DIR used by DirectStage
    import pipeline.strategies as strategies_mod
    monkeypatch.setattr(strategies_mod, "DEFAULT_STRATEGIES_DIR", strat_dir)

    stage = DirectStage()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps(direct_fixture))]
    captured = {}

    with patch("pipeline.stages.direct.get_anthropic_client") as mock_client_fn:
        mock_client = MagicMock()

        def _create(**kwargs):
            captured["messages"] = kwargs["messages"]
            return mock_response

        mock_client.messages.create.side_effect = _create
        mock_client_fn.return_value = mock_client
        await stage.run(sample_context)

    prompt_text = captured["messages"][0]["content"]
    assert "Body of strategy visible in prompt." in prompt_text


async def test_direct_handles_missing_title_description(
    sample_context, direct_fixture
):
    kb = _Path(__file__).parent.parent / "fixtures" / "sample_knowledge.json"
    (sample_context.work_dir / "knowledge.json").write_text(kb.read_text())
    sample_context.knowledge_path = sample_context.work_dir / "knowledge.json"

    # Strip title/description from fixture
    response = dict(direct_fixture)
    response.pop("title", None)
    response.pop("description", None)

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps(response))]

    with patch("pipeline.stages.direct.get_anthropic_client") as mock_client_fn:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_client_fn.return_value = mock_client

        ctx = await DirectStage().run(sample_context)

    sb = Storyboard.load(ctx.storyboard_path)
    assert sb.title is None
    assert sb.description is None
