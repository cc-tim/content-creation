"""One resolver for storyboard media paths (`clip`, `article_image`, `image`).

`pipeline validate`, compose and the still-gate all resolve `visual.path` and
`visual.refit_path` through here, so a storyboard that validates clean renders the
same files. Spec: docs/superpowers/specs/2026-09-29-e5-loud-failure-sweep-design.md §5.5
"""
from __future__ import annotations

from pathlib import Path

# src/pipeline/utils/paths.py -> parents[3] is the checkout root. Real storyboards use
# repo-root-relative paths (raw/..., through the repo's /raw symlink); this candidate
# keeps them resolving when the launcher's cwd is not the repo root.
REPO_ROOT: Path = Path(__file__).resolve().parents[3]


def media_path_candidates(raw: str | Path, project_root: Path | None) -> list[Path]:
    """Candidate files for *raw*, highest priority first. No existence checks.

    `~` is expanded. An absolute path is its own only candidate. A relative path tries
    project_root/raw (when project_root is given), REPO_ROOT/raw, then cwd/raw. A
    candidate that resolves to the same path as an earlier one is dropped.
    """
    path = Path(raw).expanduser()
    if path.is_absolute():
        return [path]
    bases = [base for base in (project_root, REPO_ROOT, Path.cwd()) if base is not None]
    candidates: list[Path] = []
    seen: set[Path] = set()
    for base in bases:
        candidate = base / path
        key = candidate.resolve()
        if key not in seen:
            seen.add(key)
            candidates.append(candidate)
    return candidates


def resolve_media_path(raw: str | Path, project_root: Path | None) -> Path:
    """The first candidate that exists; if none does, the first candidate (the path an
    error message should name)."""
    candidates = media_path_candidates(raw, project_root)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]
