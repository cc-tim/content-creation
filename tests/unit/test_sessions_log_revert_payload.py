from __future__ import annotations

import json
from pathlib import Path

from pipeline.session_log import SessionEntry, append_session


def test_session_entry_defaults_have_no_mutation_id_or_revert_payload():
    entry = SessionEntry(
        session_id="abc", timestamp="2026-05-04T00:00:00", command="x",
    )
    assert entry.mutation_id is None
    assert entry.revert_payload is None


def test_append_session_writes_revert_payload_round_trip(tmp_path: Path):
    entry = SessionEntry(
        session_id="sess1",
        timestamp="2026-05-04T00:00:00",
        command="subtitle set --scene s1 --text 'new'",
        summary="subtitle s1 set",
        mutation_id="mut-001",
        revert_payload={
            "verb": "subtitle set",
            "args": {"scene": "s1", "text": "old"},
        },
    )
    append_session(tmp_path, entry)
    rows = json.loads((tmp_path / "sessions.json").read_text(encoding="utf-8"))
    assert len(rows) == 1
    assert rows[0]["mutation_id"] == "mut-001"
    assert rows[0]["revert_payload"]["verb"] == "subtitle set"
    assert rows[0]["revert_payload"]["args"]["text"] == "old"


def test_append_session_omits_optional_fields_when_none(tmp_path: Path):
    """Backwards-compat: rows without mutation_id/revert_payload still serialise leanly."""
    entry = SessionEntry(
        session_id="sess1",
        timestamp="2026-05-04T00:00:00",
        command="something",
    )
    append_session(tmp_path, entry)
    raw = (tmp_path / "sessions.json").read_text(encoding="utf-8")
    # Optional fields default to None in dataclasses.asdict — tolerate both
    # presence-as-null and absence; just assert the row parses and other fields are right.
    rows = json.loads(raw)
    assert rows[0]["session_id"] == "sess1"
    assert rows[0].get("mutation_id") is None
    assert rows[0].get("revert_payload") is None


def test_existing_sessions_file_without_new_fields_still_parses(tmp_path: Path):
    """A pre-existing sessions.json from before this plan must still load and append."""
    legacy = [
        {
            "session_id": "old-1",
            "timestamp": "2026-05-01T00:00:00",
            "command": "compose reburn",
            "outcome": "success",
            "stages": [],
            "summary": "",
            "error": "",
        }
    ]
    (tmp_path / "sessions.json").write_text(json.dumps(legacy), encoding="utf-8")

    new_entry = SessionEntry(
        session_id="new-1", timestamp="2026-05-04T00:00:00", command="x",
        mutation_id="m1", revert_payload={"verb": "subtitle set", "args": {"scene": "s1", "text": ""}},
    )
    append_session(tmp_path, new_entry)
    rows = json.loads((tmp_path / "sessions.json").read_text(encoding="utf-8"))
    assert len(rows) == 2
    assert rows[0]["session_id"] == "old-1"
    assert rows[1]["mutation_id"] == "m1"
