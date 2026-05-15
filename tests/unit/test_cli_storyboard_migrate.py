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
