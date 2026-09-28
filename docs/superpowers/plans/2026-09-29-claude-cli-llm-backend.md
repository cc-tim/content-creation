# Claude CLI LLM Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route every pipeline LLM call through one facade, `pipeline.llm.complete`. Its
default backend is headless `claude -p` on Tim's subscription. The Anthropic SDK remains as an
opt-in backend.

**Architecture:**
- `src/pipeline/llm.py` holds the facade, both backends, `LLMResult` and `LLMError`.
- The CLI backend always runs `claude -p` in stream-json mode (input and output) from a temp
  directory. Isolation flags are on and `ANTHROPIC_API_KEY` is stripped. It parses the last
  `result` event.
- The 12 call sites switch from `client.messages.create` to `llm.complete`. Their prompts and
  parsing stay as they are.

**Tech Stack:** Python 3.13, `subprocess`, pydantic-settings (`PipelineConfig`), pytest, Claude
Code CLI 2.1.283.

**Spec:** `docs/superpowers/specs/2026-09-29-claude-cli-llm-backend-design.md`

**Deviations from the spec's letter** (same capability, and verified by CLI probes on 2026-09-29):
- `complete()` takes `content: str | list[dict]` instead of `images=`. A list is SDK-shaped
  content blocks passed through unchanged. The three image sites already build interleaved
  text+image blocks, and the spec requires their prompts to stay identical.
- The backend always uses `--input-format stream-json --output-format stream-json --verbose`.
  The CLI refuses stream-json input unless the output is also stream-json, and a single path
  serves text and images alike.
- Structured output is read from the `result` event's `structured_output` field. Probe: with
  `--json-schema`, `structured_output` holds the parsed dict and `result` holds the same JSON as
  text.

## Global Constraints

- The default backend is `cli`. `PIPELINE_LLM_BACKEND=api` is the only way to reach the SDK.
  There is no silent fallback in either direction.
- Models:
  - creative tier: `claude-opus-5-5`;
  - check tier: `claude-haiku-4-5-20251001`.
- CLI argv (a list, never a shell string):
  `claude -p --input-format stream-json --output-format stream-json --verbose --model <m> --system-prompt <s> --tools "" --setting-sources "" --strict-mcp-config --no-session-persistence --disable-slash-commands [--json-schema <json>]`
- The system prompt is always passed. Default: `You are a precise assistant. Follow the user's instructions exactly.`
- The child process runs with its cwd set to a fresh temp dir. Its env is the parent env minus
  `ANTHROPIC_API_KEY`. The prompt goes via stdin, never argv.
- Every call site keeps its prompt text, its parsing, and its fatal-vs-advisory behaviour.
- `anthropic>=0.49` stays in `pyproject.toml` (the api backend needs it).
- Unit tests never call the real CLI. Only `tests/integration/test_llm_cli.py`
  (`@pytest.mark.integration`) spends quota.
- Commits are small `type(scope): message`. End each with a blank line and
  `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`. Never stage `tmp/`.

## Review Focus

1. **Under systemd `PATH`, `claude` isn't on PATH.** `resolve_claude_bin` must fall back to
   `~/.local/bin/claude`. Task 1 tests this.
2. **An `ANTHROPIC_API_KEY` in the environment would silently bill the API.** It must be
   stripped from the child env. Task 1 tests this.
3. **Quota, rate-limit and login failures** must reach the user verbatim, with a hint. Task 1
   tests this.
4. **Non-JSON noise lines on stdout** (CLI warnings) must not break parsing. Task 1 tests this.
5. **Very large prompts** (scriptwrite and direct send ~16k-token prompts) must go via stdin, not
   argv. Task 1 asserts the prompt text is absent from argv.

---

### Task 1: `pipeline.llm`: facade, CLI backend and config

**Files:**
- Create: `src/pipeline/llm.py`
- Modify: `src/pipeline/config.py` (add the LLM settings; `CLAUDE_MODEL` is removed in Task 3)
- Test: `tests/unit/test_llm.py`

**Interfaces:**
- Produces:
  - `complete(content: str | list[dict], *, tier: Literal["creative","check"], call_site: str, system: str | None = None, json_schema: dict | None = None, max_tokens: int = 4096, timeout: float | None = None) -> LLMResult`
  - `LLMResult(text: str, data: Any | None, model: str, backend: str)`
  - `LLMError(call_site, reason, hint="")`, a `RuntimeError`
  - `resolve_claude_bin(config=None) -> str | None`
  - `model_for(tier, config=None) -> str`
  - `NEUTRAL_SYSTEM`

- [ ] **Step 1: Add the config fields** to `PipelineConfig` in `src/pipeline/config.py`, next to
  `ANTHROPIC_API_KEY`. The env prefix `PIPELINE_` applies automatically.

