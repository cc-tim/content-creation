# Claude CLI LLM backend: run pipeline LLM calls on the subscription

**Status:** approved in chat by Tim, 2026-09-29, pending review of this written spec. The EM is
placing it in `docs/ROADMAP.md` (infrastructure).
**Why:** the Anthropic API credit is exhausted (`400 credit balance too low`, found by the toon
compose smoke on 2026-09-28). Every Claude-backed stage fails today: analyze, scriptwrite,
direct, metadata, proofread, visual QC and the others.
**Tim:** "replace with main agent or subagent ability or "claude -p" to do, we have extra quota
in subscription". Model pick: "Creative on Opus, checks on Haiku".

## 1. Goal and success

Every pipeline LLM call runs on Tim's Claude subscription through headless `claude -p`. Success
means all of the following:

- All 12 call sites (§4) work through the CLI on the Mac and on the hub, including runs under
  systemd (the dashboard) whose `PATH` is minimal.
- No Anthropic API key is needed.
- Outputs parse exactly as they do today.
- Failures are loud: the real CLI or quota message reaches the user, and there is no silent
  fallback.
- Creative stages use Opus; checkers use Haiku.

**Non-goals:**
- An "agent answers the prompt" mode, where the main agent or a subagent fills a prompt file.
  `claude -p` already covers unattended runs; revisit if ever needed.
- Changing prompts. The one exception is the forced-tool pattern (§4), which becomes a JSON
  schema.
- Changing any call site's fatal-vs-advisory behaviour.

## 2. Architecture

```
call sites (12) ──► pipeline.llm.complete(...) ──► backend
                                                  ├─ ClaudeCliBackend  (default)  → `claude -p …`
                                                  └─ AnthropicApiBackend (opt-in) → anthropic SDK
```

| Unit | Responsibility |
|---|---|
| `src/pipeline/llm.py` | The facade. `complete(prompt, *, system=None, tier, images=(), json_schema=None, max_tokens=None, timeout=None) -> LLMResult`. It resolves the tier to a model, selects the backend, and raises `LLMError`. |
| `LLMResult` | A frozen dataclass: `text: str`, `data: Any \| None` (parsed when `json_schema` is given), `model: str`, `backend: str`. |
| `LLMError(RuntimeError)` | Fields `call_site`, `reason`, `hint`. `__str__` includes the reason and the hint. |
| `ClaudeCliBackend` | Builds the argv and stdin, runs the subprocess, and parses the JSON envelope. Owns binary resolution, isolation, timeout and a concurrency cap. |
| `AnthropicApiBackend` | Today's SDK call moved behind the interface. It is the only user of `utils/anthropic_key.py`, and the `anthropic` import is lazy. |

**Config** (`src/pipeline/config.py`, env overridable):

| Setting | Default | Meaning |
|---|---|---|
| `LLM_BACKEND` (`PIPELINE_LLM_BACKEND`) | `cli` | `cli` or `api` |
| `LLM_MODEL_CREATIVE` | `claude-opus-5-5` | analyze, scriptwrite, direct (storyboard, shorts, metadata), storyboard beats |
| `LLM_MODEL_CHECK` | `claude-haiku-4-5-20251001` | proofread, visual QC, image alignment, storyteller, MLA rewrite, style anchor |
| `CLAUDE_BIN` (`PIPELINE_CLAUDE_BIN`) | unset, so resolve | Path to the `claude` binary |
| `LLM_TIMEOUT_SEC` | `600` | Per-call subprocess timeout |
| `LLM_MAX_CONCURRENCY` | `4` | Maximum concurrent `claude -p` processes |

`CLAUDE_MODEL` (today `claude-sonnet-4-20250514`) is replaced by the two tier settings, and its
readers migrate. `style_anchor._HAIKU_MODEL` goes away.

## 3. The CLI backend

**Invocation** (argv as a list, never a shell string):

```
claude -p --output-format json --model <model>
       --system-prompt <system>                      # replaces Claude Code's default agent prompt
       --tools ""                                    # no tools: a pure completion
       --setting-sources "" --strict-mcp-config      # no user/project settings, hooks, MCP
       --no-session-persistence --disable-slash-commands
       [--json-schema <schema json>]                 # structured output
       [--input-format stream-json]                  # only when images are attached
```

- **System prompt:** it is always passed. When a call site has no `system`, the backend passes
  a neutral one-line prompt, `You are a precise assistant. Follow the user's instructions
  exactly.`, so Claude Code's default coding-agent prompt never applies.
- **Flags:** the implementer verifies every flag above against the installed CLI (2.1.283 on
  both machines) before relying on it, including the exact envelope field that carries
  `--json-schema` output. If a flag is missing or behaves differently, stop and report; don't
  improvise.
- **Isolation:** the working directory is a fresh temporary directory, so no repo `CLAUDE.md`
  is loaded. The environment passes through, and the CLI uses its own subscription login. An
  `ANTHROPIC_API_KEY` in the environment would switch the CLI to API billing, so the backend
  **removes** `ANTHROPIC_API_KEY` from the child's environment.
- **Text prompts:** the prompt is written to stdin as plain text.
- **Images:** with `--input-format stream-json`, stdin carries one user message whose content
  blocks match the SDK's today: `{"type":"image","source":{"type":"base64",…}}` blocks followed
  by the text block. Base64 encoding happens in the facade, which accepts `Path` or `bytes`.
