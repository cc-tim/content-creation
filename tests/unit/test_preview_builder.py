from __future__ import annotations

from pathlib import Path

from pipeline.dashboard.preview import build_preview


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
