from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from pipeline.style.cli import style_app
from pipeline.style.log import append_log
from pipeline.style.manifest import (
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


def test_build_manifest_split_style_elements(tmp_path):
    sb = _write_storyboard(
        tmp_path,
        {
            "medium_hint": "soft sketch lines, hand-drawn warmth",
            "palette": "cream background, muted earth tones",
            "subject_bias": "same parent-child duo across scenes",
            "universal_rules": "no clutter, no text in images",
            "visual_style": "cream background, muted earth tones, no clutter, no text in images",
        },
    )
    manifest = build_manifest(sb)
    elements = {e.id: e for e in manifest.elements}
    assert elements["medium_hint"].kind == "image_prompt_prefix"
    assert elements["medium_hint"].value == "soft sketch lines, hand-drawn warmth"
    assert elements["palette"].value == "cream background, muted earth tones"
    assert elements["subject_bias"].value == "same parent-child duo across scenes"
    assert elements["medium_hint"].theme_key == "medium_hint"


def test_build_manifest_medium_warning_uses_medium_hint(tmp_path):
    sb = _write_storyboard(
        tmp_path,
        {
            "medium_hint": "soft sketch lines, hand-drawn warmth",
            "palette": "cream background",
            "visual_style": "cream background, no text in images",
        },
    )
    manifest = build_manifest(sb)
    medium = next(e for e in manifest.elements if e.id == "medium_hint")
    composite = next(e for e in manifest.elements if e.id == "visual_style")
    assert len(medium.warnings) == 1
    assert "medium descriptor" in medium.warnings[0]
    assert "medium_hint" in medium.warnings[0]
    assert composite.warnings == []


def test_build_manifest_legacy_visual_style_keeps_composite_element(tmp_path):
    sb = _write_storyboard(
        tmp_path,
        {"visual_style": "soft sketch lines, hand-drawn warmth, no text in images"},
    )
    manifest = build_manifest(sb)
    assert [e.id for e in manifest.elements] == ["visual_style"]
    el = manifest.elements[0]
    assert el.kind == "image_prompt_prefix"
    assert el.value == "soft sketch lines, hand-drawn warmth, no text in images"
    assert el.warnings == []


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


# ── CLI tests ─────────────────────────────────────────────────────────────────


def _make_project(tmp_path: Path, project_id: str, theme: dict, scenes: list | None = None) -> Path:
    """Create output/projects/{project_id}/storyboard.json under tmp_path."""
    project_dir = tmp_path / "output" / "projects" / project_id
    project_dir.mkdir(parents=True)
    sb = project_dir / "storyboard.json"
    sb.write_text(
        json.dumps({
            "project_id": project_id,
            "theme": theme,
            "scenes": scenes or [],
        }),
        encoding="utf-8",
    )
    return project_dir


def test_style_list_shows_frame(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _make_project(tmp_path, "test-proj", {"frame_style": "open_book_page"})
    runner = CliRunner()
    result = runner.invoke(style_app, ["list", "--project-id", "test-proj"])
    assert result.exit_code == 0, result.output
    assert "frame_open_book_page" in result.output
    assert "frame" in result.output


def test_style_list_shows_anchor_inactive(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _make_project(tmp_path, "test-anchor", {"_anchor_image": "/some/path.png"})
    runner = CliRunner()
    result = runner.invoke(style_app, ["list", "--project-id", "test-anchor"])
    assert result.exit_code == 0, result.output
    assert "anchor_image" in result.output
    assert "INACTIVE" in result.output


def test_style_list_shows_split_image_prompt_fields(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _make_project(
        tmp_path,
        "test-split-style",
        {
            "medium_hint": "soft sketch lines",
            "palette": "cream background",
            "subject_bias": "same parent-child duo",
        },
    )
    runner = CliRunner()
    result = runner.invoke(style_app, ["list", "--project-id", "test-split-style"])
    assert result.exit_code == 0, result.output
    assert "medium_hint" in result.output
    assert "palette" in result.output
    assert "subject_bias" in result.output
    assert "image_prompt_prefix" in result.output


def test_style_list_unknown_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(style_app, ["list", "--project-id", "no-such-project"])
    assert result.exit_code != 0


# ── style remove tests ────────────────────────────────────────────────────────


def test_style_remove_frame(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    project_dir = _make_project(
        tmp_path, "proj-remove",
        {"frame_style": "open_book_page"},
        scenes=[{"scene_id": "s01", "visual": {}}, {"scene_id": "s02", "visual": {}}],
    )
    runner = CliRunner()
    result = runner.invoke(
        style_app,
        ["remove", "--project-id", "proj-remove", "frame_open_book_page"],
    )
    assert result.exit_code == 0, result.output
    data = json.loads((project_dir / "storyboard.json").read_text(encoding="utf-8"))
    assert "frame_style" not in data["theme"]
    log = json.loads((project_dir / "style_log.json").read_text(encoding="utf-8"))
    assert len(log) == 1
    assert log[0]["action"] == "remove"
    assert log[0]["element_id"] == "frame_open_book_page"
    assert "2 scene" in result.output


def test_style_remove_anchor_image(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    project_dir = _make_project(
        tmp_path, "proj-anchor",
        {"_anchor_image": "/configs/niche_anchors/parenting/style_anchor.png"},
    )
    runner = CliRunner()
    result = runner.invoke(
        style_app,
        ["remove", "--project-id", "proj-anchor", "anchor_image"],
    )
    assert result.exit_code == 0, result.output
    data = json.loads((project_dir / "storyboard.json").read_text(encoding="utf-8"))
    assert "_anchor_image" not in data["theme"]


def test_style_remove_not_found(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _make_project(tmp_path, "proj-notfound", {})
    runner = CliRunner()
    result = runner.invoke(
        style_app,
        ["remove", "--project-id", "proj-notfound", "frame_open_book_page"],
    )
    assert result.exit_code != 0


def test_style_remove_with_rationale(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    project_dir = _make_project(tmp_path, "proj-rationale", {"frame_style": "open_book_page"})
    runner = CliRunner()
    runner.invoke(
        style_app,
        [
            "remove", "--project-id", "proj-rationale",
            "frame_open_book_page", "--rationale", "switching to clean look",
        ],
    )
    log = json.loads((project_dir / "style_log.json").read_text(encoding="utf-8"))
    assert log[0]["rationale"] == "switching to clean look"


# ── style add tests ───────────────────────────────────────────────────────────


def test_style_add_frame(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    project_dir = _make_project(tmp_path, "proj-add", {})
    runner = CliRunner()
    result = runner.invoke(
        style_app,
        ["add", "--project-id", "proj-add", "frame_open_book_page", "frame", "open_book_page"],
    )
    assert result.exit_code == 0, result.output
    data = json.loads((project_dir / "storyboard.json").read_text(encoding="utf-8"))
    assert data["theme"]["frame_style"] == "open_book_page"
    log = json.loads((project_dir / "style_log.json").read_text(encoding="utf-8"))
    assert log[0]["action"] == "add"
    assert log[0]["element_id"] == "frame_open_book_page"


def test_style_add_image_prompt_prefix(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    project_dir = _make_project(tmp_path, "proj-add-vs", {})
    runner = CliRunner()
    result = runner.invoke(
        style_app,
        [
            "add", "--project-id", "proj-add-vs",
            "visual_style", "image_prompt_prefix", "warm amber documentary tones",
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads((project_dir / "storyboard.json").read_text(encoding="utf-8"))
    assert data["theme"]["visual_style"] == "warm amber documentary tones"


def test_style_add_unknown_kind(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _make_project(tmp_path, "proj-bad-kind", {})
    runner = CliRunner()
    result = runner.invoke(
        style_app,
        ["add", "--project-id", "proj-bad-kind", "some_id", "unknown_kind", "value"],
    )
    assert result.exit_code != 0


# ── dead-code removal verification ────────────────────────────────────────────


def test_render_generated_image_no_anchor_param():
    """anchor_image must NOT be a parameter of render_generated_image (dead code removed)."""
    import inspect

    from pipeline.composer.image import render_generated_image

    sig = inspect.signature(render_generated_image)
    assert "anchor_image" not in sig.parameters, (
        "anchor_image is still in render_generated_image signature. "
        "Remove it from image.py and the call site in base.py."
    )


def test_build_manifest_registers_callout_for_line_chart_markers(tmp_path):
    sb = {
        "project_id": "p1",
        "theme": {},
        "scenes": [
            {"id": "s1", "visual": {"type": "generated_image"}},
            {"id": "s21", "visual": {
                "type": "chart", "chart_type": "line",
                "data": {"points": [{"x": 1990, "y": 5}],
                         "markers": [{"x": 1995, "label": "ban"}]},
            }},
        ],
    }
    p = tmp_path / "storyboard.json"
    p.write_text(json.dumps(sb), encoding="utf-8")

    manifest = build_manifest(p)
    callout = next((e for e in manifest.elements if e.kind == "overlay"), None)
    assert callout is not None
    assert callout.id == "callout"
    assert "s21" in callout.value
    assert callout.active is True


def test_build_manifest_no_callout_when_no_markers(tmp_path):
    sb = {
        "project_id": "p1", "theme": {},
        "scenes": [{"id": "s1", "visual": {"type": "chart", "chart_type": "bar",
                                           "data": {"x": ["a"], "y": [1]}}}],
    }
    p = tmp_path / "storyboard.json"
    p.write_text(json.dumps(sb), encoding="utf-8")
    assert not any(e.kind == "overlay" for e in build_manifest(p).elements)