```python
    LLM_BACKEND: str = "cli"                                  # "cli" (claude -p, subscription) | "api"
    LLM_MODEL_CREATIVE: str = "claude-opus-5-5"               # analyze, scriptwrite, direct, beats
    LLM_MODEL_CHECK: str = "claude-haiku-4-5-20251001"        # proofread, QC, alignment, storyteller, mla, style anchor
    CLAUDE_BIN: str = ""                                      # explicit path to the claude CLI
    LLM_TIMEOUT_SEC: float = 600.0
    LLM_MAX_CONCURRENCY: int = 4
```

- [ ] **Step 2: Write the failing tests** in `tests/unit/test_llm.py`. A fake `claude`
  executable records what it was given and prints canned stream-json.

```python
import json
import os
import stat
import sys
import threading
import time
from pathlib import Path

import pytest

from pipeline import llm

FAKE = r'''#!{python}
import json, os, sys, time
log = os.environ["FAKE_CLAUDE_LOG"]
mode = os.environ.get("FAKE_CLAUDE_MODE", "ok")
stdin = sys.stdin.read()
rec = {{"argv": sys.argv[1:], "stdin": stdin, "cwd": os.getcwd(),
        "has_api_key": "ANTHROPIC_API_KEY" in os.environ, "t0": time.time()}}
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
if mode == "empty":
    ev(type="result", subtype="success", is_error=False, result="   "); sys.exit(0)
if mode == "schema":
    ev(type="result", subtype="success", is_error=False, result='{{"title": "T"}}',
       structured_output={{"title": "T"}}); sys.exit(0)
if mode == "schema_text_only":
    ev(type="result", subtype="success", is_error=False, result='{{"title": "T2"}}'); sys.exit(0)
if mode == "schema_garbage":
    ev(type="result", subtype="success", is_error=False, result="not json"); sys.exit(0)
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


def test_api_key_is_stripped_from_child_env(fake_claude, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-leak")
    llm.complete("x", tier="check", call_site="t")
    assert fake_claude()[0]["has_api_key"] is False


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
```

- [ ] **Step 3: Run to verify they fail.**
  Run `uv run pytest tests/unit/test_llm.py -q`. Expected: it fails at collection with
  `ImportError: cannot import name 'llm'`.

- [ ] **Step 4: Implement `src/pipeline/llm.py`.** The api backend is added in Task 2; for now
  the `api` branch raises `LLMError`.

