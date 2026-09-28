import json
from unittest.mock import patch

from pipeline.llm import LLMResult


def _res(text="", data=None):
    return LLMResult(text=text, data=data, model="m", backend="cli")


def test_scriptwrite_uses_creative_tier_and_parses_json():
    from pipeline.stages import scriptwrite
    from pipeline.storyboard import Scene

    scenes = [Scene(id="s1", section="hook", narration="n", narration_est_sec=3.0, visual={"type": "text_card"})]
    with patch("pipeline.llm.complete", return_value=_res('```json\n{"s1": "旁白"}\n```')) as c:
        out = scriptwrite._write_narration_for_locale(scenes, "zh-TW")
    assert out == {"s1": "旁白"} and c.call_args.kwargs["tier"] == "creative"


def test_storyboard_beats_use_creative_tier():
    from pipeline import cli_storyboard

    with patch("pipeline.llm.complete", return_value=_res(json.dumps({"s1": "beat"}))) as c:
        out = cli_storyboard._generate_beats([{"id": "s1", "section": "hook", "narration": "n"}])
    assert out == {"s1": "beat"} and c.call_args.kwargs["tier"] == "creative"


# ── Step 0: fused decorator line in cli_visual_review.py ────────────────────


def test_visual_review_extract_frames_is_registered():
    from typer.testing import CliRunner

    from pipeline.cli_visual_review import visual_review_app

    res = CliRunner().invoke(visual_review_app, ["extract-frames", "--help"])
    assert res.exit_code == 0, res.output


def test_print_visual_issues_table_does_not_raise():
    from pipeline.cli_visual_review import print_visual_issues_table

    print_visual_issues_table([{"scene_id": "s1", "severity": "MINOR", "observation": "o",
                                "suggestion": "s", "reason": "r"}])
