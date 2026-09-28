import json
import stat
import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pipeline import llm

FAKE = r'''#!{python}
import json, os, sys, time
log = os.environ["FAKE_CLAUDE_LOG"]
mode = os.environ.get("FAKE_CLAUDE_MODE", "ok")
stdin = sys.stdin.read()
watch_names = ["ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
               "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_OAUTH_TOKEN",
               "CLAUDE_CODE_USE_FOUNDRY", "ANTHROPIC_MODEL"]
rec = {{"argv": sys.argv[1:], "stdin": stdin, "cwd": os.getcwd(),
        "env_present": {{n: (n in os.environ) for n in watch_names}}, "t0": time.time()}}
if mode == "sleep":
    time.sleep(0.3)
if mode == "sleep_stderr":
    print("partial output: engine warming up", file=sys.stderr, flush=True)
    time.sleep(3.0)
rec["t1"] = time.time()
with open(log, "a") as f:
    f.write(json.dumps(rec) + "\n")
def ev(**kw):
    print(json.dumps(kw), flush=True)
print("warning: this is not json")
ev(type="system", subtype="init")
if mode == "exit":
    print("boom on stderr", file=sys.stderr); sys.exit(2)
if mode == "error_subtype":
    ev(type="result", subtype="error_max_structured_output_retries", is_error=True,
       errors=["schema validation failed"])
    sys.exit(1)
if mode == "limit":
    ev(type="result", subtype="success", is_error=True, api_error_status=429,
       result="You've hit your limit · resets 5pm")
    sys.exit(1)
if mode == "auth":
    ev(type="result", subtype="success", is_error=True,
       result="Invalid API key · Please run /login")
    sys.exit(1)
if mode == "empty":
    ev(type="result", subtype="success", is_error=False, result="   "); sys.exit(0)
if mode == "schema":
    ev(type="result", subtype="success", is_error=False, result='{{"title": "T"}}',
       structured_output={{"title": "T"}}); sys.exit(0)
if mode == "schema_text_only":
    ev(type="result", subtype="success", is_error=False, result='{{"title": "T2"}}'); sys.exit(0)
if mode == "schema_garbage":
    ev(type="result", subtype="success", is_error=False, result="not json"); sys.exit(0)
if mode == "two_results":
    ev(type="result", subtype="success", is_error=False, result="first")
    ev(type="result", subtype="success", is_error=False, result="second")
    sys.exit(0)
ev(type="result", subtype="success", is_error=False, result="hello")
'''


@pytest.fixture
def fake_claude(tmp_path, monkeypatch):
    exe = tmp_path / "bin" / "claude"
    exe.parent.mkdir()
    exe.write_text(FAKE.format(python=sys.executable))
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "calls.jsonl"
    monkeypatch.setenv("PIPELINE_CLAUDE_BIN", str(exe))
    monkeypatch.setenv("PIPELINE_LLM_BACKEND", "cli")
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log))
    monkeypatch.delenv("FAKE_CLAUDE_MODE", raising=False)

    def calls():
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
    return calls


def _message(rec):
    return json.loads(rec["stdin"])["message"]


def test_text_call_builds_isolated_argv_and_stdin(fake_claude):
    r = llm.complete("Say hi", tier="check", call_site="t")
    assert (r.text, r.data, r.backend, r.model) == ("hello", None, "cli", "claude-haiku-4-5-20251001")
    (rec,) = fake_claude()
    a = rec["argv"]
    assert a[:1] == ["-p"]
    for flag in ("--input-format", "--output-format"):
        assert a[a.index(flag) + 1] == "stream-json"
    assert "--verbose" in a and "--strict-mcp-config" in a
    assert "--no-session-persistence" in a and "--disable-slash-commands" in a
    assert a[a.index("--tools") + 1] == "" and a[a.index("--setting-sources") + 1] == ""
    assert a[a.index("--model") + 1] == "claude-haiku-4-5-20251001"
    assert a[a.index("--system-prompt") + 1] == llm.NEUTRAL_SYSTEM
    assert "Say hi" not in " ".join(a)                         # prompt via stdin only
    assert _message(rec) == {"role": "user", "content": [{"type": "text", "text": "Say hi"}]}
    assert Path(rec["cwd"]).resolve() != Path.cwd().resolve()   # temp dir, not the repo


def test_creative_tier_uses_opus_and_passes_system(fake_claude):
    llm.complete("x", tier="creative", call_site="t", system="SYS")
    a = fake_claude()[0]["argv"]
    assert a[a.index("--model") + 1] == "claude-opus-5-5"
    assert a[a.index("--system-prompt") + 1] == "SYS"


def test_content_blocks_pass_through_unchanged(fake_claude):
    blocks = [{"type": "text", "text": "look"},
              {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "AAAA"}},
              {"type": "text", "text": "^ scene s1"}]
    llm.complete(blocks, tier="check", call_site="t")
    assert _message(fake_claude()[0])["content"] == blocks


_BILLING_SWITCHING_ENV = ["ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
                          "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX",
                          "CLAUDE_CODE_USE_FOUNDRY", "ANTHROPIC_MODEL"]


