import json
from pathlib import Path

from pipeline.cli_storyboard import migrate_storyboard_file


def _write(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_migrate_folds_narration_en(tmp_path: Path):
    sb_path = tmp_path / "storyboard.json"
    _write(sb_path, {
        "version": 1,
        "scenes": [
            {"id": "s1", "section": "hook", "narration": "主要",
             "narration_en": "primary", "narration_est_sec": 5.0},
        ],
    })
    changed = migrate_storyboard_file(sb_path, primary_locale="zh-TW")
    assert changed is True
    data = json.loads(sb_path.read_text(encoding="utf-8"))
    assert data["primary_locale"] == "zh-TW"
    scene = data["scenes"][0]
    assert scene["narration_alt"] == {"en": "primary"}
    assert "narration_en" not in scene
    assert scene["beat"] == ""


def test_migrate_is_idempotent(tmp_path: Path):
    sb_path = tmp_path / "storyboard.json"
    _write(sb_path, {
        "version": 1,
        "primary_locale": "zh-TW",
        "scenes": [
            {"id": "s1", "section": "hook", "beat": "", "narration": "主要",
             "narration_alt": {"en": "primary"}, "narration_est_sec": 5.0},
        ],
    })
    changed = migrate_storyboard_file(sb_path, primary_locale="zh-TW")
    assert changed is False


def test_backfill_beats_fills_empty_beats(tmp_path: Path, monkeypatch):
    from pipeline import cli_storyboard

    sb_path = tmp_path / "storyboard.json"
    _write(sb_path, {
        "version": 1,
        "primary_locale": "zh-TW",
        "scenes": [
            {"id": "s1", "section": "hook", "beat": "", "narration": "主要一",
             "narration_alt": {}, "narration_est_sec": 5.0},
            {"id": "s2", "section": "context", "beat": "", "narration": "主要二",
             "narration_alt": {}, "narration_est_sec": 5.0},
        ],
    })

    def fake_generate(scenes):
        return {"s1": "beat one", "s2": "beat two"}

    monkeypatch.setattr(cli_storyboard, "_generate_beats", fake_generate)
    cli_storyboard.backfill_beats_file(sb_path)
    data = json.loads(sb_path.read_text(encoding="utf-8"))
    assert data["scenes"][0]["beat"] == "beat one"
    assert data["scenes"][1]["beat"] == "beat two"
