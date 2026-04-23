from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from pipeline.publish.stage import PreflightError, run_preflight
from pipeline.stages.base import PipelineContext

META_FIXTURE = Path(__file__).parents[2] / "fixtures" / "sample_metadata.json"


@pytest.fixture
def ready_project(tmp_path: Path) -> Path:
    d = tmp_path / "project"
    d.mkdir()
    (d / "final.mp4").write_bytes(b"x" * 1024)
    (d / "thumbnail.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 500)
    shutil.copy(META_FIXTURE, d / "metadata.json")
    return d


def _ctx(work_dir: Path) -> PipelineContext:
    return PipelineContext(
        project_id=1,
        source_url="https://example.com",
        locale="zh-TW",
        work_dir=work_dir,
        niche="sample",
        final_video_path=work_dir / "final.mp4",
    )


def test_preflight_ok(ready_project: Path) -> None:
    ctx = _ctx(ready_project)
    run_preflight(ctx=ctx, privacy="unlisted", schedule_iso=None)


def test_preflight_missing_video(ready_project: Path) -> None:
    (ready_project / "final.mp4").unlink()
    ctx = _ctx(ready_project)
    with pytest.raises(PreflightError, match="final video"):
        run_preflight(ctx=ctx, privacy="unlisted", schedule_iso=None)


def test_preflight_missing_thumbnail(ready_project: Path) -> None:
    (ready_project / "thumbnail.png").unlink()
    ctx = _ctx(ready_project)
    with pytest.raises(PreflightError, match="thumbnail"):
        run_preflight(ctx=ctx, privacy="unlisted", schedule_iso=None)


def test_preflight_missing_metadata(ready_project: Path) -> None:
    (ready_project / "metadata.json").unlink()
    ctx = _ctx(ready_project)
    with pytest.raises(PreflightError, match="metadata"):
        run_preflight(ctx=ctx, privacy="unlisted", schedule_iso=None)


def test_preflight_thumbnail_too_large(ready_project: Path) -> None:
    (ready_project / "thumbnail.png").write_bytes(
        b"\x89PNG\r\n\x1a\n" + b"\x00" * (3 * 1024 * 1024)
    )
    ctx = _ctx(ready_project)
    with pytest.raises(PreflightError, match="thumbnail.*exceeds"):
        run_preflight(ctx=ctx, privacy="unlisted", schedule_iso=None)


def test_preflight_schedule_with_public_rejected(ready_project: Path) -> None:
    ctx = _ctx(ready_project)
    with pytest.raises(PreflightError, match="schedule.*public"):
        run_preflight(ctx=ctx, privacy="public", schedule_iso="2099-01-01T00:00:00+00:00")


def test_preflight_schedule_in_past(ready_project: Path) -> None:
    ctx = _ctx(ready_project)
    with pytest.raises(PreflightError, match="schedule.*past"):
        run_preflight(ctx=ctx, privacy="private", schedule_iso="2000-01-01T00:00:00+00:00")


def test_preflight_invalid_metadata(ready_project: Path) -> None:
    raw = json.loads((ready_project / "metadata.json").read_text())
    raw["title"] = "x" * 200
    (ready_project / "metadata.json").write_text(json.dumps(raw))
    ctx = _ctx(ready_project)
    with pytest.raises(PreflightError, match="metadata.*invalid"):
        run_preflight(ctx=ctx, privacy="unlisted", schedule_iso=None)