@pytest.mark.parametrize("name", _BILLING_SWITCHING_ENV)
def test_billing_switching_env_is_stripped_from_child_env(fake_claude, monkeypatch, name):
    monkeypatch.setenv(name, "leaky-value")
    llm.complete("x", tier="check", call_site="t")
    assert fake_claude()[0]["env_present"][name] is False


def test_oauth_token_passes_through_to_child_env(fake_claude, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "sk-ant-oat-should-pass-through")
    llm.complete("x", tier="check", call_site="t")
    assert fake_claude()[0]["env_present"]["CLAUDE_CODE_OAUTH_TOKEN"] is True


def test_json_schema_reads_structured_output(fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "schema")
    schema = {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]}
    r = llm.complete("x", tier="creative", call_site="t", json_schema=schema)
    assert r.data == {"title": "T"}
    a = fake_claude()[0]["argv"]
    assert json.loads(a[a.index("--json-schema") + 1]) == schema


def test_json_schema_falls_back_to_parsing_result_text(fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "schema_text_only")
    assert llm.complete("x", tier="check", call_site="t", json_schema={"type": "object"}).data == {"title": "T2"}


@pytest.mark.parametrize("mode, needle", [
    ("limit", "You've hit your limit"),        # verbatim quota message + api status
    ("exit", "boom on stderr"),                # non-zero exit, no result event -> stderr tail
    ("empty", "empty result"),
    ("schema_garbage", "no structured output"),
])
def test_failures_raise_llm_error_with_the_real_reason(fake_claude, monkeypatch, mode, needle):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", mode)
    schema = {"type": "object"} if mode == "schema_garbage" else None
    with pytest.raises(llm.LLMError, match=needle) as ei:
        llm.complete("x", tier="check", call_site="proofread", json_schema=schema)
    assert "proofread" in str(ei.value)
    if mode == "limit":
        assert "429" in str(ei.value) and "quota" in ei.value.hint


def test_error_reason_survives_when_result_is_empty_but_subtype_and_errors_exist(fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "error_subtype")
    with pytest.raises(llm.LLMError) as ei:
        llm.complete("x", tier="check", call_site="t")
    assert "schema validation failed" in str(ei.value)
    assert "error_max_structured_output_retries" in str(ei.value)


def test_auth_failure_hints_claude_login(fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "auth")
    with pytest.raises(llm.LLMError, match="Please run /login") as ei:
        llm.complete("x", tier="check", call_site="t")
    assert "claude login" in ei.value.hint


@pytest.mark.parametrize("reason", ["Failed to generate a response", "Written by the author of this book"])
def test_hint_does_not_false_positive_on_substrings(reason):
    assert llm._hint(reason) == ""


def test_hint_quota_for_429_message():
    assert "quota" in llm._hint("Error: 429 too many requests, rate limit exceeded")


def test_hint_login_for_slash_login_message():
    assert "claude login" in llm._hint("Please run /login to continue")


def test_last_result_event_wins(fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "two_results")
    r = llm.complete("x", tier="check", call_site="t")
    assert r.text == "second"


def test_timeout_raises_llm_error(fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "sleep")
    with pytest.raises(llm.LLMError, match="timed out"):
        llm.complete("x", tier="check", call_site="t", timeout=0.05)


def test_timeout_reason_includes_stderr_tail(fake_claude, monkeypatch):
    # Generous margin: on macOS, a freshly-written executable's first exec can be slowed by a
    # Gatekeeper/quarantine check, so the child needs real headroom to start up, flush its
    # partial stderr, and still be caught mid-sleep well before the 3s the fake script sleeps.
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "sleep_stderr")
    with pytest.raises(llm.LLMError, match="engine warming up"):
        llm.complete("x", tier="check", call_site="t", timeout=1.0)


def test_missing_binary_raises_llm_error(monkeypatch, tmp_path):
    bad_path = tmp_path / "nope"
    monkeypatch.setenv("PIPELINE_CLAUDE_BIN", str(bad_path))
    with pytest.raises(llm.LLMError, match="claude CLI not found") as ei:
        llm.complete("x", tier="check", call_site="t")
    assert str(bad_path) in str(ei.value)
    assert "PIPELINE_CLAUDE_BIN" in str(ei.value)


def test_missing_binary_without_explicit_path_uses_generic_message(monkeypatch, tmp_path):
    monkeypatch.delenv("PIPELINE_CLAUDE_BIN", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))         # systemd-like PATH without claude
    monkeypatch.setenv("HOME", str(tmp_path / "home-without-claude"))
    with pytest.raises(llm.LLMError, match="claude CLI not found") as ei:
        llm.complete("x", tier="check", call_site="t")
    assert "install Claude Code" in str(ei.value)


def test_launch_failure_raises_llm_error(monkeypatch, tmp_path):
    exe = tmp_path / "claude"
    exe.write_text("#!/bin/sh\necho hi\n")   # deliberately not chmod +x -> OSError on exec
    monkeypatch.setenv("PIPELINE_CLAUDE_BIN", str(exe))
    monkeypatch.setenv("PIPELINE_LLM_BACKEND", "cli")
    with pytest.raises(llm.LLMError, match="could not launch") as ei:
        llm.complete("x", tier="check", call_site="t")
    assert str(exe) in str(ei.value)
    assert "PIPELINE_CLAUDE_BIN" in ei.value.hint


