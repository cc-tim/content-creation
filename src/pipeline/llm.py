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

# Every one of these would move billing or routing off the subscription and onto a
# different, possibly-metered path if it leaked into the `claude -p` child process:
#   ANTHROPIC_API_KEY        - switches the CLI to pay-per-token API billing
#   ANTHROPIC_AUTH_TOKEN     - alternate API bearer token, same billing effect as the key above
#   ANTHROPIC_BASE_URL       - redirects the CLI to a different (possibly billed) endpoint
#   CLAUDE_CODE_USE_BEDROCK  - routes calls through AWS Bedrock billing instead
#   CLAUDE_CODE_USE_VERTEX   - routes calls through GCP Vertex AI billing instead
# CLAUDE_CODE_OAUTH_TOKEN is deliberately excluded: it *is* the subscription login on
# headless hosts and must reach the child process for `claude -p` to work at all.
_STRIP_ENV = frozenset({
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
})


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
        return _complete_api(blocks, model=model, call_site=call_site, system=system,
                             json_schema=json_schema, max_tokens=max_tokens)
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
    env = {k: v for k, v in os.environ.items() if k not in _STRIP_ENV}
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