```python
"""One door for every LLM call in the pipeline.

Default backend: headless `claude -p` on Tim's Claude subscription. Opt-in backend:
PIPELINE_LLM_BACKEND=api (Anthropic SDK). There is no silent fallback between them.
Spec: docs/superpowers/specs/2026-09-29-claude-cli-llm-backend-design.md
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pipeline.config import PipelineConfig

Tier = Literal["creative", "check"]
NEUTRAL_SYSTEM = "You are a precise assistant. Follow the user's instructions exactly."
_ISOLATION = ("--tools", "", "--setting-sources", "", "--strict-mcp-config",
              "--no-session-persistence", "--disable-slash-commands")


@dataclass(frozen=True)
class LLMResult:
    text: str
    data: Any | None
    model: str
    backend: str


class LLMError(RuntimeError):
    def __init__(self, call_site: str, reason: str, hint: str = "") -> None:
        self.call_site, self.reason, self.hint = call_site, reason, hint
        super().__init__(str(self))

    def __str__(self) -> str:
        msg = f"{self.call_site}: {self.reason}"
        return f"{msg} — {self.hint}" if self.hint else msg


_SEMS: dict[int, threading.BoundedSemaphore] = {}
_SEMS_LOCK = threading.Lock()


def _semaphore(n: int) -> threading.BoundedSemaphore:
    with _SEMS_LOCK:
        return _SEMS.setdefault(n, threading.BoundedSemaphore(max(1, n)))


def model_for(tier: Tier, config: PipelineConfig | None = None) -> str:
    c = config or PipelineConfig()
    return c.LLM_MODEL_CREATIVE if tier == "creative" else c.LLM_MODEL_CHECK


def resolve_claude_bin(config: PipelineConfig | None = None) -> str | None:
    c = config or PipelineConfig()
    if c.CLAUDE_BIN:
        return c.CLAUDE_BIN if Path(c.CLAUDE_BIN).is_file() else None
    found = shutil.which("claude")
    if found:
        return found
    local = Path.home() / ".local" / "bin" / "claude"
    return str(local) if local.is_file() else None


def complete(content: str | list[dict[str, Any]], *, tier: Tier, call_site: str,
             system: str | None = None, json_schema: dict[str, Any] | None = None,
             max_tokens: int = 4096, timeout: float | None = None) -> LLMResult:
    config = PipelineConfig()
    model = model_for(tier, config)
    blocks = [{"type": "text", "text": content}] if isinstance(content, str) else list(content)
    if config.LLM_BACKEND == "cli":
        return _complete_cli(blocks, model=model, call_site=call_site, system=system,
                             json_schema=json_schema, timeout=timeout or config.LLM_TIMEOUT_SEC,
                             config=config)
    if config.LLM_BACKEND == "api":
        raise LLMError(call_site, "api backend not wired yet")  # Task 2 replaces this line
    raise LLMError(call_site, f"unknown LLM backend {config.LLM_BACKEND!r}",
                   "set PIPELINE_LLM_BACKEND to cli or api")


def _hint(reason: str) -> str:
    low = reason.lower()
    if "login" in low or "auth" in low or "credential" in low:
        return "run `claude login` on this machine"
    if "limit" in low or "quota" in low or "rate" in low or "429" in low:
        return "subscription quota or rate limit reached — wait for the reset or set PIPELINE_LLM_BACKEND=api"
    return ""


def _last_result_event(stdout: str) -> dict[str, Any] | None:
    last = None
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(ev, dict) and ev.get("type") == "result":
            last = ev
    return last


def _complete_cli(blocks: list[dict[str, Any]], *, model: str, call_site: str, system: str | None,
                  json_schema: dict[str, Any] | None, timeout: float,
                  config: PipelineConfig) -> LLMResult:
    binary = resolve_claude_bin(config)
    if binary is None:
        raise LLMError(call_site, "claude CLI not found",
                       "install Claude Code or set PIPELINE_CLAUDE_BIN")
    argv = [binary, "-p", "--input-format", "stream-json", "--output-format", "stream-json",
            "--verbose", "--model", model, "--system-prompt", system or NEUTRAL_SYSTEM, *_ISOLATION]
    if json_schema is not None:
        argv += ["--json-schema", json.dumps(json_schema)]
    stdin = json.dumps({"type": "user", "message": {"role": "user", "content": blocks}}) + "\n"
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    with _semaphore(config.LLM_MAX_CONCURRENCY), tempfile.TemporaryDirectory(prefix="llm-") as cwd:
        try:
            proc = subprocess.run(argv, input=stdin, capture_output=True, text=True,
                                  cwd=cwd, env=env, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise LLMError(call_site, f"claude -p timed out after {timeout:g}s",
                           "retry, or raise PIPELINE_LLM_TIMEOUT_SEC") from exc
    ev = _last_result_event(proc.stdout)
    if proc.returncode != 0 or ev is None or ev.get("is_error"):
        reason = str((ev or {}).get("result") or "").strip() or proc.stderr.strip()[-500:] \
            or f"exit code {proc.returncode}"
        status = (ev or {}).get("api_error_status")
        if status:
            reason = f"{reason} (api status {status})"
        raise LLMError(call_site, f"claude -p failed: {reason}", _hint(reason))
    text = str(ev.get("result") or "")
    data: Any | None = None
    if json_schema is not None:
        data = ev.get("structured_output")
        if data is None:
            try:
                data = json.loads(text)
            except json.JSONDecodeError as exc:
                raise LLMError(call_site, f"claude -p returned no structured output: {text[:200]!r}") from exc
    elif not text.strip():
        raise LLMError(call_site, "claude -p returned an empty result")
    return LLMResult(text=text, data=data, model=model, backend="cli")
```

- [ ] **Step 5: Run the tests.** Run `uv run pytest tests/unit/test_llm.py -q`. Expected: all
  pass. Then run `uv run ruff check src/pipeline/llm.py tests/unit/test_llm.py` and
  `uv run mypy src/pipeline/llm.py`. Expected: clean.

- [ ] **Step 6: Commit.**

```bash
git add src/pipeline/llm.py src/pipeline/config.py tests/unit/test_llm.py
git commit -m "feat(llm): claude -p backend facade on the subscription"
```

---

### Task 2: Opt-in Anthropic API backend

**Files:**
- Modify: `src/pipeline/llm.py` (replace the `api` placeholder; add `_complete_api`)
- Modify: `src/pipeline/utils/anthropic_key.py` (docstring only: now used by `llm` api backend)
- Test: `tests/unit/test_llm.py` (append)

**Interfaces:**
- Consumes: Task 1's `complete`, `LLMResult` and `LLMError`.
- Produces: `PIPELINE_LLM_BACKEND=api` works through the same `complete()` signature.

- [ ] **Step 1: Write the failing tests** (append them to `tests/unit/test_llm.py`):

```python
from unittest.mock import MagicMock, patch


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


def test_api_backend_schema_uses_forced_tool(monkeypatch):
    _api_env(monkeypatch)
    block = MagicMock(type="tool_use", input={"title": "T"})
    with patch("anthropic.Anthropic") as cls:
        cls.return_value.messages.create.return_value = MagicMock(content=[block])
        r = llm.complete("q", tier="check", call_site="t", json_schema={"type": "object"})
    kw = cls.return_value.messages.create.call_args.kwargs
    assert r.data == {"title": "T"} and kw["tool_choice"] == {"type": "tool", "name": "emit"}


def test_api_backend_errors_are_llm_errors(monkeypatch):
    _api_env(monkeypatch)
    with patch("anthropic.Anthropic") as cls:
        cls.return_value.messages.create.side_effect = RuntimeError("credit balance too low")
        with pytest.raises(llm.LLMError, match="credit balance too low"):
            llm.complete("q", tier="check", call_site="t")
```

