"""Fences for the E5 loud-failure sweep: guardrails in code, not docs.

Spec: docs/superpowers/specs/2026-09-29-e5-loud-failure-sweep-design.md §5.6
"""
from __future__ import annotations

import ast
from pathlib import Path

import pipeline

PKG = Path(pipeline.__file__).resolve().parent  # src/pipeline

# Every consumer of storyboard media paths delegates to pipeline.utils.paths.
_MEDIA_PATH_CONSUMERS = (
    "composer/clip.py",
    "composer/refit.py",
    "stages/compose.py",
    "director/storyboard_validator.py",
)


def _parse(rel: str) -> ast.Module:
    path = PKG / rel
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _cwd_call_lines(tree: ast.Module) -> list[int]:
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"cwd", "getcwd"}
    ]


def test_media_resolution_has_one_owner():
    offenders = {rel: _cwd_call_lines(_parse(rel)) for rel in _MEDIA_PATH_CONSUMERS}
    offenders = {rel: lines for rel, lines in offenders.items() if lines}
    assert offenders == {}, (
        f"cwd-relative media resolution outside pipeline/utils/paths.py: {offenders}; "
        "use pipeline.utils.paths.resolve_media_path"
    )
