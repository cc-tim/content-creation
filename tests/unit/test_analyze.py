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


from pipeline.stages.analyze import _format_timestamped_transcript


def test_format_timestamped_transcript_basic():
    data = [
        {"text": "Hello world.", "start": 0.08, "duration": 4.16},
        {"text": "How are you?", "start": 4.24, "duration": 3.00},
    ]
    result = _format_timestamped_transcript(data)
    assert "[0.08s–4.24s] Hello world." in result
    assert "[4.24s–7.24s] How are you?" in result


def test_format_timestamped_transcript_merges_mid_sentence():
    # Two entries — first has no sentence-ending punctuation → should merge
    data = [
        {"text": "Mrs. Henry, excuse me. You brought this", "start": 0.08, "duration": 4.16},
        {"text": "case before the court.", "start": 4.24, "duration": 3.00},
    ]
    result = _format_timestamped_transcript(data)
    lines = [l for l in result.splitlines() if l]
    assert len(lines) == 1
    assert lines[0].startswith("[0.08s–")
    assert "Mrs. Henry" in lines[0]
    assert "court." in lines[0]


def test_format_timestamped_transcript_skips_blank_entries():
    data = [
        {"text": "First sentence.", "start": 0.0, "duration": 3.0},
        {"text": "", "start": 3.0, "duration": 2.0},
        {"text": "Second sentence.", "start": 5.0, "duration": 3.0},
    ]
    result = _format_timestamped_transcript(data)
    lines = [l for l in result.splitlines() if l]
    assert len(lines) == 2


def test_build_analysis_prompt_with_transcript_data():
    data = [{"text": "Officer Johnson arrested the suspect.", "start": 1.0, "duration": 3.0}]
    prompt = build_analysis_prompt(
        "Officer Johnson arrested the suspect.",
        "https://youtube.com/watch?v=test",
        "Test Video",
        transcript_data=data,
    )
    assert "[1.00s–4.00s]" in prompt
    assert "timestamps in seconds" in prompt


def test_build_analysis_prompt_without_transcript_data_unchanged():
    # Existing behaviour preserved when transcript_data is None
    prompt = build_analysis_prompt(
        "Plain text transcript.",
        "https://youtube.com/watch?v=test",
        "Test Video",
    )
    assert "Plain text transcript." in prompt
    assert "timestamps in seconds" not in prompt


async def test_analyze_uses_structured_transcript_when_available(
    sample_context, analysis_fixture, tmp_path
):
    """AnalyzeStage passes transcript_data to build_analysis_prompt when transcript.json exists."""
    # Set up transcript.json in the project dir
    source_dir = sample_context.work_dir / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    transcript_path = source_dir / "transcript.json"
    transcript_data = [
        {"text": "Officer Johnson arrested the suspect.", "start": 1.0, "duration": 3.0},
        {"text": "He was charged with theft.", "start": 4.0, "duration": 2.5},
    ]
    transcript_path.write_text(
        json.dumps(transcript_data, ensure_ascii=False), encoding="utf-8"
    )
    sample_context.transcript_text = "Officer Johnson arrested the suspect. He was charged with theft."
    sample_context.transcript_path = transcript_path

    stage = AnalyzeStage()

    captured_prompt: list[str] = []

    def mock_create(**kwargs):
        captured_prompt.append(kwargs["messages"][0]["content"])
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(analysis_fixture))]
        return mock_response

    with patch("pipeline.stages.analyze.get_anthropic_client") as mock_client_fn:
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = mock_create
        mock_client_fn.return_value = mock_client
        await stage.run(sample_context)

    prompt = captured_prompt[0]
    assert "[1.00s–4.00s]" in prompt          # structured format used
    assert "timestamps in seconds" in prompt
