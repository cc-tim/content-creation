from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from pipeline.explainer import Manifest

ItemStatusValue = Literal["used", "modified", "missing", "user_skipped"]
ItemCategory = Literal[
    "verbatim_line",
    "key_fact",
    "required_image",
    "required_clip",
    "required_sequence",
]


class ItemStatus(BaseModel):
    item_id: str           # e.g. "verbatim_line:0"
    category: ItemCategory
    label: str             # display text
    status: ItemStatusValue
    auto_checked: bool


class VerifierResult(BaseModel):
    items: list[ItemStatus]
    used_count: int
    missing_count: int
    skipped_count: int


@dataclass
class VerifierState:
    skipped: set[str] = field(default_factory=set)
    manual_checked: set[str] = field(default_factory=set)


def load_verifier_state(path: Path) -> VerifierState:
    if not path.exists():
        return VerifierState()
    raw = json.loads(path.read_text(encoding="utf-8"))
    return VerifierState(
        skipped=set(raw.get("skipped", [])),
        manual_checked=set(raw.get("manual_checked", [])),
    )


def save_verifier_state(
    path: Path,
    *,
    skipped: set[str],
    manual_checked: set[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"skipped": sorted(skipped), "manual_checked": sorted(manual_checked)},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _haystack_for_lines(storyboard: dict[str, Any]) -> str:
    parts: list[str] = []
    for scene in storyboard.get("scenes", []):
        parts.append(scene.get("narration", "") or "")
        overlay = scene.get("overlay") or {}
        if isinstance(overlay, dict):
            parts.append(overlay.get("text", "") or "")
        for sub in scene.get("subtitles", []) or []:
            if isinstance(sub, dict):
                parts.append(sub.get("text", "") or "")
            else:
                parts.append(str(sub))
    return "\n".join(parts)


def _scene_visual_paths(storyboard: dict[str, Any]) -> set[str]:
    paths: set[str] = set()
    for scene in storyboard.get("scenes", []):
        visual = scene.get("visual") or {}
        if isinstance(visual, dict) and visual.get("path"):
            paths.add(visual["path"])
    return paths


def _resolve_status(
    item_id: str,
    auto_status: ItemStatusValue,
    state: VerifierState | None,
) -> ItemStatusValue:
    if state is None:
        return auto_status
    if item_id in state.skipped:
        return "user_skipped"
    if item_id in state.manual_checked:
        return "used"
    return auto_status


def run_auto_checks(
    manifest: Manifest,
    storyboard: dict[str, Any],
    *,
    state: VerifierState | None = None,
) -> VerifierResult:
    haystack = _haystack_for_lines(storyboard)
    visual_paths = _scene_visual_paths(storyboard)

    items: list[ItemStatus] = []

    for i, line in enumerate(manifest.verbatim_lines):
        auto = "used" if line in haystack else "missing"
        item_id = f"verbatim_line:{i}"
        items.append(ItemStatus(
            item_id=item_id,
            category="verbatim_line",
            label=line,
            status=_resolve_status(item_id, auto, state),
            auto_checked=True,
        ))

    for i, fact in enumerate(manifest.key_facts):
        item_id = f"key_fact:{i}"
        items.append(ItemStatus(
            item_id=item_id,
            category="key_fact",
            label=fact,
            status=_resolve_status(item_id, "missing", state),
            auto_checked=False,
        ))

    for i, image in enumerate(manifest.required_images):
        auto = "used" if image.path in visual_paths else "missing"
        item_id = f"required_image:{i}"
        items.append(ItemStatus(
            item_id=item_id,
            category="required_image",
            label=image.path,
            status=_resolve_status(item_id, auto, state),
            auto_checked=True,
        ))

    for i, clip in enumerate(manifest.required_clips):
        auto = "used" if clip.path in visual_paths else "missing"
        item_id = f"required_clip:{i}"
        items.append(ItemStatus(
            item_id=item_id,
            category="required_clip",
            label=clip.path,
            status=_resolve_status(item_id, auto, state),
            auto_checked=True,
        ))

    for i, seq in enumerate(manifest.required_sequence):
        item_id = f"required_sequence:{i}"
        items.append(ItemStatus(
            item_id=item_id,
            category="required_sequence",
            label=seq,
            status=_resolve_status(item_id, "missing", state),
            auto_checked=False,
        ))

    used = sum(1 for it in items if it.status == "used")
    missing = sum(1 for it in items if it.status == "missing")
    skipped = sum(1 for it in items if it.status == "user_skipped")

    return VerifierResult(
        items=items,
        used_count=used,
        missing_count=missing,
        skipped_count=skipped,
    )
