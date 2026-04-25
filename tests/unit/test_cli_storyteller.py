"""Unit tests for cli_storyteller — no API calls."""
import json

# ---------------------------------------------------------------------------
# _parse_storytell_issues
# ---------------------------------------------------------------------------

def test_parse_minor_issue():
    from pipeline.cli_storyteller import _parse_storytell_issues
    raw = "ISSUE|s3|MINOR|原本的句子。|建議的句子。|缺少過渡語"
    issues = _parse_storytell_issues(raw)
    assert len(issues) == 1
    assert issues[0]["scene_id"] == "s3"
    assert issues[0]["severity"] == "MINOR"
    assert issues[0]["original"] == "原本的句子。"
    assert issues[0]["suggested"] == "建議的句子。"
    assert issues[0]["reason"] == "缺少過渡語"


def test_parse_major_issue():
    from pipeline.cli_storyteller import _parse_storytell_issues
    raw = "ISSUE|s7|MAJOR|原文。|改寫建議。|敘事角度改變"
    issues = _parse_storytell_issues(raw)
    assert issues[0]["severity"] == "MAJOR"


def test_parse_ok_returns_empty():
    from pipeline.cli_storyteller import _parse_storytell_issues
    assert _parse_storytell_issues("OK") == []


def test_parse_ignores_non_issue_lines():
    from pipeline.cli_storyteller import _parse_storytell_issues
    raw = "這是一些說明文字\nISSUE|s1|MINOR|原文|建議|原因\n另一行"
    issues = _parse_storytell_issues(raw)
    assert len(issues) == 1


def test_parse_multiple_issues():
    from pipeline.cli_storyteller import _parse_storytell_issues
    raw = (
        "ISSUE|s2|MINOR|原文A|建議A|原因A\n"
        "ISSUE|s5|MAJOR|原文B|建議B|原因B\n"
        "ISSUE|s9|MINOR|原文C|建議C|原因C"
    )
    issues = _parse_storytell_issues(raw)
    assert len(issues) == 3
    assert issues[1]["severity"] == "MAJOR"


# ---------------------------------------------------------------------------
# _format_for_storytell
# ---------------------------------------------------------------------------

def test_format_for_storytell_includes_all_scenes(tmp_path):
    from pipeline.cli_storyteller import _format_for_storytell

    sb = {
        "version": 1, "format": "storyboard_v1",
        "target_duration_sec": 300, "aspect_ratio": "9:16", "theme": {},
        "scenes": [
            {
                "id": "s1", "section": "hook", "narration": "第一段旁白。",
                "narration_est_sec": 5, "facts_ref": [], "visual": {},
                "overlay": {}, "pause_after_sec": 0.5,
            },
            {
                "id": "s2", "section": "body", "narration": "第二段旁白。",
                "narration_est_sec": 5, "facts_ref": [], "visual": {},
                "overlay": {}, "pause_after_sec": 0.5,
            },
        ],
    }
    p = tmp_path / "storyboard.json"
    p.write_text(json.dumps(sb), encoding="utf-8")

    result = _format_for_storytell(p)
    assert "[s1]" in result
    assert "第一段旁白。" in result
    assert "[s2]" in result
    assert "第二段旁白。" in result


# ---------------------------------------------------------------------------
# apply_storytell_issues
# ---------------------------------------------------------------------------

def test_apply_minor_replaces_narration(tmp_path):
    from pipeline.cli_storyteller import apply_storytell_issues

    sb = {
        "version": 1, "format": "storyboard_v1",
        "target_duration_sec": 300, "aspect_ratio": "9:16", "theme": {},
        "scenes": [
            {
                "id": "s3", "section": "body", "narration": "原本的句子。後面的文字。",
                "narration_est_sec": 5, "facts_ref": [], "visual": {},
                "overlay": {}, "pause_after_sec": 0.5,
            },
        ],
    }
    p = tmp_path / "storyboard.json"
    p.write_text(json.dumps(sb), encoding="utf-8")

    issues = [{"scene_id": "s3", "severity": "MINOR",
               "original": "原本的句子。", "suggested": "改寫後的句子。", "reason": "過渡"}]
    applied = apply_storytell_issues(p, issues)

    data = json.loads(p.read_text(encoding="utf-8"))
    assert applied == 1
    assert "改寫後的句子。" in data["scenes"][0]["narration"]
    assert "原本的句子。" not in data["scenes"][0]["narration"]


def test_apply_skips_when_original_not_found(tmp_path):
    from pipeline.cli_storyteller import apply_storytell_issues

    sb = {
        "version": 1, "format": "storyboard_v1",
        "target_duration_sec": 300, "aspect_ratio": "9:16", "theme": {},
        "scenes": [
            {
                "id": "s1", "section": "hook", "narration": "完全不同的文字。",
                "narration_est_sec": 5, "facts_ref": [], "visual": {},
                "overlay": {}, "pause_after_sec": 0.5,
            },
        ],
    }
    p = tmp_path / "storyboard.json"
    p.write_text(json.dumps(sb), encoding="utf-8")

    issues = [{"scene_id": "s1", "severity": "MINOR",
               "original": "不存在的原文。", "suggested": "新文字。", "reason": "test"}]
    applied = apply_storytell_issues(p, issues)
    assert applied == 0
