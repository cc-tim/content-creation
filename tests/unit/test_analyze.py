import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pipeline.knowledge import Knowledge
from pipeline.stages.analyze import AnalyzeStage, build_analysis_prompt


@pytest.fixture
def analysis_fixture() -> dict:
    path = Path(__file__).parent.parent / "fixtures" / "claude_analysis_response.json"
    return json.loads(path.read_text())


def test_build_analysis_prompt():
    prompt = build_analysis_prompt(
        "This is a transcript.",
        "https://youtube.com/watch?v=test",
        "Test Video",
    )
    assert "transcript" in prompt.lower()
    assert "facts" in prompt.lower()
    assert "entities" in prompt.lower()
    assert "timeline" in prompt.lower()


async def test_analyze_outputs_knowledge_json(sample_context, analysis_fixture):
    sample_context.transcript_text = "Officer Johnson responded to a call..."
    stage = AnalyzeStage()
    assert stage.name == "analyze"

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps(analysis_fixture))]

    with patch("pipeline.stages.analyze.get_anthropic_client") as mock_client_fn:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_client_fn.return_value = mock_client

        ctx = await stage.run(sample_context)

    # Layer 1 output
    assert ctx.knowledge_path is not None
    assert ctx.knowledge_path.exists()
    knowledge = Knowledge.load(ctx.knowledge_path)
    assert len(knowledge.facts) == 3
    assert len(knowledge.entities) == 2
    assert knowledge.facts[0].id == "f1"

    # Backwards compat
    assert ctx.story_structure is not None
    assert ctx.knowledge_graph is not None
