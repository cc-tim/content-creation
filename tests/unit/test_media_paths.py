"""One media-path resolver (E5 sweep §5.5): candidates, precedence, and agreement
between `pipeline validate` and the renderers."""
from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.utils import paths
from pipeline.utils.paths import media_path_candidates, resolve_media_path


def _touch(p: Path) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")
    return p


@pytest.fixture
def layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, Path]:
    """A project dir, a stand-in repo root and a cwd that is neither."""
    project, repo, cwd = tmp_path / "project", tmp_path / "repo", tmp_path / "cwd"
    for d in (project, repo, cwd):
        d.mkdir()
    monkeypatch.setattr(paths, "REPO_ROOT", repo)
    monkeypatch.chdir(cwd)
    return project, repo, cwd


def test_repo_root_is_the_checkout_root():
    assert (paths.REPO_ROOT / "pyproject.toml").is_file()
    assert (paths.REPO_ROOT / "src" / "pipeline" / "utils" / "paths.py").is_file()


def test_absolute_path_is_its_own_only_candidate(layout):
    project, _, _ = layout
    a = _touch(project / "abs.mp4")
    assert media_path_candidates(str(a), project) == [a]
    assert resolve_media_path(a, project) == a


def test_relative_candidates_are_project_then_repo_then_cwd(layout):
    project, repo, cwd = layout
    assert media_path_candidates("raw/x.png", project) == [
        project / "raw/x.png", repo / "raw/x.png", cwd / "raw/x.png",
    ]


def test_project_relative_wins(layout):
    project, repo, cwd = layout
    p = _touch(project / "source/clip.mp4")
    _touch(repo / "source/clip.mp4")
    _touch(cwd / "source/clip.mp4")
    assert resolve_media_path("source/clip.mp4", project) == p


def test_repo_relative_resolves_with_cwd_elsewhere(layout):
    project, repo, _ = layout
    r = _touch(repo / "raw/parenting/a.png")
    assert resolve_media_path("raw/parenting/a.png", project) == r


def test_cwd_relative_still_resolves(layout):
    project, _, cwd = layout
    c = _touch(cwd / "local/b.png")
    assert resolve_media_path("local/b.png", project) == c


def test_nothing_exists_returns_the_project_candidate(layout):
    project, _, _ = layout
    assert resolve_media_path("missing/c.png", project) == project / "missing/c.png"


def test_without_project_root_repo_then_cwd(layout):
    _, repo, cwd = layout
    assert media_path_candidates("x.png", None) == [repo / "x.png", cwd / "x.png"]
    assert resolve_media_path("x.png", None) == repo / "x.png"


def test_expanduser(layout, tmp_path, monkeypatch):
    project, _, _ = layout
    home = tmp_path / "home"
    h = _touch(home / "media/d.png")
    monkeypatch.setenv("HOME", str(home))
    assert media_path_candidates("~/media/d.png", project) == [h]
    assert resolve_media_path("~/media/d.png", project) == h


def test_candidates_that_resolve_to_the_same_file_are_dropped(layout, monkeypatch):
    project, repo, _ = layout
    monkeypatch.chdir(repo)  # the usual launcher case: cwd is the repo root
    assert media_path_candidates("raw/x.png", project) == [project / "raw/x.png", repo / "raw/x.png"]
    assert media_path_candidates("raw/x.png", repo) == [repo / "raw/x.png"]


def test_validator_and_renderers_agree_on_project_relative_paths(tmp_path, monkeypatch):
    """`pipeline validate` and the renderers must pick the same file (Sprint 9 hub-smoke
    defect: the validator found project/source/clip.mp4, the renderer looked in cwd)."""
    from pipeline.composer import clip, refit
    from pipeline.director import storyboard_validator as validator

    project = tmp_path / "project"
    clip_file = _touch(project / "source/clip.mp4")
    img = _touch(project / "source/img.png")
    refit_img = _touch(project / "source/img.refit.png")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    clip_visual = {"type": "clip", "path": "source/clip.mp4"}
    refit_visual = {"type": "article_image", "path": "source/img.png",
                    "refit_path": "source/img.refit.png"}
    plain_visual = {"type": "article_image", "path": "source/img.png"}

    assert validator._clip_visual_path(clip_visual, project) == clip_file
    assert clip._resolve_source_video(clip_visual, None, project_root=project) == clip_file
    assert validator._effective_visual_path(refit_visual, project) == refit_img
    assert refit.effective_image_path(refit_visual, project_root=project) == refit_img
    assert validator._effective_visual_path(plain_visual, project) == img
    assert refit.effective_image_path(plain_visual, project_root=project) == img
