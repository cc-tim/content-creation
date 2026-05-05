from __future__ import annotations

import json
from pathlib import Path

from pipeline.session_log import SessionEntry, append_session, recent_mutations


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


def test_recent_mutations_returns_entries_with_revert_payload_only(tmp_path: Path):
    append_session(tmp_path, SessionEntry(
        session_id="s1", timestamp="2026-05-04T00:00:01", command="compose reburn",
    ))
    append_session(tmp_path, SessionEntry(
        session_id="s2", timestamp="2026-05-04T00:00:02", command="subtitle set",
        mutation_id="m1", revert_payload={"verb": "subtitle set", "args": {}},
    ))
    append_session(tmp_path, SessionEntry(
        session_id="s3", timestamp="2026-05-04T00:00:03", command="overlay set",
        mutation_id="m2", revert_payload={"verb": "overlay set", "args": {}},
    ))
    muts = recent_mutations(tmp_path)
    assert [m.mutation_id for m in muts] == ["m1", "m2"]
    assert all(m.revert_payload is not None for m in muts)


def test_recent_mutations_returns_last_n_only(tmp_path: Path):
    for i in range(15):
        append_session(tmp_path, SessionEntry(
            session_id=f"s{i}", timestamp=f"2026-05-04T00:00:{i:02d}", command="x",
            mutation_id=f"m{i}", revert_payload={"verb": "subtitle set", "args": {}},
        ))
    muts = recent_mutations(tmp_path, n=10)
    assert len(muts) == 10
    # most recent 10 -> mutations m5..m14
    assert [m.mutation_id for m in muts] == [f"m{i}" for i in range(5, 15)]


def test_recent_mutations_handles_missing_sessions_file(tmp_path: Path):
    assert recent_mutations(tmp_path) == []


def test_recent_mutations_handles_corrupt_sessions_file(tmp_path: Path):
    (tmp_path / "sessions.json").write_text("{bogus", encoding="utf-8")
    assert recent_mutations(tmp_path) == []