- [ ] **Step 2: Run to verify they fail.** Run
  `uv run pytest tests/unit/test_llm.py -q -k api`. Expected: FAIL (`api backend not wired yet`).

- [ ] **Step 3: Implement it.** In `complete`, replace the placeholder `raise` with this:

```python
        return _complete_api(blocks, model=model, call_site=call_site, system=system,
                             json_schema=json_schema, max_tokens=max_tokens)
```

Then add this function:

```python
def _complete_api(blocks: list[dict[str, Any]], *, model: str, call_site: str, system: str | None,
                  json_schema: dict[str, Any] | None, max_tokens: int) -> LLMResult:
    import anthropic

    from pipeline.utils.anthropic_key import get_anthropic_api_key

    kwargs: dict[str, Any] = {"model": model, "max_tokens": max_tokens,
                              "messages": [{"role": "user", "content": blocks}]}
    if system:
        kwargs["system"] = system
    if json_schema is not None:
        kwargs["tools"] = [{"name": "emit", "description": "Emit the answer as structured JSON.",
                            "input_schema": json_schema}]
        kwargs["tool_choice"] = {"type": "tool", "name": "emit"}
    try:
        resp = anthropic.Anthropic(api_key=get_anthropic_api_key()).messages.create(**kwargs)
    except Exception as exc:
        raise LLMError(call_site, f"anthropic API call failed: {exc}",
                       "check the API key and credit, or set PIPELINE_LLM_BACKEND=cli") from exc
    if json_schema is not None:
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use":
                return LLMResult(text=json.dumps(block.input), data=block.input, model=model, backend="api")
        raise LLMError(call_site, "anthropic API returned no structured output")
    text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", "text") == "text")
    return LLMResult(text=text, data=None, model=model, backend="api")
```

Update the `anthropic_key.py` module docstring's first paragraph to say: "Used only by the opt-in
`api` backend in `pipeline.llm` (PIPELINE_LLM_BACKEND=api)."

- [ ] **Step 4: Run the tests.** Run `uv run pytest tests/unit/test_llm.py -q`. Expected: all pass.

- [ ] **Step 5: Commit.**

```bash
git add src/pipeline/llm.py src/pipeline/utils/anthropic_key.py tests/unit/test_llm.py
git commit -m "feat(llm): opt-in Anthropic API backend behind the same facade"
```

---

### Task 3: Migrate the creative-tier call sites (Opus)

**Files:**
- Modify:
  - `src/pipeline/stages/analyze.py` (`AnalyzeStage.run`; delete `get_anthropic_client` and `import anthropic`)
  - `src/pipeline/stages/scriptwrite.py` (`_write_narration_for_locale`)
  - `src/pipeline/stages/direct.py` (`generate_shorts_storyboards`, `write_metadata_for_project`, `DirectStage.run`)
  - `src/pipeline/cli_storyboard.py` (`_generate_beats`)
  - `src/pipeline/config.py` (delete `CLAUDE_MODEL`)
- Test:
  - Modify `tests/unit/test_analyze.py`, `tests/unit/test_direct.py`,
    `tests/unit/test_direct_metadata.py` and `tests/unit/test_config.py`.
  - Create `tests/unit/test_llm_call_sites.py`.

**Interfaces:**
- Consumes: `pipeline.llm.complete` and `LLMResult`.
- Pattern at every site: `from pipeline import llm` at module top, then `llm.complete(...)`
  (attribute access, so tests can patch `pipeline.llm.complete`). Async sites use
  `await asyncio.to_thread(llm.complete, ...)`.

- [ ] **Step 1: Rewrite the existing mocks.** In the three test files, replace every
  `patch("pipeline.stages.<mod>.get_anthropic_client")` block with a patch of
  `pipeline.llm.complete` that returns an `LLMResult`. Keep each test's fixture and assertions.
  Example (`tests/unit/test_analyze.py:39-47`):

```python
    from pipeline.llm import LLMResult

    with patch("pipeline.llm.complete",
               return_value=LLMResult(text=json.dumps(analysis_fixture), data=None,
                                      model="m", backend="cli")) as complete:
        ctx = await stage.run(sample_context)
    assert complete.call_args.kwargs["tier"] == "creative"
```

  For `tests/unit/test_direct_metadata.py`, the fake returns
  `LLMResult(text="", data={...the tool input dict the test used...}, model="m", backend="cli")`.
  Then assert `complete.call_args.kwargs["json_schema"] == _METADATA_TOOL["input_schema"]`, where
  `_METADATA_TOOL` is imported from `pipeline.stages.direct`. Also assert
  `complete.call_args.kwargs["system"]` is non-empty.

  In `tests/unit/test_config.py:8`, replace the `CLAUDE_MODEL` assertion with:
  `assert (config.LLM_BACKEND, config.LLM_MODEL_CREATIVE, config.LLM_MODEL_CHECK) == ("cli", "claude-opus-5-5", "claude-haiku-4-5-20251001")`.

