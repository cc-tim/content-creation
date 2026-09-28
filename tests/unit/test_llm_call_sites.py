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
    from pipeline.cli_visual_review import visual_review_app

    names = [c.name for c in visual_review_app.registered_commands]
    assert "extract-frames" in names, names


def test_visual_review_extract_frames_reachable_via_top_level_app():
    from typer.testing import CliRunner

    from pipeline.cli import app

    res = CliRunner().invoke(app, ["visual-review", "extract-frames", "--help"])
    assert res.exit_code == 0, res.output
    assert "extract-frames" in res.output or "Extract a midpoint frame" in res.output, res.output


def test_print_visual_issues_table_does_not_raise():
    from pipeline.cli_visual_review import print_visual_issues_table

    print_visual_issues_table([{"scene_id": "s1", "severity": "MINOR", "observation": "o",
                                "suggestion": "s", "reason": "r"}])


# ── Step 1: check-tier call sites ────────────────────────────────────────────


def _png(path):
    from PIL import Image
    Image.new("RGB", (16, 16), (200, 30, 30)).save(path)
    return path


def test_proofread_uses_check_tier_with_its_system_prompt(tmp_path):
    from pipeline import cli_proofread

    sb = tmp_path / "storyboard.json"
    sb.write_text(json.dumps({"scenes": [{"id": "s1", "section": "hook", "narration": "你好",
                                          "narration_est_sec": 2.0, "visual": {"type": "text_card"}}]}),
                  encoding="utf-8")
    with patch("pipeline.llm.complete", return_value=_res("OK")) as c:
        assert cli_proofread.proofread_storyboard(sb) == []
    kw = c.call_args.kwargs
    assert kw["tier"] == "check" and kw["system"].startswith(cli_proofread._SYSTEM_PROMPT)


def test_style_anchor_sends_one_image_then_text(tmp_path):
    from pipeline.composer import style_anchor

    frame = _png(tmp_path / "f.jpg")
    with patch("pipeline.llm.complete", return_value=_res("high\nflat ink, warm palette")) as c:
        assert style_anchor._assess_source(frame) == ("high", "flat ink, warm palette")
    blocks = c.call_args.args[0]
    assert [b["type"] for b in blocks] == ["image", "text"] and c.call_args.kwargs["tier"] == "check"


def test_style_anchor_skips_blank_lines_in_the_answer(tmp_path):
    from pipeline.composer import style_anchor

    frame = _png(tmp_path / "f.jpg")
    with patch("pipeline.llm.complete", return_value=_res("Medium\n\nSerif typography, warm palette")):
        assert style_anchor._assess_source(frame) == ("medium", "Serif typography, warm palette")


def test_style_anchor_stays_advisory_on_llm_error(tmp_path):
    from pipeline.composer import style_anchor
    from pipeline.llm import LLMError

    with patch("pipeline.llm.complete", side_effect=LLMError("style_anchor", "quota")):
        assert style_anchor._assess_source(_png(tmp_path / "f.jpg")) == ("medium", "")


def test_storytell_uses_check_tier(tmp_path):
    from pipeline import cli_storyteller

    sb = tmp_path / "storyboard.json"
    sb.write_text(json.dumps({"scenes": [{"id": "s1", "section": "hook", "narration": "第一段旁白。",
                                          "narration_est_sec": 5.0}]}),
                  encoding="utf-8")
    with patch("pipeline.llm.complete", return_value=_res("OK")) as c:
        assert cli_storyteller.storytell_storyboard(sb) == []
    kw = c.call_args.kwargs
    assert kw["tier"] == "check" and kw["system"] == cli_storyteller._SYSTEM_PROMPT


def test_call_haiku_rewrite_uses_check_tier():
    from pipeline.cli_mla import _Offender, call_haiku_rewrite

    offenders = [_Offender(scene_id="s1", primary_text="繁體中文文字", primary_ms=5_000,
                            secondary_text="Long English text here", secondary_ms=8_000,
                            secondary_words=4, target_words=2, direction="over")]
    with patch("pipeline.llm.complete", return_value=_res("s1|Short text")) as c:
        out = call_haiku_rewrite(offenders, "zh-TW")
    assert out == {"s1": "Short text"}
    assert c.call_args.kwargs["tier"] == "check"


def test_check_alignment_uses_check_tier_and_sends_image(tmp_path):
    from pipeline import cli_image_alignment

    img = _png(tmp_path / "scene.png")
    sb = tmp_path / "storyboard.json"
    sb.write_text(json.dumps({"scenes": [{"id": "s1", "section": "hook", "narration": "narration text",
                                          "narration_est_sec": 2.0,
                                          "visual": {"type": "image", "path": str(img)}}]}),
                  encoding="utf-8")
    with patch("pipeline.llm.complete", return_value=_res("OK")) as c:
        assert cli_image_alignment.check_alignment(tmp_path) == []
    blocks = c.call_args.args[0]
    assert any(b["type"] == "image" for b in blocks)
    assert c.call_args.kwargs["tier"] == "check"


def test_review_visual_fit_uses_check_tier_and_sends_image(tmp_path):
    from pipeline import cli_visual_review

    work_dir = tmp_path
    sb = work_dir / "storyboard.json"
    sb.write_text(json.dumps({"scenes": [{"id": "s1", "section": "hook", "narration": "n",
                                          "narration_est_sec": 2.0, "visual": {"type": "text_card"}}]}),
                  encoding="utf-8")
    frames_dir = work_dir / "compose" / "scenes" / "_review_frames"
    frames_dir.mkdir(parents=True)
    _png(frames_dir / "s1.png")
    with patch("pipeline.llm.complete", return_value=_res("OK")) as c:
        assert cli_visual_review.review_visual_fit(work_dir) == []
    blocks = c.call_args.args[0]
    assert any(b["type"] == "image" for b in blocks)
    assert c.call_args.kwargs["tier"] == "check"
