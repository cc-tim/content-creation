from __future__ import annotations

import os
import time

_FAKE_PNG = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x11\x00\x01\x1b\xb0\xa4G\x00\x00\x00\x00IEND\xaeB`\x82'


def test_save_to_history_creates_timestamped_file(tmp_path):
    from pipeline.composer.image_history import save_to_history
    src = tmp_path / "s5_source.png"
    src.write_bytes(_FAKE_PNG)
    dest = save_to_history(src, "s5", tmp_path)
    assert dest.exists()
    assert dest.parent == tmp_path / "image_history"
    assert dest.name.startswith("s5_")
    assert dest.suffix == ".png"


def test_save_to_history_preserves_content(tmp_path):
    from pipeline.composer.image_history import save_to_history
    src = tmp_path / "s5_source.png"
    src.write_bytes(_FAKE_PNG)
    dest = save_to_history(src, "s5", tmp_path)
    assert dest.read_bytes() == _FAKE_PNG


def test_find_history_returns_most_recent_first(tmp_path):
    from pipeline.composer.image_history import find_history
    hist = tmp_path / "image_history"
    hist.mkdir()
    (hist / "s5_20260427T000000.png").write_bytes(_FAKE_PNG)
    (hist / "s5_20260428T000000.png").write_bytes(_FAKE_PNG)
    entries = find_history("s5", tmp_path)
    assert len(entries) == 2
    assert entries[0][1].name == "s5_20260428T000000.png"


def test_find_history_ignores_other_scenes(tmp_path):
    from pipeline.composer.image_history import find_history
    hist = tmp_path / "image_history"
    hist.mkdir()
    (hist / "s5_20260428T000000.png").write_bytes(_FAKE_PNG)
    (hist / "s12b_20260428T000000.png").write_bytes(_FAKE_PNG)
    entries = find_history("s5", tmp_path)
    assert len(entries) == 1
    assert "s5" in entries[0][1].name


def test_purge_old_removes_stale_entries(tmp_path):
    from pipeline.composer.image_history import purge_old
    hist = tmp_path / "image_history"
    hist.mkdir()
    old = hist / "s5_20260101T000000.png"
    old.write_bytes(_FAKE_PNG)
    old_mtime = time.time() - (8 * 24 * 3600)
    os.utime(old, (old_mtime, old_mtime))
    removed = purge_old(tmp_path, max_age_days=7)
    assert removed == 1
    assert not old.exists()


def test_purge_old_keeps_recent_entries(tmp_path):
    from pipeline.composer.image_history import purge_old
    hist = tmp_path / "image_history"
    hist.mkdir()
    recent = hist / "s5_20260428T000000.png"
    recent.write_bytes(_FAKE_PNG)
    removed = purge_old(tmp_path, max_age_days=7)
    assert removed == 0
    assert recent.exists()


def test_purge_old_returns_zero_when_no_history(tmp_path):
    from pipeline.composer.image_history import purge_old
    assert purge_old(tmp_path, max_age_days=7) == 0


def test_restore_scene_copies_most_recent(tmp_path):
    from pipeline.composer.image_history import restore_scene
    hist = tmp_path / "image_history"
    hist.mkdir()
    (hist / "s5_20260427T000000.png").write_bytes(b"old")
    (hist / "s5_20260428T000000.png").write_bytes(b"new")
    result = restore_scene("s5", tmp_path)
    assert result is not None
    assert result == tmp_path / "s5_restore.png"
    assert result.read_bytes() == b"new"


def test_restore_scene_specific_timestamp(tmp_path):
    from pipeline.composer.image_history import restore_scene
    hist = tmp_path / "image_history"
    hist.mkdir()
    (hist / "s5_20260427T000000.png").write_bytes(b"old")
    (hist / "s5_20260428T000000.png").write_bytes(b"new")
    result = restore_scene("s5", tmp_path, timestamp_str="20260427T000000")
    assert result is not None
    assert result.read_bytes() == b"old"


def test_restore_scene_returns_none_when_no_history(tmp_path):
    from pipeline.composer.image_history import restore_scene
    assert restore_scene("s5", tmp_path) is None
