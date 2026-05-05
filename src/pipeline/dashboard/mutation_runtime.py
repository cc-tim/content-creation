"""Mutation runtime models, revert snapshots, apply path, and coordinator."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from pipeline.storyboard import Storyboard, Transition

ProposalStatus = Literal["applied", "cancelled", "failed"]


class MutationProposal(BaseModel):
    """Mutation request posted by the agent-side proxy."""

    job_id: str
    verb: str
    args: dict[str, Any]


class MutationResult(BaseModel):
    """Terminal result returned to the mutation proxy."""

    status: ProposalStatus
    mutation_id: str | None = None
    message: str = ""


class MutationProposed(BaseModel):
    """Interim response for proposal-gated mutations."""

    status: Literal["proposed"] = "proposed"
    mutation_id: str
    proposal_message: str = ""


def compute_revert_payload(
    *,
    verb: str,
    args: dict[str, Any],
    storyboard: Storyboard,
) -> dict[str, Any] | None:
    """Return the inverse mutation payload for a known verb, if one exists."""
    if verb == "subtitle set":
        scene = storyboard.get_scene(args.get("scene"))
        if scene is None:
            return None
        text = scene.subtitle_override if scene.subtitle_override is not None else scene.narration
        return {"verb": "subtitle set", "args": {"scene": scene.id, "text": text}}

    if verb == "overlay set":
        scene = storyboard.get_scene(args.get("scene"))
        if scene is None:
            return None
        text = str(scene.overlay.get("text") or "") if isinstance(scene.overlay, dict) else ""
        return {"verb": "overlay set", "args": {"scene": scene.id, "text": text}}

    if verb == "narration regen":
        scene = storyboard.get_scene(args.get("scene"))
        if scene is None:
            return None
        return {
            "verb": "narration regen",
            "args": {"scene": scene.id, "text": scene.narration},
        }

    if verb == "transition set":
        existing = _find_transition(storyboard, args.get("from"), args.get("to"))
        if existing is None:
            return {
                "verb": "transition clear",
                "args": {"from": args.get("from"), "to": args.get("to")},
            }
        return {"verb": "transition set", "args": _transition_args(existing)}

    if verb == "transition clear":
        existing = _find_transition(storyboard, args.get("from"), args.get("to"))
        if existing is None:
            return None
        return {"verb": "transition set", "args": _transition_args(existing)}

    if verb == "image regen":
        scene = storyboard.get_scene(args.get("scene"))
        if scene is None:
            return None
        visual = scene.visual or {}
        return {
            "verb": "image regen",
            "args": {
                "scene": scene.id,
                "prompt": visual.get("prompt", ""),
                "tier": visual.get("tier", "draft"),
            },
        }

    return None


def _find_transition(
    storyboard: Storyboard,
    from_scene: str | None,
    to_scene: str | None,
) -> Transition | None:
    if from_scene is None or to_scene is None:
        return None
    for transition in storyboard.transitions:
        if transition.from_scene == from_scene and transition.to_scene == to_scene:
            return transition
    return None


def _transition_args(transition: Transition) -> dict[str, Any]:
    return {
        "from": transition.from_scene,
        "to": transition.to_scene,
        "style": transition.style,
        "duration_sec": transition.duration_sec,
        "sfx": transition.sfx,
    }