- **Output:** the stdout JSON envelope is parsed.
  - `is_error: true`, a non-zero exit code, an empty `result`, or a timeout each raise
    `LLMError`. Its `reason` quotes the CLI message or the stderr tail; quota, rate-limit and
    login messages appear verbatim. Its `hint` names the fix: `claude login` on that machine, or
    wait for the quota to reset.
  - With `--json-schema`, `data` is taken from the envelope's structured output. If it is
    missing, `json.loads(result)` is tried. If both fail, `LLMError` is raised.
- **Binary resolution:** `CLAUDE_BIN`, else `shutil.which("claude")`, else `~/.local/bin/claude`,
  else `LLMError("claude CLI not found", hint="install Claude Code or set PIPELINE_CLAUDE_BIN")`.
- **Concurrency:** a process-wide semaphore of size `LLM_MAX_CONCURRENCY`. Async call sites use
  a thread offload (`asyncio.to_thread`), so the event loop never blocks on the subprocess.
- **`max_tokens`:** not passed to the CLI, which has no such flag. It is kept in the signature
  for the API backend.
- **Fallback:** there is none. If the CLI fails, the call fails. `PIPELINE_LLM_BACKEND=api` is
  an explicit operator choice.

## 4. Call-site migration

| # | File : function | Tier | Images | Output handling |
|---|---|---|---|---|
| 1 | `stages/analyze.py : AnalyzeStage.run` | creative | — | existing JSON extraction on `.text` |
| 2 | `stages/scriptwrite.py : _write_narration_for_locale` | creative | — | existing JSON extraction |
| 3 | `stages/direct.py : DirectStage.run` | creative | — | existing JSON extraction |
| 4 | `stages/direct.py : generate_shorts_storyboards` | creative | — | existing JSON extraction |
| 5 | `stages/direct.py : write_metadata_for_project` | creative | — | **forced tool `_METADATA_TOOL` → `json_schema`** (the tool's `input_schema`); read `.data` |
| 6 | `cli_storyboard.py : _generate_beats` | creative | — | existing JSON extraction |
| 7 | `cli_proofread.py : proofread_storyboard` | check | — | existing |
| 8 | `cli_storyteller.py : storytell_storyboard` | check | — | existing |
| 9 | `cli_visual_review.py : review_visual_fit` | check | yes | existing |
| 10 | `cli_image_alignment.py : check_alignment` | check | yes | existing |
| 11 | `cli_mla.py : call_haiku_rewrite` | check | — | existing |
| 12 | `composer/style_anchor.py : _assess_source` | check | yes | existing |

- Each site keeps its own prompt text, its own parsing, and its current behaviour on failure.
  An advisory site catches `LLMError` where it caught SDK errors before, and prints the reason.
- The post-compose visual QC in `produce` stays advisory, and now runs on the subscription.
- The `anthropic` dependency stays in `pyproject.toml` for the `api` backend.

## 5. Testing

- **Unit tests for the facade and backend** (`tests/unit/test_llm.py`) use a fake `claude`
  executable, a small script selected through `PIPELINE_CLAUDE_BIN`, that records its argv,
  stdin, cwd and env, then prints a canned envelope. They assert:
  - tier → model;
  - every isolation flag is present;
  - `--json-schema` is passed through;
  - image calls use `--input-format stream-json` with correct image blocks;
  - `ANTHROPIC_API_KEY` is stripped from the child env;
  - the cwd is a temp dir, not the repo;
  - the envelope is parsed;
  - each failure (`is_error`, non-zero exit, timeout, empty result, missing binary, bad JSON
    with a schema) raises `LLMError` with the reason quoted;
  - the concurrency cap holds.
- **API backend:** one test with a mocked SDK client shows the same interface.
- **Call sites:** the existing tests switch from mocking `anthropic` to mocking
  `pipeline.llm.complete`. They also assert each site's tier, and that site 5 sends the metadata
  schema.
- **Guard:** outside `llm.py` and the API backend, no module under `src/pipeline` imports
  `anthropic` or calls `messages.create`. This is enforced by a source-scan test.
- **Integration** (`--integration`; skips when `claude` isn't installed): one real Haiku text
  call and one real Haiku call with a tiny image, each asserting a non-empty answer. This spends
  a trivial amount of quota.
- **Doctor:** `check_llm` reports the backend and the resolved `claude` binary with its
  `--version`. It FAILs if `cli` is selected and no binary is found. It never makes a model call.

## 6. Done criteria

1. All tests in §5 pass on the Mac. The suite, ruff and mypy are clean.
2. On the hub, `uv run pipeline doctor` shows the `llm` check passing, and the integration test
   passes.
3. On the hub, at least three sites make a real call under the backend:
   - a proofread run on an existing storyboard (check tier);
   - one creative-tier call, such as `storyboard` beats or metadata generation on an existing
     project, without publishing;
   - one image call, either `visual-review` or `image-alignment`.

   Evidence is saved to `tmp/claude-cli-backend/`.
4. The budget tables in README and CLAUDE.md show Claude calls as the subscription (via
   `claude -p`) rather than "Claude Sonnet API ~$10". README documents the env settings.
5. A separate code review has happened, then the EM runs REVIEW.
