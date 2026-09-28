import json
import stat
import sys
import threading
from pathlib import Path

import pytest

from pipeline import llm

FAKE = r'''#!{python}
import json, os, sys, time
log = os.environ["FAKE_CLAUDE_LOG"]
mode = os.environ.get("FAKE_CLAUDE_MODE", "ok")
stdin = sys.stdin.read()
watch_names = ["ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
               "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_OAUTH_TOKEN"]
rec = {{"argv": sys.argv[1:], "stdin": stdin, "cwd": os.getcwd(),
        "env_present": {{n: (n in os.environ) for n in watch_names}}, "t0": time.time()}}
if mode == "sleep":
    time.sleep(0.3)
rec["t1"] = time.time()
with open(log, "a") as f:
    f.write(json.dumps(rec) + "\n")
def ev(**kw):
    print(json.dumps(kw), flush=True)
print("warning: this is not json")
ev(type="system", subtype="init")
if mode == "exit":
    print("boom on stderr", file=sys.stderr); sys.exit(2)
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
                          "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX"]


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


def test_auth_failure_hints_claude_login(fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "auth")
    with pytest.raises(llm.LLMError, match="Please run /login") as ei:
        llm.complete("x", tier="check", call_site="t")
    assert "claude login" in ei.value.hint


def test_last_result_event_wins(fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "two_results")
    r = llm.complete("x", tier="check", call_site="t")
    assert r.text == "second"


def test_timeout_raises_llm_error(fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "sleep")
    with pytest.raises(llm.LLMError, match="timed out"):
        llm.complete("x", tier="check", call_site="t", timeout=0.05)


def test_missing_binary_raises_llm_error(monkeypatch, tmp_path):
    monkeypatch.setenv("PIPELINE_CLAUDE_BIN", str(tmp_path / "nope"))
    with pytest.raises(llm.LLMError, match="claude CLI not found"):
        llm.complete("x", tier="check", call_site="t")


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


def test_unknown_backend_is_loud(monkeypatch):
    monkeypatch.setenv("PIPELINE_LLM_BACKEND", "carrier-pigeon")
    with pytest.raises(llm.LLMError, match="unknown LLM backend"):
        llm.complete("x", tier="check", call_site="t")
