from __future__ import annotations

from pathlib import Path

from pipeline.cli_compose import _delete_transition_cache_for_scenes


def test_delete_transition_cache_removes_directory(tmp_path: Path):
    """The helper wipes the entire transitions cache directory."""
    compose = tmp_path / "compose"
    transitions = compose / "transitions"
    transitions.mkdir(parents=True)
    (transitions / "abc123.mp4").write_bytes(b"x")
    (transitions / "def456.mp4").write_bytes(b"y")

    _delete_transition_cache_for_scenes(compose, ["s9"])

    assert not transitions.exists()


def test_delete_transition_cache_noop_when_directory_absent(tmp_path: Path):
    """Helper is safe to call when no transition cache exists yet."""
    compose = tmp_path / "compose"
    compose.mkdir()
    # Should not raise.
    _delete_transition_cache_for_scenes(compose, ["s9"])
