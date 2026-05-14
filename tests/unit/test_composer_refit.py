from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from PIL import Image

from pipeline.composer import refit


def test_canvas_size_uses_storyboard_aspect_ratio():
    assert refit.canvas_size({"aspect_ratio": "16:9"}) == (1280, 720)
    assert refit.canvas_size({"aspect_ratio": "9:16"}) == (720, 1280)


def test_target_box_open_book_page_uses_book_scene_inset():
    assert refit.target_box({"frame_style": "open_book_page"}, 1280, 720) == (947, 484)
    assert refit.target_box({"frame_style": "open_book_page"}, 1920, 1080) == (1422, 726)


def test_target_box_without_frame_uses_canvas():
    assert refit.target_box({}, 1280, 720) == (1280, 720)


def test_target_box_rejects_unknown_frame_style():
    with pytest.raises(ValueError, match="Unknown frame_style"):
        refit.target_box({"frame_style": "polaroid_stack"}, 1280, 720)


@pytest.mark.parametrize(
    ("src_w", "src_h", "target_w", "target_h", "expected"),
    [
        (200, 100, 400, 200, False),
        (192, 100, 400, 200, False),
        (180, 100, 400, 200, True),
        (100, 160, 947, 484, True),
    ],
)
def test_needs_refit_threshold(src_w, src_h, target_w, target_h, expected):
    assert refit.needs_refit(src_w, src_h, target_w, target_h) is expected


def test_apply_crop_writes_requested_output_at_target_aspect(tmp_path: Path):
    source = tmp_path / "wide.png"
    out = tmp_path / "cropped.png"
    Image.new("RGB", (400, 200), "red").save(source)

    result = refit.apply_crop(source, out, 100, 100, bias=(0.25, 0.5))

    assert result == out
    assert out.exists()
    image = Image.open(out)
    assert image.size == (100, 100)


def test_apply_crop_handles_tall_source(tmp_path: Path):
    source = tmp_path / "tall.png"
    out = tmp_path / "cropped.png"
    Image.new("RGB", (200, 400), "blue").save(source)

    refit.apply_crop(source, out, 200, 100, bias=(0.5, 0.25))

    image = Image.open(out)
    assert image.size == (200, 100)


def test_apply_outpaint_shells_to_shared_helper(tmp_path: Path, monkeypatch):
    source = tmp_path / "source.png"
    out = tmp_path / "out.png"
    source.write_bytes(b"fake")
    captured = {}

    def fake_run(cmd, capture_output, text, timeout, check):
        captured["cmd"] = cmd
        out.write_bytes(b"png")
        return subprocess.CompletedProcess(cmd, 0, stdout=str(out) + "\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = refit.apply_outpaint(source, out, 947, 484, "Extend horizontally.")

    assert result == out
    assert captured["cmd"][:3] == [
        "python3",
        str(Path.home() / ".claude" / "bin" / "gen-image-edit.py"),
        "--source",
    ]
    assert "--mode" in captured["cmd"]
    assert "outpaint" in captured["cmd"]
    assert "--target-aspect" in captured["cmd"]
    assert "947:484" in captured["cmd"]


def test_apply_outpaint_raises_when_helper_fails(tmp_path: Path, monkeypatch):
    source = tmp_path / "source.png"
    out = tmp_path / "out.png"
    source.write_bytes(b"fake")

    def fake_run(cmd, capture_output, text, timeout, check):
        return subprocess.CompletedProcess(cmd, 3, stdout="", stderr="API error")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(refit.RefitError, match="API error"):
        refit.apply_outpaint(source, out, 947, 484, "Extend horizontally.")


def test_effective_image_path_prefers_existing_refit_path(tmp_path: Path):
    raw = tmp_path / "raw.png"
    refitted = tmp_path / "refit.png"
    raw.write_bytes(b"raw")
    refitted.write_bytes(b"refit")

    assert refit.effective_image_path({"path": str(raw), "refit_path": str(refitted)}) == refitted


def test_effective_image_path_falls_back_when_refit_missing(tmp_path: Path):
    raw = tmp_path / "raw.png"
    raw.write_bytes(b"raw")

    assert (
        refit.effective_image_path({"path": str(raw), "refit_path": str(tmp_path / "missing.png")})
        == raw
    )
    assert refit.effective_image_path({"path": str(raw)}) == raw
