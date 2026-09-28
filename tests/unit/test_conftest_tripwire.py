"""The suite-wide quota tripwire (tests/conftest.py): no unit test may reach the real
`claude` binary by accident, even when the dev machine has one installed and on PATH.

tests/integration/test_llm_cli.py's own visibility of the real binary is verified
separately (--collect-only), not here — the tripwire is a per-test fixture and the
integration test's skipif is a module-level check evaluated at collection time, before
any fixture runs.
"""
import os

from pipeline.config import PipelineConfig
from pipeline.llm import resolve_claude_bin


def test_tripwire_defaults_claude_bin_to_a_nonexistent_path():
    assert os.environ.get("PIPELINE_CLAUDE_BIN") == "/nonexistent/claude-tripwire"
    assert resolve_claude_bin(PipelineConfig()) is None


def test_a_tests_own_monkeypatch_still_wins_over_the_tripwire(monkeypatch, tmp_path):
    exe = tmp_path / "claude"
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)
    monkeypatch.setenv("PIPELINE_CLAUDE_BIN", str(exe))
    assert resolve_claude_bin(PipelineConfig()) == str(exe)