def test_resolve_falls_back_to_local_bin(monkeypatch, tmp_path):
    home = tmp_path / "home"
    exe = home / ".local" / "bin" / "claude"
    exe.parent.mkdir(parents=True)
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)
    monkeypatch.delenv("PIPELINE_CLAUDE_BIN", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))        # systemd-like PATH without claude
    monkeypatch.setenv("HOME", str(home))
    assert llm.resolve_claude_bin() == str(exe)


def test_concurrency_is_capped(fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "sleep")
    monkeypatch.setenv("PIPELINE_LLM_MAX_CONCURRENCY", "2")
    threads = [threading.Thread(target=llm.complete, args=("x",),
                                kwargs={"tier": "check", "call_site": "t"}) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    spans = [(c["t0"], c["t1"]) for c in fake_claude()]
    peak = max(sum(1 for s in spans if s[0] <= t0 < s[1]) for t0, _ in spans)
    assert len(spans) == 5 and peak <= 2


def _capture_run_timeout(monkeypatch):
    captured: dict[str, float | None] = {}
    real_run = llm.subprocess.run

    def fake_run(*args, **kwargs):
        captured["timeout"] = kwargs.get("timeout")
        return real_run(*args, **kwargs)

    monkeypatch.setattr(llm.subprocess, "run", fake_run)
    return captured


def test_creative_tier_uses_the_longer_default_timeout(fake_claude, monkeypatch):
    captured = _capture_run_timeout(monkeypatch)
    llm.complete("x", tier="creative", call_site="t")
    assert captured["timeout"] == 1200.0


def test_check_tier_uses_the_shorter_default_timeout(fake_claude, monkeypatch):
    captured = _capture_run_timeout(monkeypatch)
    llm.complete("x", tier="check", call_site="t")
    assert captured["timeout"] == 600.0


def test_explicit_timeout_overrides_the_creative_default(fake_claude, monkeypatch):
    captured = _capture_run_timeout(monkeypatch)
    llm.complete("x", tier="creative", call_site="t", timeout=42.0)
    assert captured["timeout"] == 42.0


def test_unknown_backend_is_loud(monkeypatch):
    monkeypatch.setenv("PIPELINE_LLM_BACKEND", "carrier-pigeon")
    with pytest.raises(llm.LLMError, match="unknown LLM backend"):
        llm.complete("x", tier="check", call_site="t")


def _api_env(monkeypatch):
    monkeypatch.setenv("PIPELINE_LLM_BACKEND", "api")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")


def test_api_backend_text(monkeypatch):
    _api_env(monkeypatch)
    resp = MagicMock(content=[MagicMock(type="text", text="hi")])
    with patch("anthropic.Anthropic") as cls:
        cls.return_value.messages.create.return_value = resp
        r = llm.complete("q", tier="creative", call_site="t", system="S", max_tokens=123)
    kw = cls.return_value.messages.create.call_args.kwargs
    assert (r.text, r.backend, kw["model"], kw["system"], kw["max_tokens"]) == \
        ("hi", "api", "claude-opus-5-5", "S", 123)
    assert kw["messages"] == [{"role": "user", "content": [{"type": "text", "text": "q"}]}]


def test_api_backend_schema_defaults_to_emit_tool_name(monkeypatch):
    _api_env(monkeypatch)
    block = MagicMock(type="tool_use", input={"title": "T"})
    with patch("anthropic.Anthropic") as cls:
        cls.return_value.messages.create.return_value = MagicMock(content=[block])
        r = llm.complete("q", tier="check", call_site="t", json_schema={"type": "object"})
    kw = cls.return_value.messages.create.call_args.kwargs
    assert r.data == {"title": "T"} and kw["tool_choice"] == {"type": "tool", "name": "emit"}
    assert kw["tools"][0]["name"] == "emit"


def test_api_backend_schema_uses_caller_supplied_tool_name(monkeypatch):
    _api_env(monkeypatch)
    block = MagicMock(type="tool_use", input={"title": "T"})
    with patch("anthropic.Anthropic") as cls:
        cls.return_value.messages.create.return_value = MagicMock(content=[block])
        r = llm.complete("q", tier="check", call_site="t", json_schema={"type": "object"},
                         schema_name="emit_metadata")
    kw = cls.return_value.messages.create.call_args.kwargs
    assert r.data == {"title": "T"}
    assert kw["tools"][0]["name"] == "emit_metadata"
    assert kw["tool_choice"] == {"type": "tool", "name": "emit_metadata"}


def test_api_backend_errors_are_llm_errors(monkeypatch):
    _api_env(monkeypatch)
    with patch("anthropic.Anthropic") as cls:
        cls.return_value.messages.create.side_effect = RuntimeError("credit balance too low")
        with pytest.raises(llm.LLMError, match="credit balance too low"):
            llm.complete("q", tier="check", call_site="t")
