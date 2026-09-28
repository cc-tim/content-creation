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


def _str_constants_by_scope(tree: ast.Module):
    """Yield (enclosing Class.function qualname, text) for every str constant,
    f-string parts included."""

    def visit(node: ast.AST, scope: tuple[str, ...]):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                yield from visit(child, (*scope, child.name))
                continue
            if isinstance(child, ast.Constant) and isinstance(child.value, str):
                yield ".".join(scope), child.value
            yield from visit(child, scope)

    yield from visit(tree, ())


def test_no_black_fallback_helpers_remain():
    from pipeline.composer import image_sequence
    from pipeline.stages.compose import ComposeStage

    assert not hasattr(ComposeStage, "_black_screen")
    assert not hasattr(image_sequence, "_black_clip")


def test_black_lavfi_source_only_in_silence_gap():
    """A black lavfi source is legitimate only for pause_after_sec gaps (black by design).
    Anywhere else it is a stand-in that hides a failed scene."""
    hits = set()
    for py in sorted(PKG.rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for scope, text in _str_constants_by_scope(tree):
            if "color=c=black" in text:
                hits.add((py.relative_to(PKG).as_posix(), scope))
    assert hits == {("stages/compose.py", "ComposeStage._silence_gap")}
