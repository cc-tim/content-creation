from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import structlog
import yaml

from pipeline.stages.base import PipelineContext

logger = structlog.get_logger()

DEFAULT_STRATEGIES_DIR = Path("configs/promo-strategies")


def _predicate_always(_ctx: PipelineContext, value: Any) -> bool:
    return bool(value)


def _predicate_target_locale_differs_from_source(ctx: PipelineContext, value: Any) -> bool:
    if not bool(value):
        return True  # predicate with value: false means "skip this check"
    if ctx.source_locale is None:
        return False
    return ctx.locale != ctx.source_locale


PREDICATES: dict[str, Callable[[PipelineContext, Any], bool]] = {
    "always": _predicate_always,
    "target_locale_differs_from_source": _predicate_target_locale_differs_from_source,
}


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str] | None:
    """Return (frontmatter_dict, body) or None if malformed / missing."""
    if not text.startswith("---"):
        return None
    try:
        end = text.index("\n---", 3)
    except ValueError:
        return None
    raw = text[3:end].strip()
    body_start = end + len("\n---")
    # Consume a trailing newline after closing ---
    if body_start < len(text) and text[body_start] == "\n":
        body_start += 1
    body = text[body_start:]
    try:
        data = yaml.safe_load(raw) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    return data, body


def _applies(ctx: PipelineContext, applies_when: dict[str, Any]) -> bool:
    for key, value in applies_when.items():
        predicate = PREDICATES.get(key)
        if predicate is None:
            logger.warning("strategies.unknown_predicate", key=key)
            return False
        if not predicate(ctx, value):
            return False
    return True


def load_strategies(
    ctx: PipelineContext, strategies_dir: Path | None = None
) -> str:
    """Load all strategy .md files whose applies_when matches ctx.

    Returns a single string ready to inject into a prompt, or empty string
    if no strategies apply / the directory is missing.
    """
    directory = strategies_dir if strategies_dir is not None else DEFAULT_STRATEGIES_DIR
    if not directory.exists() or not directory.is_dir():
        logger.debug("strategies.dir_missing", path=str(directory))
        return ""

    sections: list[str] = []
    for path in sorted(directory.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        parsed = _parse_frontmatter(text)
        if parsed is None:
            logger.warning("strategies.malformed_frontmatter", path=str(path))
            continue
        fm, body = parsed
        name = fm.get("name", path.stem)
        description = fm.get("description", "")
        applies_when = fm.get("applies_when") or {}
        if not isinstance(applies_when, dict):
            logger.warning("strategies.invalid_applies_when", path=str(path))
            continue
        if not _applies(ctx, applies_when):
            continue
        sections.append(f"### {name} — {description}\n{body.strip()}")

    if not sections:
        return ""
    header = "LOADED STRATEGIES (apply these when writing narration, title, and description):\n\n"
    return header + "\n\n".join(sections) + "\n"
