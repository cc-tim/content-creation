import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pipeline.stages.scriptwrite import (
    ScriptwriteStage,
    build_scriptwrite_prompt,
    parse_script_markers,
)


@pytest.fixture
def scriptwrite_fixture() -> dict:
    path = Path(__file__).parent.parent / "fixtures" / "claude_scriptwrite_response.json"
    return json.loads(path.read_text())


def test_build_scriptwrite_prompt():
    prompt = build_scriptwrite_prompt(
        story_structure={"hook": "test", "beats": []},
        knowledge_graph={"entities": [], "conflicts": []},
        locale="zh-TW",
    )
    assert "zh-TW" in prompt or "Traditional Chinese" in prompt
    assert "NOT" in prompt or "not translation" in prompt.lower() or "原創" in prompt


def test_parse_script_markers():
    script = "[HOOK]\n[CLIP:01:23-01:35]\n一段文字\n[OVERLAY:map:Texas]\n更多文字"
    markers = parse_script_markers(script)
    sections = [m for m in markers if m["type"] == "section"]
    clips = [m for m in markers if m["type"] == "clip"]
    overlays = [m for m in markers if m["type"] == "overlay"]
    narration = [m for m in markers if m["type"] == "narration"]
    assert len(sections) == 1
    assert sections[0]["value"] == "HOOK"
    assert len(clips) == 1
    assert len(overlays) == 1
    assert len(narration) >= 1


async def test_scriptwrite_produces_script(sample_context, scriptwrite_fixture):
    sample_context.story_structure = {"hook": "test", "beats": []}
    sample_context.knowledge_graph = {"entities": [], "conflicts": []}
    sample_context.clip_timestamps = [(5, 20), (120, 135)]

    stage = ScriptwriteStage()
    assert stage.name == "scriptwrite"

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=scriptwrite_fixture["script"])]

    with patch("pipeline.stages.scriptwrite.get_anthropic_client") as mock_client_fn:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_client_fn.return_value = mock_client

        ctx = await stage.run(sample_context)

    assert ctx.script_path is not None
    assert ctx.script_path.exists()
    script_text = ctx.script_path.read_text()
    assert "[HOOK]" in script_text
    assert "[CLIP:" in script_text
