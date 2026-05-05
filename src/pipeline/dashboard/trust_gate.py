"""Trust gate classifier for dashboard-driven mutations."""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any, Literal

from pipeline.storyboard import Scene, Storyboard

Tier = Literal["auto_apply", "propose"]

_TEXT_ONLY_VERBS = {"subtitle set", "overlay set", "narration regen"}
_AUTO_APPLY_CHURN_THRESHOLD = 0.80


def classify_tier(verb: str, args: dict[str, Any], storyboard: Storyboard) -> Tier:
    """Classify a mutation as immediate auto-apply or explicit proposal.

    Only small, text-only, single-scene mutations auto-apply. Unknown verbs,
    multi-scene verbs, costly verbs, and large text rewrites propose first.
    """
    if verb not in _TEXT_ONLY_VERBS:
        return "propose"

    scene_id = args.get("scene")
    if not isinstance(scene_id, str):
        return "propose"

    scene = storyboard.get_scene(scene_id)
    if scene is None:
        return "propose"

    new_text = args.get("text")
    if not isinstance(new_text, str):
        return "propose"

    old_text = _existing_text(verb, scene)
    if _char_churn_ratio(old_text, new_text) >= _AUTO_APPLY_CHURN_THRESHOLD:
        return "propose"
    return "auto_apply"


def _existing_text(verb: str, scene: Scene) -> str:
    if verb == "subtitle set":
        return scene.subtitle_override if scene.subtitle_override is not None else scene.narration
    if verb == "overlay set":
        return str(scene.overlay.get("text") or "") if isinstance(scene.overlay, dict) else ""
    if verb == "narration regen":
        return scene.narration
    return ""


def _char_churn_ratio(old: str, new: str) -> float:
    if not old and not new:
        return 0.0
    return 1.0 - SequenceMatcher(a=old, b=new).ratio()
