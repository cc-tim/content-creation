"""Tests for ProjectConstraints: load/save, reminder formatting, storyboard check."""
from __future__ import annotations

import json

import pytest

from pipeline.constraints import ProjectConstraints


def test_save_and_load_roundtrip(tmp_path):
    c = ProjectConstraints(duration_min_minutes=8.0, duration_max_minutes=12.0, notes="test")
    c.save(tmp_path)
    loaded = ProjectConstraints.load(tmp_path)
    assert loaded is not None
    assert loaded.duration_min_minutes == 8.0
    assert loaded.duration_max_minutes == 12.0
    assert loaded.notes == "test"


def test_load_returns_none_when_missing(tmp_path):
    assert ProjectConstraints.load(tmp_path) is None


def test_load_ignores_unknown_fields(tmp_path):
    (tmp_path / "constraints.json").write_text(
        json.dumps({"duration_min_minutes": 5.0, "future_field": "ignored"}), encoding="utf-8"
    )
    c = ProjectConstraints.load(tmp_path)
    assert c is not None
    assert c.duration_min_minutes == 5.0


def test_format_reminder_both_bounds():
    c = ProjectConstraints(duration_min_minutes=8, duration_max_minutes=12)
    reminder = c.format_reminder()
    assert "8" in reminder and "12" in reminder
    assert "HARD REQUIREMENT" in reminder


def test_format_reminder_min_only():
    c = ProjectConstraints(duration_min_minutes=5)
    reminder = c.format_reminder()
    assert "at least 5" in reminder


def test_format_reminder_max_only():
    c = ProjectConstraints(duration_max_minutes=10)
    reminder = c.format_reminder()
    assert "at most 10" in reminder


def test_format_reminder_with_notes():
    c = ProjectConstraints(notes="subtitles only, no overlays")
    reminder = c.format_reminder()
    assert "subtitles only" in reminder


def test_check_storyboard_within_range():
    c = ProjectConstraints(duration_min_minutes=8, duration_max_minutes=12)
    assert c.check_storyboard(600) == []  # 10 min — OK


def test_check_storyboard_below_min():
    c = ProjectConstraints(duration_min_minutes=8)
    violations = c.check_storyboard(450)  # 7.5 min
    assert len(violations) == 1
    assert "below" in violations[0]


def test_check_storyboard_above_max():
    c = ProjectConstraints(duration_max_minutes=12)
    violations = c.check_storyboard(800)  # 13.3 min
    assert len(violations) == 1
    assert "exceeds" in violations[0]


def test_duration_instruction_both_bounds():
    c = ProjectConstraints(duration_min_minutes=8, duration_max_minutes=12)
    instr = c.duration_instruction()
    assert "8–12" in instr and "HARD REQUIREMENT" in instr


def test_duration_instruction_empty_when_no_bounds():
    c = ProjectConstraints()
    assert c.duration_instruction() == ""
