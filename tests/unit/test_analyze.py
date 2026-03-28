import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pipeline.stages.analyze import AnalyzeStage, build_analysis_prompt


@pytest.fixture
def analysis_fixture() -> dict:
    path = Path(__file__).parent.parent / "fixtures" / "claude_analysis_response.json"
    return json.loads(path.read_text())


def test_build_analysis_prompt():
    prompt = build_analysis_prompt("This is a transcript about a traffic stop in Austin.")
    assert "transcript" in prompt.lower()
    assert "story_structure" in prompt or "story structure" in prompt.lower()
    assert "knowledge_graph" in prompt or "knowledge graph" in prompt.lower()


async def test_analyze_extracts_structure(sample_context, analysis_fixture):
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

    assert ctx.story_structure is not None
    assert "beats" in ctx.story_structure
    assert ctx.knowledge_graph is not None
    assert "entities" in ctx.knowledge_graph
    assert ctx.clip_timestamps is not None
    assert len(ctx.clip_timestamps) > 0
