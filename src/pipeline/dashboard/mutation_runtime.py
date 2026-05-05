"""Mutation runtime models, revert snapshots, apply path, and coordinator."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from pipeline.session_log import SessionEntry, append_session, new_session_id
from pipeline.storyboard import NarrationSource, Storyboard, Transition

logger = logging.getLogger(__name__)

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


def apply_mutation(proposal: MutationProposal, *, project_root: Path) -> MutationResult:
    """Apply a mutation directly to a project's storyboard and session log."""
    storyboard_path = project_root / "storyboard.json"
    if not storyboard_path.exists():
        return MutationResult(status="failed", message="storyboard.json not found")

    storyboard = Storyboard.load(storyboard_path)
    revert_payload = compute_revert_payload(
        verb=proposal.verb,
        args=proposal.args,
        storyboard=storyboard,
    )

    try:
        summary = _dispatch_in_process(storyboard, proposal, project_root=project_root)
    except (KeyError, ValueError) as exc:
        return MutationResult(status="failed", message=str(exc))
    except Exception as exc:  # pragma: no cover - defensive boundary for proxy callers.
        logger.exception("Unexpected mutation apply failure for verb %s", proposal.verb)
        return MutationResult(status="failed", message=f"{type(exc).__name__}: {exc}")

    storyboard.save(storyboard_path)
    mutation_id = uuid.uuid4().hex[:12]
    append_session(
        project_root,
        SessionEntry(
            session_id=new_session_id(),
            timestamp=datetime.now().isoformat(timespec="seconds"),
            command=_command_string(proposal),
            summary=summary,
            mutation_id=mutation_id,
            revert_payload=revert_payload,
        ),
    )
    return MutationResult(status="applied", mutation_id=mutation_id, message=summary)


def _dispatch_in_process(
    storyboard: Storyboard,
    proposal: MutationProposal,
    *,
    project_root: Path,
) -> str:
    verb = proposal.verb
    args = proposal.args

    if verb == "subtitle set":
        scene = _require_scene(storyboard, args["scene"])
        scene.subtitle_override = args["text"]
        return f"subtitle set {scene.id}: {args['text'][:40]}"

    if verb == "overlay set":
        scene = _require_scene(storyboard, args["scene"])
        overlay = dict(scene.overlay) if isinstance(scene.overlay, dict) else {}
        overlay["text"] = args["text"]
        scene.overlay = overlay
        return f"overlay set {scene.id}: {args['text'][:40]}"

    if verb == "narration regen":
        scene = _require_scene(storyboard, args["scene"])
        scene.narration = args["text"]
        return f"narration regen {scene.id}: {args['text'][:40]}"

    if verb == "transition set":
        from_scene = args["from"]
        to_scene = args["to"]
        _require_scene(storyboard, from_scene)
        _require_scene(storyboard, to_scene)
        storyboard.transitions = [
            transition
            for transition in storyboard.transitions
            if not (
                transition.from_scene == from_scene
                and transition.to_scene == to_scene
            )
        ]
        storyboard.transitions.append(
            Transition(
                from_scene=from_scene,
                to_scene=to_scene,
                style=args["style"],
                duration_sec=float(args["duration_sec"]),
                sfx=args.get("sfx"),
            )
        )
        return f"transition set {from_scene} to {to_scene}: {args['style']}"

    if verb == "transition clear":
        from_scene = args["from"]
        to_scene = args["to"]
        _require_scene(storyboard, from_scene)
        _require_scene(storyboard, to_scene)
        before = len(storyboard.transitions)
        storyboard.transitions = [
            transition
            for transition in storyboard.transitions
            if not (
                transition.from_scene == from_scene
                and transition.to_scene == to_scene
            )
        ]
        if len(storyboard.transitions) == before:
            return f"transition clear {from_scene} to {to_scene}: nothing to clear"
        return f"transition clear {from_scene} to {to_scene}"

    if verb == "image regen":
        scene = _require_scene(storyboard, args["scene"])
        visual = dict(scene.visual or {})
        visual["prompt"] = args.get("prompt", "")
        if "tier" in args:
            visual["tier"] = args["tier"]
        scene.visual = visual
        _delete_image_cache_for_scene(project_root, scene.id)
        return f"image regen {scene.id}: tier={visual.get('tier', 'draft')}"

    if verb == "narration set-source":
        scene = _require_scene(storyboard, args["scene"])
        scene.narration_source = NarrationSource(
            engine=args["engine"],
            voice=args.get("voice"),
            file=args.get("file"),
        )
        return f"narration set-source {scene.id}: engine={args['engine']}"

    raise ValueError(f"unknown verb {verb!r}")


def _require_scene(storyboard: Storyboard, scene_id: str):
    scene = storyboard.get_scene(scene_id)
    if scene is None:
        raise KeyError(f"scene {scene_id!r} not found")
    return scene


def _delete_image_cache_for_scene(project_root: Path, scene_id: str) -> None:
    images_dir = project_root / "images"
    if images_dir.exists():
        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            path = images_dir / f"{scene_id}{ext}"
            if path.exists():
                path.unlink()

    scenes_dir = project_root / "compose" / "scenes"
    if scenes_dir.exists():
        for suffix in ("_final.mp4", "_final_no_overlay.mp4"):
            path = scenes_dir / f"{scene_id}{suffix}"
            if path.exists():
                path.unlink()


def _command_string(proposal: MutationProposal) -> str:
    options = " ".join(f"--{key} {value!r}" for key, value in proposal.args.items())
    return f"{proposal.verb} {options}".strip()
