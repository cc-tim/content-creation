from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.dashboard.mutation_runtime import (
    MutationProposal,
    MutationResult,
    apply_mutation,
    compute_revert_payload,
)
from pipeline.storyboard import Scene, Storyboard, Transition


def _sb() -> Storyboard:
    return Storyboard(
        scenes=[
            Scene(
                id="s1",
                section="content",
                narration="old narration",
                narration_est_sec=1.0,
                subtitle_override="old subtitle",
                overlay={"text": "old overlay", "y": 100},
            ),
            Scene(id="s2", section="content", narration="b", narration_est_sec=1.0),
        ]
    )


def test_mutation_proposal_round_trips_through_json():
    proposal = MutationProposal(
        job_id="j1",
        verb="subtitle set",
        args={"scene": "s1", "text": "new"},
    )
    raw = proposal.model_dump_json()
    parsed = MutationProposal.model_validate_json(raw)
    assert parsed == proposal


def test_mutation_result_carries_status_and_mutation_id():
    result = MutationResult(status="applied", mutation_id="mut-1", message="ok")
    raw = result.model_dump_json()
    parsed = MutationResult.model_validate_json(raw)
    assert parsed.status == "applied"
    assert parsed.mutation_id == "mut-1"


def test_compute_revert_subtitle_set():
    payload = compute_revert_payload(
        verb="subtitle set",
        args={"scene": "s1", "text": "new subtitle"},
        storyboard=_sb(),
    )
    assert payload == {
        "verb": "subtitle set",
        "args": {"scene": "s1", "text": "old subtitle"},
    }


def test_compute_revert_overlay_set_preserves_other_overlay_keys():
    payload = compute_revert_payload(
        verb="overlay set",
        args={"scene": "s1", "text": "new overlay"},
        storyboard=_sb(),
    )
    assert payload == {
        "verb": "overlay set",
        "args": {"scene": "s1", "text": "old overlay"},
    }


def test_compute_revert_narration_regen():
    payload = compute_revert_payload(
        verb="narration regen",
        args={"scene": "s1", "text": "new narration"},
        storyboard=_sb(),
    )
    assert payload == {
        "verb": "narration regen",
        "args": {"scene": "s1", "text": "old narration"},
    }


def test_compute_revert_transition_set_inverse_is_clear_when_no_existing():
    payload = compute_revert_payload(
        verb="transition set",
        args={"from": "s1", "to": "s2", "style": "fade", "duration_sec": 0.5},
        storyboard=_sb(),
    )
    assert payload == {"verb": "transition clear", "args": {"from": "s1", "to": "s2"}}


def test_compute_revert_transition_set_inverse_is_set_when_existing():
    sb = _sb()
    sb.transitions.append(
        Transition(
            from_scene="s1",
            to_scene="s2",
            style="page-turn",
            duration_sec=0.3,
            sfx=None,
        )
    )
    payload = compute_revert_payload(
        verb="transition set",
        args={"from": "s1", "to": "s2", "style": "fade", "duration_sec": 0.5},
        storyboard=sb,
    )
    assert payload == {
        "verb": "transition set",
        "args": {
            "from": "s1",
            "to": "s2",
            "style": "page-turn",
            "duration_sec": 0.3,
            "sfx": None,
        },
    }


def test_compute_revert_transition_clear_inverse_is_set():
    sb = _sb()
    sb.transitions.append(
        Transition(
            from_scene="s1",
            to_scene="s2",
            style="fade",
            duration_sec=0.5,
            sfx=None,
        )
    )
    payload = compute_revert_payload(
        verb="transition clear",
        args={"from": "s1", "to": "s2"},
        storyboard=sb,
    )
    assert payload == {
        "verb": "transition set",
        "args": {
            "from": "s1",
            "to": "s2",
            "style": "fade",
            "duration_sec": 0.5,
            "sfx": None,
        },
    }


def test_compute_revert_image_regen_snapshots_old_prompt():
    sb = Storyboard(
        scenes=[
            Scene(
                id="s1",
                section="content",
                narration="x",
                narration_est_sec=1.0,
                visual={"prompt": "old prompt", "tier": "draft"},
            )
        ]
    )
    payload = compute_revert_payload(
        verb="image regen",
        args={"scene": "s1", "prompt": "new prompt", "tier": "production"},
        storyboard=sb,
    )
    assert payload == {
        "verb": "image regen",
        "args": {"scene": "s1", "prompt": "old prompt", "tier": "draft"},
    }


def test_compute_revert_unknown_verb_returns_none():
    payload = compute_revert_payload(
        verb="future verb",
        args={"scene": "s1"},
        storyboard=_sb(),
    )
    assert payload is None


def _project_with_sb(tmp_path: Path, sb: Storyboard) -> Path:
    project_root = tmp_path / "projects" / "42"
    project_root.mkdir(parents=True)
    sb.save(project_root / "storyboard.json")
    return project_root


def test_apply_subtitle_set_writes_storyboard_and_session_entry(tmp_path: Path):
    project_root = _project_with_sb(tmp_path, _sb())
    proposal = MutationProposal(
        job_id="j1",
        verb="subtitle set",
        args={"scene": "s1", "text": "the new subtitle"},
    )
    result = apply_mutation(proposal, project_root=project_root)
    assert result.status == "applied"
    assert result.mutation_id is not None

    loaded = Storyboard.load(project_root / "storyboard.json")
    assert loaded.get_scene("s1").subtitle_override == "the new subtitle"

    rows = json.loads((project_root / "sessions.json").read_text(encoding="utf-8"))
    last = rows[-1]
    assert last["mutation_id"] == result.mutation_id
    assert last["revert_payload"]["verb"] == "subtitle set"
    assert last["revert_payload"]["args"]["text"] == "old subtitle"


def test_apply_overlay_set_preserves_other_overlay_keys(tmp_path: Path):
    project_root = _project_with_sb(tmp_path, _sb())
    proposal = MutationProposal(
        job_id="j1",
        verb="overlay set",
        args={"scene": "s1", "text": "new overlay"},
    )
    result = apply_mutation(proposal, project_root=project_root)
    assert result.status == "applied"

    loaded = Storyboard.load(project_root / "storyboard.json")
    scene = loaded.get_scene("s1")
    assert scene.overlay["text"] == "new overlay"
    assert scene.overlay["y"] == 100


def test_apply_unknown_scene_returns_failed_with_message(tmp_path: Path):
    project_root = _project_with_sb(tmp_path, _sb())
    proposal = MutationProposal(
        job_id="j1",
        verb="subtitle set",
        args={"scene": "s99", "text": "x"},
    )
    result = apply_mutation(proposal, project_root=project_root)
    assert result.status == "failed"
    assert "s99" in result.message


def test_apply_unknown_verb_returns_failed(tmp_path: Path):
    project_root = _project_with_sb(tmp_path, _sb())
    proposal = MutationProposal(job_id="j1", verb="future verb", args={})
    result = apply_mutation(proposal, project_root=project_root)
    assert result.status == "failed"
    assert "unknown" in result.message.lower() or "future verb" in result.message


def test_apply_transition_set_writes_to_storyboard(tmp_path: Path):
    project_root = _project_with_sb(tmp_path, _sb())
    proposal = MutationProposal(
        job_id="j1",
        verb="transition set",
        args={"from": "s1", "to": "s2", "style": "fade", "duration_sec": 0.5},
    )
    result = apply_mutation(proposal, project_root=project_root)
    assert result.status == "applied"

    loaded = Storyboard.load(project_root / "storyboard.json")
    assert len(loaded.transitions) == 1
    assert loaded.transitions[0].style == "fade"
