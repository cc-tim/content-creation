from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.style.log import StyleLogEntry, append_log
from pipeline.style.manifest import (
    PerSceneOverride,
    StyleElement,
    StyleManifest,
    build_manifest,
)


# ── Data-structure smoke tests ────────────────────────────────────────────────

def test_style_element_defaults():
    el = StyleElement(
        id="frame_open_book_page",
        kind="frame",
        value="open_book_page",
        source="project_theme",
        scope="all_scenes",
        theme_key="frame_style",
    )
    assert el.active is True
    assert el.warnings == []


def test_style_element_inactive():
    el = StyleElement(
        id="anchor_image",
        kind="anchor_image",
        value="/some/path.png",
        source="project_theme",
        scope="generated_image_scenes",
        theme_key="_anchor_image",
        active=False,
        warnings=["not used in image generation"],
    )
    assert el.active is False
    assert "not used" in el.warnings[0]


def test_style_manifest_empty():
    m = StyleManifest(project_id="proj", elements=[], per_scene_overrides=[])
    assert m.project_id == "proj"
    assert m.elements == []
    assert m.per_scene_overrides == []


# ── build_manifest tests ──────────────────────────────────────────────────────

def _write_storyboard(tmp_path: Path, theme: dict, scenes: list | None = None) -> Path:
    sb = tmp_path / "storyboard.json"
    sb.write_text(json.dumps({
        "project_id": "test-project",
        "theme": theme,
        "scenes": scenes or [],
    }))
    return sb


def test_build_manifest_frame_style(tmp_path):
    sb = _write_storyboard(tmp_path, {"frame_style": "open_book_page"})
    manifest = build_manifest(sb)
    assert manifest.project_id == "test-project"
    ids = [e.id for e in manifest.elements]
    assert "frame_open_book_page" in ids
    el = next(e for e in manifest.elements if e.id == "frame_open_book_page")
    assert el.kind == "frame"
    assert el.value == "open_book_page"
    assert el.theme_key == "frame_style"
    assert el.active is True
    assert len(el.warnings) == 1  # "no per-scene opt-out" warning always present


def test_build_manifest_visual_style_no_warning(tmp_path):
    sb = _write_storyboard(tmp_path, {"visual_style": "warm amber tones, documentary"})
    manifest = build_manifest(sb)
    el = next(e for e in manifest.elements if e.id == "visual_style")
    assert el.kind == "image_prompt_prefix"
    assert el.warnings == []


def test_build_manifest_visual_style_medium_warning(tmp_path):
    sb = _write_storyboard(
        tmp_path,
        {"visual_style": "soft sketch lines, hand-drawn warmth, no text in images"},
    )
    manifest = build_manifest(sb)
    el = next(e for e in manifest.elements if e.id == "visual_style")
    assert len(el.warnings) == 1
    assert "medium descriptor" in el.warnings[0]


def test_build_manifest_transition(tmp_path):
    sb = _write_storyboard(tmp_path, {"intro_transition_style": "book-page-turn-v2"})
    manifest = build_manifest(sb)
    ids = [e.id for e in manifest.elements]
    assert "transition_book_page_turn_v2" in ids
    el = next(e for e in manifest.elements if e.id == "transition_book_page_turn_v2")
    assert el.kind == "transition"
    assert el.value == "book-page-turn-v2"
    assert el.theme_key == "intro_transition_style"


def test_build_manifest_anchor_image_inactive(tmp_path):
    sb = _write_storyboard(tmp_path, {"_anchor_image": "/configs/niche_anchors/parenting/style_anchor.png"})
    manifest = build_manifest(sb)
    el = next((e for e in manifest.elements if e.id == "anchor_image"), None)
    assert el is not None
    assert el.active is False
    assert el.theme_key == "_anchor_image"
    assert len(el.warnings) == 1
    assert "not used" in el.warnings[0].lower()


def test_build_manifest_empty_theme(tmp_path):
    sb = _write_storyboard(tmp_path, {})
    manifest = build_manifest(sb)
    assert manifest.elements == []
    assert manifest.per_scene_overrides == []


def test_build_manifest_per_scene_skip_niche_style(tmp_path):
    scenes = [
        {"scene_id": "s01", "visual": {"type": "generated_image", "skip_niche_style": True}},
        {"scene_id": "s02", "visual": {"type": "generated_image"}},
    ]
    sb = _write_storyboard(tmp_path, {}, scenes)
    manifest = build_manifest(sb)
    assert len(manifest.per_scene_overrides) == 1
    assert manifest.per_scene_overrides[0].scene_id == "s01"
    assert manifest.per_scene_overrides[0].kind == "skip_niche_style"


def test_build_manifest_per_scene_style_modifier(tmp_path):
    scenes = [
        {"scene_id": "s03", "visual": {"type": "generated_image", "style_modifier": "cinematic lighting"}},
    ]
    sb = _write_storyboard(tmp_path, {}, scenes)
    manifest = build_manifest(sb)
    assert len(manifest.per_scene_overrides) == 1
    assert manifest.per_scene_overrides[0].kind == "style_modifier"
    assert manifest.per_scene_overrides[0].value == "cinematic lighting"


def test_build_manifest_project_id_fallback(tmp_path):
    """project_id falls back to parent directory name if not in JSON."""
    sb = tmp_path / "storyboard.json"
    sb.write_text(json.dumps({"theme": {}, "scenes": []}))
    manifest = build_manifest(sb)
    assert manifest.project_id == tmp_path.name


def test_build_manifest_visual_style_no_false_positive_outlines(tmp_path):
    """'outlines' should NOT trigger the medium-descriptor warning for 'lines'."""
    sb = _write_storyboard(tmp_path, {"visual_style": "clean outlines, minimal design"})
    manifest = build_manifest(sb)
    el = next(e for e in manifest.elements if e.id == "visual_style")
    assert el.warnings == []


def test_build_manifest_non_ascii_project_id(tmp_path):
    """Storyboard files with Traditional Chinese content must be read correctly."""
    sb = tmp_path / "storyboard.json"
    sb.write_text(
        json.dumps({"project_id": "嬰兒學步車", "theme": {}, "scenes": []}),
        encoding="utf-8",
    )
    manifest = build_manifest(sb)
    assert manifest.project_id == "嬰兒學步車"


# ── Style log tests ───────────────────────────────────────────────────────────


def test_append_log_creates_file(tmp_path):
    append_log(tmp_path, "add", "frame_open_book_page", "Tim requested book feel")
    log_path = tmp_path / "style_log.json"
    assert log_path.exists()
    entries = json.loads(log_path.read_text(encoding="utf-8"))
    assert len(entries) == 1
    e = entries[0]
    assert e["action"] == "add"
    assert e["element_id"] == "frame_open_book_page"
    assert e["rationale"] == "Tim requested book feel"
    assert "timestamp" in e
    # timestamp must be ISO-8601 with timezone offset
    assert "T" in e["timestamp"] and ("Z" in e["timestamp"] or "+" in e["timestamp"])


def test_append_log_appends_multiple(tmp_path):
    append_log(tmp_path, "add", "el1", "first")
    append_log(tmp_path, "remove", "el1", "changed mind")
    entries = json.loads((tmp_path / "style_log.json").read_text(encoding="utf-8"))
    assert len(entries) == 2
    assert entries[0]["action"] == "add"
    assert entries[1]["action"] == "remove"


def test_append_log_empty_rationale(tmp_path):
    append_log(tmp_path, "remove", "anchor_image")
    entries = json.loads((tmp_path / "style_log.json").read_text(encoding="utf-8"))
    assert entries[0]["rationale"] == ""
