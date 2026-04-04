import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pipeline.knowledge import Knowledge
from pipeline.stages.direct import DirectStage, build_direct_prompt
from pipeline.storyboard import Storyboard


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