- [ ] **Step 2: Add `tests/unit/test_llm_call_sites.py`** with the two creative sites that have
  no existing test:

```python
import json
from unittest.mock import patch

from pipeline.llm import LLMResult


def _res(text="", data=None):
    return LLMResult(text=text, data=data, model="m", backend="cli")


def test_scriptwrite_uses_creative_tier_and_parses_json():
    from pipeline.stages import scriptwrite
    from pipeline.storyboard import Scene

    scenes = [Scene(id="s1", section="hook", narration="n", narration_est_sec=3.0, visual={"type": "text_card"})]
    with patch("pipeline.llm.complete", return_value=_res('```json\n{"s1": "旁白"}\n```')) as c:
        out = scriptwrite._write_narration_for_locale(scenes, "zh-TW")
    assert out == {"s1": "旁白"} and c.call_args.kwargs["tier"] == "creative"


def test_storyboard_beats_use_creative_tier():
    from pipeline import cli_storyboard

    with patch("pipeline.llm.complete", return_value=_res(json.dumps({"s1": "beat"}))) as c:
        out = cli_storyboard._generate_beats([{"id": "s1", "section": "hook", "narration": "n"}])
    assert out == {"s1": "beat"} and c.call_args.kwargs["tier"] == "creative"
```

  (If `Scene`'s required fields differ, build it the way `tests/unit/test_scriptwrite*.py` does.)

- [ ] **Step 3: Run to verify they fail.** Run
  `uv run pytest tests/unit/test_analyze.py tests/unit/test_direct.py tests/unit/test_direct_metadata.py tests/unit/test_config.py tests/unit/test_llm_call_sites.py -q`.
  Expected: FAIL, because the sites still call `get_anthropic_client` and `CLAUDE_MODEL` still
  exists.

- [ ] **Step 4: Migrate the sites.** Keep the prompts and the fence-stripping and JSON parsing
  exactly as they are.
  - **`analyze.py` `run`:** delete `client = get_anthropic_client()` (and `config = ...` if it
    is now unused), then replace the call:

```python
        raw_text = (await asyncio.to_thread(
            llm.complete, prompt, tier="creative", call_site="analyze", max_tokens=4096)).text
```

    Delete `get_anthropic_client()` and `import anthropic` from `analyze.py`. Add
    `import asyncio` and `from pipeline import llm`.
  - **`scriptwrite.py` `_write_narration_for_locale`:**
    `raw = llm.complete(prompt, tier="creative", call_site="scriptwrite", max_tokens=16000).text`
    Drop the `get_anthropic_client` import.
  - **`direct.py` `generate_shorts_storyboards`:**
    `raw_text = (await asyncio.to_thread(llm.complete, prompt, tier="creative", call_site="direct.shorts", max_tokens=8192)).text`
  - **`direct.py` `DirectStage.run`:**
    `raw_text = (await asyncio.to_thread(llm.complete, prompt, tier="creative", call_site="direct", max_tokens=16000)).text`
  - **`direct.py` `write_metadata_for_project`:** replace the `messages.create` call and the
    `tool_use` loop with:

```python
    result = llm.complete(user, tier="creative", call_site="direct.metadata", system=system,
                          json_schema=_METADATA_TOOL["input_schema"], max_tokens=2048)
    if not isinstance(result.data, dict):
        raise RuntimeError("metadata: model returned no structured metadata")
    tool_input: dict = dict(result.data)
```

  - **`cli_storyboard.py` `_generate_beats`:**
    `raw = llm.complete(prompt, tier="creative", call_site="storyboard.beats", max_tokens=4096).text`
    Drop the `get_anthropic_client` import and the unused `config`.
  - **`config.py`:** delete `CLAUDE_MODEL`. Then `grep -rn "CLAUDE_MODEL\|get_anthropic_client" src tests`
    must return nothing.

- [ ] **Step 5: Run the tests.** Run the Step 3 command, then `uv run pytest -q`,
  `uv run ruff check src/ tests/` and `uv run mypy src/`. Expected: all pass and clean.

- [ ] **Step 6: Commit.**

```bash
git add src/pipeline/stages/analyze.py src/pipeline/stages/scriptwrite.py src/pipeline/stages/direct.py \
        src/pipeline/cli_storyboard.py src/pipeline/config.py tests/unit/test_analyze.py \
        tests/unit/test_direct.py tests/unit/test_direct_metadata.py tests/unit/test_config.py \
        tests/unit/test_llm_call_sites.py
git commit -m "refactor(llm): creative stages call llm.complete (Opus via claude -p)"
```

---

### Task 4: Migrate the check-tier call sites (Haiku, including the three image sites)

**Files:**
- Modify:
  - `src/pipeline/cli_proofread.py` (`proofread_storyboard`)
  - `src/pipeline/cli_storyteller.py` (`storytell_storyboard`)
  - `src/pipeline/cli_mla.py` (`call_haiku_rewrite`)
  - `src/pipeline/cli_visual_review.py` (`review_visual_fit`)
  - `src/pipeline/cli_image_alignment.py` (`check_alignment`)
  - `src/pipeline/composer/style_anchor.py` (`_assess_source`; delete `_HAIKU_MODEL`)
- Test: `tests/unit/test_llm_call_sites.py` (append)

**Interfaces:**
- Consumes: `pipeline.llm.complete`.

- [ ] **Step 0: Fix the fused decorator line in `cli_visual_review.py`.** The EM found this during
  Sprint 10 grounding. Line ~321 reads `    c.print(table)@visual_review_app.command("extract-frames")`.
  Python parses it as `None @ decorator`, which has two effects:
  - `print_visual_issues_table` raises `TypeError` right after printing, so produce's QC always
    ends in "(visual review skipped)";
  - `extract-frames` is never registered.

  **First, the failing tests** (append to `tests/unit/test_llm_call_sites.py`):

```python
def test_visual_review_extract_frames_is_registered():
    from typer.testing import CliRunner

    from pipeline.cli_visual_review import visual_review_app

    res = CliRunner().invoke(visual_review_app, ["extract-frames", "--help"])
    assert res.exit_code == 0, res.output


def test_print_visual_issues_table_does_not_raise():
    from pipeline.cli_visual_review import print_visual_issues_table

    print_visual_issues_table([{"scene_id": "s1", "severity": "MINOR", "observation": "o",
                                "suggestion": "s", "reason": "r"}])
```

  Run them and see both FAIL. Then split the line into `    c.print(table)`, a blank line, and
  `@visual_review_app.command("extract-frames")` at column 0. See both PASS, then commit:
  `fix(visual-review): unfuse print from the extract-frames decorator`. If
  `print_visual_issues_table` takes different arguments, adapt the call to its real signature.

- [ ] **Step 1: Write the failing tests** (append):

```python
def _png(path):
    from PIL import Image
    Image.new("RGB", (16, 16), (200, 30, 30)).save(path)
    return path


def test_proofread_uses_check_tier_with_its_system_prompt(tmp_path):
    from pipeline import cli_proofread

    sb = tmp_path / "storyboard.json"
    sb.write_text(json.dumps({"scenes": [{"id": "s1", "section": "hook", "narration": "你好",
                                          "narration_est_sec": 2.0, "visual": {"type": "text_card"}}]}),
                  encoding="utf-8")
    with patch("pipeline.llm.complete", return_value=_res("OK")) as c:
        assert cli_proofread.proofread_storyboard(sb) == []
    kw = c.call_args.kwargs
    assert kw["tier"] == "check" and kw["system"].startswith(cli_proofread._SYSTEM_PROMPT)


def test_style_anchor_sends_one_image_then_text(tmp_path):
    from pipeline.composer import style_anchor

    frame = _png(tmp_path / "f.jpg")
    with patch("pipeline.llm.complete", return_value=_res("high\nflat ink, warm palette")) as c:
        assert style_anchor._assess_source(frame) == ("high", "flat ink, warm palette")
    blocks = c.call_args.args[0]
    assert [b["type"] for b in blocks] == ["image", "text"] and c.call_args.kwargs["tier"] == "check"


def test_style_anchor_stays_advisory_on_llm_error(tmp_path):
    from pipeline.composer import style_anchor
    from pipeline.llm import LLMError

    with patch("pipeline.llm.complete", side_effect=LLMError("style_anchor", "quota")):
        assert style_anchor._assess_source(_png(tmp_path / "f.jpg")) == ("medium", "")
```

  Also add one test each for `storytell_storyboard`, `call_haiku_rewrite`, `check_alignment` and
  `review_visual_fit`, in the same shape:
  - patch `pipeline.llm.complete` with `_res("OK")`, or with a canned `ISSUE|…` line in the
    module's own format;
  - call the function with the smallest fixture its existing tests use. Reuse fixtures from
    `tests/unit/test_cli_*` where they exist. For the two image functions, give it one real
    tiny PNG, and pre-create `compose/scenes/_review_frames/s1.png` so `review_visual_fit` skips
    extraction;
  - assert `tier == "check"`. For the image functions, also assert that at least one
    `{"type": "image"}` block reached `complete`.

- [ ] **Step 2: Run to verify they fail.** Run
  `uv run pytest tests/unit/test_llm_call_sites.py -q`. Expected: the new tests FAIL, because the
  sites still construct `anthropic.Anthropic`.

- [ ] **Step 3: Migrate the sites.** Delete `import anthropic` and the `get_anthropic_api_key`
  import from each module, and add `from pipeline import llm`.
  - **proofread:** `raw = llm.complete(review_text, tier="check", call_site="proofread", system=system, max_tokens=2000).text.strip()`
  - **storyteller:** `raw = llm.complete(review_text, tier="check", call_site="storyteller", system=_SYSTEM_PROMPT, max_tokens=2000).text.strip()`
    (the `hasattr(block, "text")` dance goes away).
  - **mla:** `raw = llm.complete(user_prompt, tier="check", call_site="mla.rewrite", system=_REBALANCE_SYSTEM_PROMPT, max_tokens=2000).text.strip()`
    `api_key` is no longer used. Remove the parameter, update every caller
    (`grep -rn "call_haiku_rewrite" src tests`), and update the docstring to "Ask the check-tier
    model…".
  - **visual review:** `raw = llm.complete(content, tier="check", call_site="visual_review", system=_REVIEW_SYSTEM_PROMPT, max_tokens=2000).text.strip()`
  - **image alignment:** `raw = llm.complete(_build_review_content(items), tier="check", call_site="image_alignment", system=_SYSTEM_PROMPT, max_tokens=2000).text.strip()`
  - **style anchor:** inside the existing `try`, which stays advisory, build the same two
    blocks and call:

```python
        text = llm.complete(
            [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
             {"type": "text", "text": _ASSESS_PROMPT}],
            tier="check", call_site="style_anchor", max_tokens=200,
        ).text
        lines = text.strip().splitlines()
```

    Here `_ASSESS_PROMPT` is the existing two-line instruction string, moved into a module
    constant verbatim. Delete `_HAIKU_MODEL`.

- [ ] **Step 4: Run the tests.** Run `uv run pytest tests/unit/test_llm_call_sites.py -q`, then
  `uv run pytest -q`, `uv run ruff check src/ tests/` and `uv run mypy src/`. Expected: all pass
  and clean.

- [ ] **Step 5: Commit.**

```bash
git add src/pipeline/cli_proofread.py src/pipeline/cli_storyteller.py src/pipeline/cli_mla.py \
        src/pipeline/cli_visual_review.py src/pipeline/cli_image_alignment.py \
        src/pipeline/composer/style_anchor.py tests/unit/test_llm_call_sites.py
git add -u tests   # only if Step 3's mla caller update touched other test files; review `git diff --cached` first
git commit -m "refactor(llm): check-tier sites call llm.complete (Haiku via claude -p)"
```

---

### Task 5: Guard, doctor, integration test and docs

**Files:**
- Test:
  - `tests/unit/test_llm_guard.py` (create)
  - `tests/integration/test_llm_cli.py` (create)
  - `tests/unit/test_cli_doctor.py` (modify `_all_pass`)
- Modify:
  - `src/pipeline/cli_doctor.py` (`check_llm` + `run_checks`)
  - `README.md` (budget table + an "LLM backend" config block)
  - `CLAUDE.md` (budget table rows only)

**Interfaces:**
- Consumes: `pipeline.llm.resolve_claude_bin`, `PipelineConfig`.

- [ ] **Step 1: Write the failing tests.**

  `tests/unit/test_llm_guard.py`:

```python
import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "pipeline"
ALLOWED = {SRC / "llm.py"}


def test_only_the_llm_module_talks_to_anthropic():
    bad = []
    for py in sorted(SRC.rglob("*.py")):
        if py in ALLOWED:
            continue
        text = py.read_text(encoding="utf-8")
        if re.search(r"^\s*(import anthropic|from anthropic)", text, re.M) or "messages.create" in text:
            bad.append(str(py.relative_to(SRC)))
    assert bad == []
```

  Doctor tests: append these to `tests/unit/test_cli_doctor.py`, and in `_all_pass` add
  `monkeypatch.setattr(cli_doctor, "check_llm", lambda: [CheckResult("llm", True, "ok")])`.

```python
def test_check_llm_passes_with_a_binary(monkeypatch, tmp_path):
    exe = tmp_path / "claude"
    exe.write_text("#!/bin/sh\necho '9.9.9 (Claude Code)'\n")
    exe.chmod(0o755)
    monkeypatch.setenv("PIPELINE_LLM_BACKEND", "cli")
    monkeypatch.setenv("PIPELINE_CLAUDE_BIN", str(exe))
    (r,) = cli_doctor.check_llm()
    assert r.ok and "9.9.9" in r.detail and "claude-opus-5-5" in r.detail


def test_check_llm_fails_without_a_binary(monkeypatch, tmp_path):
    monkeypatch.setenv("PIPELINE_LLM_BACKEND", "cli")
    monkeypatch.setenv("PIPELINE_CLAUDE_BIN", str(tmp_path / "missing"))
    (r,) = cli_doctor.check_llm()
    assert not r.ok and "PIPELINE_CLAUDE_BIN" in r.detail
```

  `tests/integration/test_llm_cli.py`:

```python
import base64
import io

import pytest
from PIL import Image

from pipeline import llm

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(llm.resolve_claude_bin() is None, reason="claude CLI not installed")]


def test_real_text_call():
    assert "ok" in llm.complete("Reply with exactly: ok", tier="check", call_site="it.text").text.lower()


def test_real_image_call():
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (220, 30, 30)).save(buf, "PNG")
    blocks = [{"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                           "data": base64.b64encode(buf.getvalue()).decode()}},
              {"type": "text", "text": "What colour is this image? One word."}]
    assert "red" in llm.complete(blocks, tier="check", call_site="it.image").text.lower()


def test_real_schema_call():
    r = llm.complete("Name one primary colour.", tier="check", call_site="it.schema",
                     json_schema={"type": "object", "properties": {"colour": {"type": "string"}},
                                  "required": ["colour"]})
    assert isinstance(r.data, dict) and r.data.get("colour")
```

- [ ] **Step 2: Run to verify they fail.** Run
  `uv run pytest tests/unit/test_llm_guard.py tests/unit/test_cli_doctor.py -q`. Expected: the
  doctor tests FAIL because `check_llm` is missing. The guard should already PASS after Tasks
  3–4; if it lists files, migrate them.

- [ ] **Step 3: Implement `check_llm`** in `src/pipeline/cli_doctor.py`, and register
  `("llm", check_llm)` in `run_checks` after `("toon", check_toon)`:

```python
def check_llm() -> list[CheckResult]:
    from pipeline.config import PipelineConfig
    from pipeline.llm import resolve_claude_bin

    c = PipelineConfig()
    models = f"creative={c.LLM_MODEL_CREATIVE} check={c.LLM_MODEL_CHECK}"
    if c.LLM_BACKEND == "api":
        return [CheckResult("llm", True, f"backend api (Anthropic SDK); {models}")]
    binary = resolve_claude_bin(c)
    if binary is None:
        return [CheckResult("llm", False, "backend cli but the claude CLI was not found — "
                                          "install Claude Code or set PIPELINE_CLAUDE_BIN")]
    try:
        version = subprocess.run([binary, "--version"], capture_output=True, text=True,
                                 timeout=30).stdout.strip()
    except Exception as exc:
        return [CheckResult("llm", False, f"{binary} --version failed: {exc!r}")]
    return [CheckResult("llm", True, f"backend cli; {binary} ({version}); {models}")]
```

  (`subprocess` is already imported in `cli_doctor.py`. If not, import it.)

- [ ] **Step 4: Update the docs.**
  - **README.md:** in the budget table, replace the "Claude Sonnet API" row with
    `| Claude (Opus creative / Haiku checks) via claude -p | $0 marginal | Tim's Claude subscription quota |`.
    In the configuration section, add an "LLM backend" block listing the `PIPELINE_LLM_*` and
    `PIPELINE_CLAUDE_BIN` settings from the spec §2 table, with one line on `claude login` per
    machine.
  - **CLAUDE.md:** make the same budget-row change in "Budget Allocation", and rebalance the
    Buffer row's figure so the table still sums to $50.

- [ ] **Step 5: Run the tests.** Run `uv run pytest -q`, `uv run ruff check src/ tests/`,
  `uv run mypy src/`, `uv run pipeline doctor` (the `llm` line must PASS on the Mac) and
  `uv run pytest -q --integration tests/integration/test_llm_cli.py` (3 passed; this spends a
  trivial amount of Haiku quota). Expected: all green.

- [ ] **Step 6: Commit.**

```bash
git add tests/unit/test_llm_guard.py tests/integration/test_llm_cli.py tests/unit/test_cli_doctor.py \
        src/pipeline/cli_doctor.py README.md CLAUDE.md
git commit -m "feat(llm): doctor check, guard + integration tests, subscription budget docs"
```

---

### Task 6 (controller, after merge and push): hub verification

The controller runs this on the hub. No subagent is involved. Nothing real is mutated.

- [ ] **Step 1:** Run
  `ssh hub 'bash -lc "cd ~/content-creation && git pull --ff-only && uv sync && uv run pipeline doctor | grep llm"'`.
  Expected: `PASS llm: backend cli; …`.
- [ ] **Step 2:** On the hub, run `uv run pytest -q --integration tests/integration/test_llm_cli.py`.
  Expected: 3 passed.
- [ ] **Step 3:** Run three real calls against a **copy**. Copy an existing project's
  `storyboard.json` and one rendered frame into `tmp/claude-cli-backend/sandbox/`, then run
  `uv run python -c` snippets that call:
  - `proofread_storyboard(copy)` (check tier);
  - `_generate_beats(scenes)` (creative tier, Opus);
  - `style_anchor._assess_source(frame)` (image).

  Save their outputs and timings to `tmp/claude-cli-backend/evidence.md`. Expected: each returns
  a real answer and no `LLMError`.
- [ ] **Step 4:** Dispatch the separate code review, then the EM in REVIEW mode for this
  infrastructure item (spec §6).
