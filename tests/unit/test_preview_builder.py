from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from pipeline.dashboard.preview import (
    build_preview,
    build_project_preview_manifest,
    build_transition_preview_image,
)
from pipeline.storyboard import Scene, Storyboard, Transition


def _seed_project(tmp_path: Path) -> Path:
    project = tmp_path / "projects" / "42"
    project.mkdir(parents=True)
    return project


def test_build_preview_subtitle_returns_text_diff(tmp_path: Path) -> None:
    project = _seed_project(tmp_path)
    preview = build_preview(
        verb="subtitle set",
        args={"scene": "s1", "text": "new"},
        project_root=project,
        old_text="old",
    )

    assert preview.kind == "text_diff"
    assert "old" in preview.body
    assert "new" in preview.body


def test_build_preview_image_regen_returns_photo_when_image_present(tmp_path: Path) -> None:
    project = _seed_project(tmp_path)
    image_dir = project / "images" / "scenes"
    image_dir.mkdir(parents=True)
    image = image_dir / "s9.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

    preview = build_preview(
        verb="image regen",
        args={"scene": "s9", "prompt": "x", "tier": "draft"},
        project_root=project,
    )

    assert preview.kind == "photo"
    assert preview.path == image


def test_build_preview_falls_back_to_text_when_artifact_missing(tmp_path: Path) -> None:
    project = _seed_project(tmp_path)
    preview = build_preview(
        verb="image regen",
        args={"scene": "s9", "prompt": "x", "tier": "draft"},
        project_root=project,
    )

    assert preview.kind == "text_diff"
    assert "s9" in preview.body


def test_build_preview_for_transition_returns_video_when_seam_present(tmp_path: Path) -> None:
    project = _seed_project(tmp_path)
    seam = project / "compose" / "seam_s1_s2.mp4"
    seam.parent.mkdir(parents=True)
    seam.write_bytes(b"\x00\x00")

    preview = build_preview(
        verb="transition set",
        args={"from": "s1", "to": "s2", "style": "fade", "duration_sec": 0.5},
        project_root=project,
    )

    assert preview.kind == "video"
    assert preview.path == seam


def test_build_project_preview_manifest_collects_scene_and_transition_previews(tmp_path: Path) -> None:
    project = _seed_project(tmp_path)
    storyboard = Storyboard(
        scenes=[
            Scene(id="s1", section="hook", narration="x", narration_est_sec=1.0),
            Scene(id="s2", section="body", narration="y", narration_est_sec=1.0),
        ],
        transitions=[
            Transition(
                from_scene="s1",
                to_scene="s2",
                style="book-page-turn",
                duration_sec=0.8,
                page_count=2,
            )
        ],
    )
    storyboard.save(project / "storyboard.json")
    scenes_dir = project / "compose" / "scenes"
    scenes_dir.mkdir(parents=True)
    (scenes_dir / "s1_final.mp4").write_bytes(b"video")
    (scenes_dir / "s1_final_no_overlay.mp4").write_bytes(b"video")
    (scenes_dir / "s2_final.mp4").write_bytes(b"video")
    (scenes_dir / "s2_final_no_overlay.mp4").write_bytes(b"video")
    transition_clip = project / "compose" / "transitions" / "clip.mp4"
    transition_clip.parent.mkdir(parents=True)
    transition_clip.write_bytes(b"video")

    with (
        patch("pipeline.dashboard.preview.ensure_scene_preview") as scene_preview,
        patch("pipeline.dashboard.preview.ensure_transition_preview") as transition_preview,
        patch("pipeline.dashboard.preview.resolve_transition_clip", return_value=transition_clip),
        patch("pipeline.dashboard.preview.build_intro_transition_preview", return_value=None),
    ):
        manifest = build_project_preview_manifest(project)

    assert [item["id"] for item in manifest["scenes"]] == ["s1", "s2"]
    assert manifest["transitions"][0]["id"] == "s1->s2"
    assert scene_preview.call_count == 2
    assert transition_preview.call_count == 1


def test_build_transition_preview_image_renders_draft_preview(tmp_path: Path) -> None:
    project = _seed_project(tmp_path)
    storyboard = Storyboard(
        scenes=[
            Scene(id="s1", section="hook", narration="x", narration_est_sec=1.0),
            Scene(id="s2", section="body", narration="y", narration_est_sec=1.0),
        ],
    )
    storyboard.save(project / "storyboard.json")
    scenes_dir = project / "compose" / "scenes"
    scenes_dir.mkdir(parents=True)
    a = scenes_dir / "s1_final.mp4"
    b = scenes_dir / "s2_final.mp4"
    a.write_bytes(b"video")
    b.write_bytes(b"video")
    clip = project / "compose" / "transitions" / "generated.mp4"
    clip.parent.mkdir(parents=True)
    clip.write_bytes(b"video")

    with (
        patch("pipeline.dashboard.preview.render_transition", return_value=clip) as render_transition,
        patch("pipeline.dashboard.preview.ensure_transition_preview") as ensure_preview,
    ):
        preview = build_transition_preview_image(
            project,
            from_scene="s1",
            to_scene="s2",
            style="fade",
            duration_sec=0.5,
            preview_name="draft_case",
        )

    assert preview == project / "compose" / "previews" / "transitions" / "draft_case.jpg"
    assert render_transition.called
    assert ensure_preview.called
