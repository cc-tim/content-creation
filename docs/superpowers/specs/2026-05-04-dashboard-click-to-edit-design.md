---
title: Dashboard Click-to-Edit (Design)
date: 2026-05-04
status: design
related:
  - 2026-05-03-dashboard-click-to-edit-intent.md
  - 2026-05-03-wiki-explainer-to-video-bridge-design.md
  - 2026-04-25-scene-panel-design.md
  - 2026-04-23-dashboard-design.md
---

# Dashboard Click-to-Edit — Design

Resolves the requirements brief at
`docs/superpowers/specs/2026-05-03-dashboard-click-to-edit-intent.md`.

The brainstorm walked through the brief's 8 design categories and folded in
three additional requirements raised during that session:

- **Extra A** — Page-turn transition primitive (new compose work)
- **Extra B** — Per-scene transition toggle UI (verifier/dashboard)
- **Extra C** — Per-scene narration audio recorder for TTS substitution

## Goals

1. Click any rendered element on the per-project dashboard view (scene
   image, subtitle line, overlay text, narration panel, transition seam,
   final-video player at time T) to mint a stable addressable token
   (`@s9/visual`, `@s9/subtitle`, `@s9/overlay`, `@s9/narration`,
   `@s9/transition`).
2. Submit `tokens + natural-language instruction` to an LLM agent that
   plans and executes the edit using the existing compose/proofread CLI
   verbs.
3. Provide direct-action UI (no LLM round-trip) for bounded-input edits:
   transition style/duration/sfx, narration source switching, browser-side
   audio recording.
4. Stream progress, deliver previews, and accept retries/confirmations
   through the existing Telegram bot — no in-browser chat infrastructure.
5. Auto-refresh the dashboard view of a project's artifacts when an edit
   lands, via SSE.

## Non-goals

- Multi-user collaboration on the same project.
- Sandboxed agent execution (project-id-scoped CLI verbs are sufficient).
- Auto-resume of jobs after dashboard server crash (mark interrupted →
  manual retry).
- A second chat UI in the browser. Telegram is the conversation surface.
- v1 ships a single page-turn renderer technique (xfade `slideleft`); the
  abstraction allows swapping to a PNG/webm overlay later.

## Architecture

Three subsystems, all running inside the existing dashboard process:

1. **Dashboard frontend** (static HTML/JS in `src/pipeline/dashboard/static/`)
   - Edit-mode toggle in header (off by default; preserves all current
     behavior when off)
   - Floating composer (sticky bottom bar, visible only in edit mode):
     token chips + textarea + cost-aware confirm popup
   - Direct-action UIs: transition modal, narration-source modal with
     MediaRecorder
   - SSE client for artifact-refresh + in-flight badge updates
   - Token ↔ element cross-highlighting

2. **Dashboard backend** (`src/pipeline/dashboard/server.py` + new modules)
   - FastAPI as today
   - `JobQueue` — in-process asyncio queue, **per project**, FIFO, single
     consumer coroutine per project. Other projects run in parallel.
   - SSE emitter — per-project channel for `files_changed` and
     `job_status` events
   - Telegram long-poll listener — handles inbound `callback_query`
     (button taps for retry / confirm / cancel / revert)
   - Direct-action HTTP endpoints — call the same CLI verbs the agent
     calls; single source of truth for mutations

3. **Agent runtime** (subprocess, started by `JobQueue`)
   - `asyncio.create_subprocess_exec("claude", "-p", ...)` per job
   - Streaming stdout pumped to Telegram via message-edit calls
   - System prompt lives at `src/pipeline/dashboard/agent_prompt.md`
     so it can be tweaked without code changes; loaded at JobQueue
     startup, supplemented per-job with the project id, current
     storyboard summary, and the resolved token list
   - On dashboard-process exit: in-flight job records marked
     `interrupted` on next startup; not auto-resumed

```
┌──────────────────────────────────────────────────────────────────────┐
│ Browser (dashboard)                                                  │
│  - edit-mode toggle, composer, modals, SSE client                    │
│  - direct-action UI: transition / narration-source / recorder        │
└──────────────────────────────────────────────────────────────────────┘
        │ HTTP (POST mutations + GET artifacts)        ▲ SSE
        ▼                                              │
┌──────────────────────────────────────────────────────────────────────┐
│ Dashboard backend (FastAPI, single process)                          │
│  ┌─────────────────┐  ┌──────────────────┐  ┌──────────────────────┐ │
│  │ Direct-action   │  │ JobQueue         │  │ SSE emitter           │ │
│  │ endpoints       │  │ (asyncio,        │  │ (per-project channel) │ │
│  │ (transition,    │  │  per-project)    │  │                       │ │
│  │  narration src, │  │                  │  │                       │ │
│  │  recorder)      │  └────────┬─────────┘  └──────────────────────┘ │
│  └────────┬────────┘           │                                     │
│           │  ┌─────────────────▼─────────────────┐                   │
│           │  │ Agent subprocess (`claude -p ...`)│                   │
│           │  │  → calls project-scoped CLI verbs │                   │
│           │  │  → streams progress to Telegram   │                   │
│           │  └─────────────────┬─────────────────┘                   │
│           │                    │                                     │
│           ▼                    ▼                                     │
│  ┌──────────────────────────────────────────────────────────────────┐│
│  │ Project tree mutations: storyboard.json, narration_overrides/,   ││
│  │ compose/, session_log entries                                    ││
│  └──────────────────────────────────────────────────────────────────┘│
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │ Telegram long-poll listener (getUpdates)                        │ │
│  │  → routes callback_query (button taps) back into JobQueue       │ │
│  └─────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
        │ outbound: sendMessage / editMessage / sendVideo / sendPhoto
        ▼
                            ┌─────────────┐
                            │  Telegram    │
                            │  (existing   │
                            │   bot/chat)  │
                            └─────────────┘
```

## Token grammar

A token is the addressable handle a click produces and the agent reads.

| Form | Meaning |
|---|---|
| `@sN` | Whole scene N — agent inspects all elements (narration, subtitle, overlay, visual) and proposes a coherent change to whichever subset matches the instruction. |
| `@sN/visual` | Scene N's image / clip |
| `@sN/subtitle` | Scene N's subtitle line |
| `@sN/overlay` | Scene N's overlay text |
| `@sN/narration` | Scene N's narration text (and the audio that derives from it) |
| `@sN/transition` | The seam between scene N and scene N+1 (canonical seam-out form; the seam-in chip on scene N+1 mints the same token) |
| `@manifest:<item_id>` | A manifest constraint from the verifier view (e.g. `@manifest:verbatim_3`) — agent can target the storyboard scenes that should satisfy this constraint |

`N` is a scene id like `s9`, matching the existing storyboard convention.
Tokens are case-sensitive. Whitespace separates tokens in the composer.

## Data model additions

### Storyboard schema (`output/projects/<id>/storyboard.json`)

Both new fields are optional and sparse — existing storyboards work
unchanged.

```jsonc
{
  "scenes": [
    {
      "id": "s9",
      "narration": "...",
      "subtitle":  "...",
      "narration_source": {                         // NEW — only when overridden
        "engine": "prerecorded",                    // | "edge-tts" | "fish-audio"
        "voice":  null,                             // for tts engines
        "file":   "narration_overrides/s9.wav"     // for prerecorded
      }
      // ... existing scene fields unchanged
    }
  ],
  "transitions": [                                  // NEW — sparse; missing = hard cut
    {
      "from":         "s9",
      "to":           "s10",
      "style":        "page-turn",                  // | "fade" | "slide" | "wipe" | "none"
      "duration_sec": 0.5,
      "sfx":          "assets/sfx/page_flip.mp3"   // optional; null = silent
    }
  ]
}
```

### Per-project sidecar files

| File | Purpose |
|---|---|
| `output/projects/<id>/edit_draft.json` | Single in-progress composer draft (tokens + textarea text). Restored on re-entering edit mode. Cleared on submit. |
| `output/projects/<id>/edit_jobs/<job_id>.json` | One file per submitted job. Records: tokens, instruction text, status (`queued`/`running`/`done`/`failed`/`interrupted`/`cancelled`), Telegram message_id, sub-action results. |
| `output/projects/<id>/narration_overrides/<scene_id>.wav` | User-recorded audio for a scene's narration. Single file per scene; re-record overwrites. |
| `output/projects/<id>/session_log.jsonl` | Existing log; extended with `revert_payload` for each mutation so the per-project last-10 revert affordance can roll back. |

### Asset shipping

| Path | Purpose |
|---|---|
| `assets/sfx/` | Built-in transition sound effects (initial set: `page_flip.mp3`, `whoosh.mp3`, `swoosh.mp3`); user-uploaded sfx land here too. |
| `assets/transitions/<style>/` | Reserved for future PNG/webm overlay assets when we swap the renderer technique. v1 ships empty. |

## User flows

### Flow 1 — Edit-mode + composer (chat-driven edit)

1. User opens a project view, taps **Edit Mode** in header. Header badge
   turns active color; sticky strip at viewport bottom reads *"Edit
   mode — tap any scene element to add a token (Esc to exit)"*. Floating
   composer slides up from bottom.
2. User taps a scene image → token `@s9/visual` minted into composer.
   Element gets a persistent border to show it's "selected." User taps a
   subtitle line on a different scene → `@s11/subtitle` added.
3. User types in textarea: *"make these darker and tighten the subtitle"*.
4. User taps **Submit**.
   - If the job involves real cost (image regen) or wide rebuild
     (>50% of scenes), a confirm popup shows resolved tokens, instruction,
     estimated cost, and side-by-side "before" preview thumbnails. User
     taps Confirm.
   - If neither cost nor wide-rebuild: silent submit, no popup.
5. Backend writes `edit_jobs/<id>.json`, queues onto the project's
   asyncio JobQueue, returns immediately. Composer empties; edit mode
   auto-exits; project card gets a **🔄 editing** in-flight badge via SSE.
6. JobQueue's per-project consumer picks up the job:
   - Sends the opener message to Telegram with `[proj-id] editing
     @s9/visual + @s11/subtitle: "make these…"`. Stores the returned
     `message_id` in the job record.
   - Spawns `claude -p` subprocess with the system prompt + verb list.
7. Agent plans sub-actions, calls CLI verbs serially. Each sub-action's
   stdout streams to Telegram as a reply to the opener message
   (`reply_to_message_id`).
8. As mutations land in `storyboard.json` and `compose/`, the SSE
   emitter notifies the open dashboard tab; tab refetches changed
   artifacts and updates in place.
9. Per Cat 5 failure policy: each sub-action commits if it succeeds;
   per-token retry buttons appear on Telegram for failed sub-actions;
   substantive interpretive choices escalate as inline-button confirm
   prompts ("image safety filter rejected — rephrase as A or B?").
10. Per Cat 8 trust policy: tier-based.
    - Auto-apply tier (text-only single-scene edits, char delta < 80%):
      change lands immediately, Telegram posts result with `↩ Revert`.
    - Propose-then-apply tier (image regen, multi-scene compositional,
      agent-driven transition or narration_source): agent posts proposal
      with `✅ Apply / ✏ Edit / ❌ Cancel` inline buttons; mutation only
      lands after Apply.
11. Final completion message includes a preview attachment (rendered
    scene clip MP4 / new image as photo / inline diff for text). In-flight
    badge clears. Job record marked `done`.

### Flow 2 — Direct-action transition toggle

1. In edit mode, user taps the transition chip on a scene panel
   (e.g. `Transition out → s10: page-turn 0.5s 🔊`). This is direct-action,
   not a chat token.
2. Quick-toggle: tapping the chip itself flips the transition on/off
   using the project's last-saved config or default.
   - Tapping the chip's `⚙` opens the modal editor: style dropdown,
     duration numeric, sfx dropdown (sourced from `assets/sfx/` plus
     `+ upload custom`).
3. **Apply** in the modal POSTs to a direct-action endpoint. Backend:
   - Writes/updates the `transitions` array entry
   - Calls `pipeline transition set ...` CLI verb
   - Recompose touches only the two transition clips on either side of
     the seam (cheap)
   - SSE refreshes the dashboard view; the chip in BOTH adjacent scene
     panels updates (mirrored read of the same seam config)

### Flow 3 — Direct-action narration source + recorder

1. In edit mode, user taps `Source: edge-tts ▾` chip on a scene's
   narration panel. Modal opens.
2. Modal contents:
   - Read-only display of the scene's narration text
   - Source radio list: Edge-TTS (default voice) / Fish Audio (each
     registered voice) / 🎙 Prerecorded (this session) / + Upload audio file
   - Recorder section: REC / STOP / Play, with timer
   - `☑ Auto-transcribe and update subtitle` checkbox (default checked)
3. User taps **REC**, browser MediaRecorder API requests mic permission,
   captures audio. Tap **STOP**. Audio plays back in browser via the
   modal's `<audio>` element.
4. User taps **Apply to s9**. Frontend:
   - Multipart-uploads the webm/opus blob to backend endpoint
   - Backend ffmpeg-normalizes to wav at standard sample rate, writes to
     `output/projects/<id>/narration_overrides/s9.wav`
   - If auto-transcribe is checked: backend invokes Whisper API on the
     wav, returns transcript; modal shows a diff of generated text vs
     transcript and asks user to **Apply Transcript** or **Keep Original**.
   - On final apply: writes `narration_source` field on scene s9, calls
     `pipeline narration set-source` CLI verb, single-scene reburn for s9.
5. SSE refreshes dashboard. Chip on the scene panel updates to
   `Source: 🎙 recording`.

### Flow 4 — Cancel / revert

- **Cancel** an in-flight job:
  - From dashboard: tap the ✕ on the project card's in-flight badge
  - From Telegram: tap the **Cancel** inline button on the job's opener message
  - Either path: backend `proc.terminate()` on the agent subprocess; job
    record marked `cancelled`; final status posted to Telegram thread.
- **Revert** a completed mutation:
  - Tap the `↩ Revert` inline button on a Telegram result message
    (or on a session-log entry in the dashboard view)
  - Backend reads the `revert_payload` from the session log entry,
    enqueues an internal "revert job" through the per-project JobQueue
    (so it serializes cleanly), executes the inverse mutation, recomposes
    the affected scope, posts result.
  - Available for the last 10 mutations per project. Older entries
    drop the inline button but remain in the log.

## Component design

### Frontend — edit mode + composer

`src/pipeline/dashboard/static/index.html` adds:

- **Header bar**: edit-mode toggle button. State: off (default) / on.
  Persists in `localStorage` per project so refreshing in mid-session
  doesn't drop you out of edit mode (but auto-exit on submit still wins).
- **Sticky bottom strip** (visible when edit mode on): mode label + Esc
  hint. Replaced by the floating composer when there are tokens.
- **Floating composer** (component): token-chip list with `✕` per chip,
  textarea, live-summary line (`N tokens · M scenes · est. $X`),
  Esc/Submit buttons. Mobile-collapsed to a single bar with `(N) ▲`
  badge until tapped.
- **Cross-highlighting**: hovering a chip fires `border-flash` on the
  matched DOM element by data-attribute lookup
  (`[data-element-id="@s9/visual"]`).
- **Confirm popup** (component): shows resolved token labels, instruction,
  cost estimate (computed locally from token types + a small client-side
  cost map keyed by edit verb), before-thumbnails grid. Cancel / Confirm.
  - The local cost estimate is best-effort. The agent may expand scope
    mid-job (e.g. interpret a narration rewrite as also requiring image
    re-generation for visual coherence). Such expansions are caught by
    the Cat 8 trust gate: any image-regen / multi-scene / agent-driven
    transition or narration_source mutation is propose-then-apply,
    surfaced in Telegram before money is spent.
- **In-flight badge** (component): rendered on each project card and on
  the project view header. Updated by SSE.
- **Direct-action modals**: `TransitionEditor`, `NarrationSourceEditor`
  (the latter wraps the MediaRecorder API and the Whisper-transcript diff
  preview).

`src/pipeline/dashboard/static/verify.html` mirrors the same edit-mode
toggle and floating composer (the verifier view also wants click-to-edit
on its scene rail and final-video player).

### Frontend — clickable elements registry

To make any element clickable in edit mode without sprinkling
`onclick` handlers everywhere, each clickable region carries
`data-edit-token="@s9/visual"` (or whatever its token is). A single
top-level click handler reads the attribute and routes to either:

- Native behavior (edit mode off): handled by existing handlers as today
- Mint-token (edit mode on): append to composer, suppress native action

For the final-video player tap-time → scene resolution: read scene
`start_sec` array from storyboard at page load, binary-search the tap
timestamp.

### Backend — JobQueue

```python
# src/pipeline/dashboard/job_queue.py (new)
class EditJob(BaseModel):
    job_id: str
    project_id: str
    tokens: list[str]
    instruction: str
    status: Literal["queued", "running", "done", "failed", "interrupted", "cancelled"]
    telegram_opener_id: int | None
    sub_action_results: list[SubActionResult]
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

class JobQueue:
    def __init__(self):
        self._queues: dict[str, asyncio.Queue[EditJob]] = {}
        self._consumers: dict[str, asyncio.Task] = {}
        self._running: dict[str, EditJob] = {}        # one per project
        self._procs:   dict[str, asyncio.subprocess.Process] = {}

    async def submit(self, job: EditJob) -> None: ...
    async def cancel(self, project_id: str, job_id: str) -> bool: ...
    async def _consume_loop(self, project_id: str) -> None: ...
    async def _run_job(self, job: EditJob) -> None: ...     # spawns claude -p
    async def reload_on_startup(self) -> None: ...           # marks any "running" in edit_jobs/ as "interrupted"
```

### Backend — Telegram listener

Extend `src/pipeline/notify/telegram.py` (currently outbound-only):

- Add `reply_to_message_id` and `reply_markup` (inline keyboard) parameters
  to existing send helpers
- Add `send_video(chat_id, video_path, caption, ...)` and
  `send_photo(chat_id, photo_path, caption, ...)`
- Add `edit_message_text(chat_id, message_id, ...)` for streaming
  progress updates
- Add a new long-poll loop (`run_long_poll_listener`) — polls
  `getUpdates` with offset, dispatches incoming `callback_query` events
  to a registered handler (the JobQueue's button-callback router)
- Started as a background asyncio task by FastAPI's `lifespan` handler

### Backend — direct-action endpoints

```
POST /api/transition/<project_id>/set       body: {from, to, style, duration_sec, sfx}
POST /api/transition/<project_id>/clear     body: {from, to}
POST /api/narration/<project_id>/set-source body: {scene, engine, voice?, file?}
POST /api/narration/<project_id>/upload     multipart file → returns saved path
POST /api/narration/<project_id>/transcribe body: {scene, file} → returns transcript
POST /api/jobs/<project_id>/submit          body: {tokens, instruction}
POST /api/jobs/<project_id>/<job_id>/cancel
POST /api/jobs/<project_id>/<mutation_id>/revert
GET  /api/sse/<project_id>                  SSE channel: files_changed / job_status events
```

All mutating endpoints internally invoke the same project-scoped CLI
verbs the agent uses, ensuring single source of truth.

## CLI verb surface

| Verb | Used by | Purpose |
|---|---|---|
| `pipeline transition set --project-id X --from sN --to sM --style ... --duration ... --sfx ...` | Both | Write/update transition entry; recompose adjacent transition clips + master concat |
| `pipeline transition clear --project-id X --from sN --to sM` | Both | Remove transition entry (= hard cut); recompose master concat |
| `pipeline narration set-source --project-id X --scene sN --engine prerecorded --file ...` | Both | Write per-scene `narration_source`; reburn that scene |
| `pipeline narration regen --project-id X --scene sN --text "..."` | Agent only | Update storyboard `narration` text + re-TTS that scene |
| `pipeline subtitle set --project-id X --scene sN --text "..."` | Agent only | Update subtitle, kick subtitle reburn |
| `pipeline overlay set --project-id X --scene sN --text "..."` | Agent only | Update overlay, kick overlay reburn |
| `pipeline image regen --project-id X --scene sN --prompt "..." --tier draft\|production` | Agent only | Regenerate scene image, recompose scene |

All verbs require `--project-id` and refuse paths outside that project's
tree (defensive sandbox per Cat 2).

## Compose pipeline change (Extra A — page-turn primitive)

New module `src/pipeline/composer/transitions.py`:

```python
class TransitionConfig(BaseModel):
    style: Literal["none", "fade", "page-turn", "slide", "wipe"]
    duration_sec: float
    sfx: str | None              # path under assets/sfx/ or absolute project path

class TransitionRenderer(Protocol):
    def render(self, scene_a: Path, scene_b: Path, cfg: TransitionConfig, out: Path) -> Path: ...

class HardCutRenderer:    # emits no clip; master concat skips
    ...
class XfadeRenderer:      # uses ffmpeg xfade with a chosen built-in transition
    def __init__(self, transition: str): ...
class OverlayRenderer:    # future: alpha-mask a PNG/webm sequence over scene seam + sfx mix
    def __init__(self, asset_dir: Path): ...

REGISTRY: dict[str, TransitionRenderer] = {
    "none":      HardCutRenderer(),
    "fade":      XfadeRenderer(transition="fade"),
    "page-turn": XfadeRenderer(transition="slideleft"),  # v1 cheapest approximation
    "slide":     XfadeRenderer(transition="slideleft"),
    "wipe":      XfadeRenderer(transition="wiperight"),
}
```

`src/pipeline/composer/base.py` is extended so the compose stage:

1. Reads `storyboard["transitions"]` (sparse; default empty).
2. For each entry, computes a cache key
   `sha1(style, duration_sec, sfx, last_frame_hash(scene_a), first_frame_hash(scene_b))`
   and either renders (cache miss) or reuses (cache hit) at
   `compose/transitions/<hash>.mp4`.
3. Builds master concat in order
   `scene_1, transition_1to2?, scene_2, transition_2to3?, ...`,
   skipping any seam whose entry is `none` / missing.
4. Per-scene reburn invalidates only the transitions touching that scene
   (the seams on either side), not the whole video.

**Future swap**: replacing the `page-turn` registry entry with
`OverlayRenderer(asset_dir=Path("assets/transitions/page_turn"))` is a
one-line change. The asset folder ships a `sequence.webm` (alpha) and a
`meta.json` (duration, aspect, direction). No storyboard/UI/agent change.

## Failure handling & policies

- **Commit-as-you-go** (Cat 5 β): each sub-action commits its mutation
  on success. Per-token failures surface in Telegram as inline
  `↻ Retry` buttons; agent has a small judgment budget for trivial
  in-line fixes (auto-recovered) and escalates substantive interpretive
  choices via Telegram inline-button prompts.
- **Compose-pending notice**: if a job mutates storyboard but a
  recompose sub-action fails, the final Telegram message is explicit
  *"compose pending — render the new state with `reburn`?"* with a
  one-tap button.
- **Concurrency** (Cat 6): per-project FIFO queue. Submit-while-busy is
  allowed; UI shows the new submission as `waiting in queue`. Different
  projects run in parallel. One submission may carry many tokens — that's
  one job, not N.
- **Crash recovery**: in-flight job records on disk from a prior crash
  are marked `interrupted` on next dashboard startup; not auto-resumed.
  User decides whether to retry from Telegram (the original opener
  message has a `↻ Retry` button after interruption).
- **Trust gate** (Cat 8): tier-based.
  - Auto-apply tier with revert: text-only, single-scene, char delta < 80%
  - Propose-then-apply tier: image regen, multi-scene, agent-driven
    transition or narration_source mutations
  - Universal preview attachment in every Telegram result message
    (rendered scene clip / new image / inline diff)
- **Revert**: backed by `session_log.jsonl` entries with embedded
  `revert_payload`; available for last 10 mutations per project; goes
  through the per-project queue.

## File structure changes

New files:

```
src/pipeline/dashboard/
  job_queue.py                    # asyncio per-project queue
  sse_emitter.py                  # per-project SSE channels
  agent_prompt.md                 # system prompt for the edit agent
  static/
    edit_mode.js                  # toggle, composer, cross-highlighting
    transition_editor.js          # direct-action modal
    narration_source_editor.js    # direct-action modal + MediaRecorder

src/pipeline/composer/
  transitions.py                  # TransitionRenderer + REGISTRY

src/pipeline/cli_transition.py    # CLI: pipeline transition set / clear
src/pipeline/cli_narration.py     # CLI: pipeline narration set-source / regen

assets/sfx/                       # initial set: page_flip.mp3, whoosh.mp3, swoosh.mp3
assets/transitions/               # reserved for future overlay assets (empty in v1)
```

Modified:

```
src/pipeline/dashboard/server.py          # +endpoints, +SSE, +Telegram listener wiring
src/pipeline/dashboard/static/index.html  # +edit-mode UI, composer
src/pipeline/dashboard/static/verify.html # mirror edit-mode UI
src/pipeline/notify/telegram.py           # +reply_to/inline_keyboard/photo/video/edit/long-poll
src/pipeline/composer/base.py             # +transitions array handling in master concat
src/pipeline/storyboard.py                # +TransitionConfig, NarrationSource pydantic models
src/pipeline/session_log.py               # +revert_payload field on log entries
src/pipeline/cli.py                       # register cli_transition, cli_narration
```

## Open questions / future work

1. **Page-turn renderer swap**: after using `slideleft` in v1, decide
   whether to ship a true page-curl PNG/webm asset and swap to
   `OverlayRenderer`. One-line registry change; no other code touched.
2. **Clip-swap UI step**: the agent identifies candidate source clips
   from the cached pool but the final selection (which clip + in/out
   points) needs a small modal, deferred to v1.1.
3. **Transitions overview panel**: an explicit row visualizing all seams
   across the video (s1→s2, s2→s3, …) for at-a-glance rhythm. Useful but
   not v1 — per-scene mirrored chips suffice.
4. **Multi-user**: out of scope. If ever needed: per-user Telegram chat
   ids + per-project ownership; today's design is single-user.

## Test plan (high level)

- `test_job_queue.py`: per-project FIFO, parallel across projects, cancel,
  crash-recovery marking, callback routing
- `test_telegram_long_poll.py`: callback dispatch, offset tracking, retry
  on transient API failure
- `test_transitions.py`: schema parse, renderer dispatch, cache key
  determinism, per-seam reburn scope
- `test_narration_source.py`: per-scene engine dispatch, prerecorded path
  resolution, fallback to project default
- `test_direct_action_endpoints.py`: each POST mutates storyboard
  correctly, refuses paths outside project tree
- Integration: round-trip a full edit job (subtitle rewrite) end-to-end
  in a fixture project; assert storyboard mutated, session_log entry
  written, Telegram messages mocked

## Implementation order (for the next plan)

This spec is intended to be decomposed into a written plan in a separate
session via the `superpowers:writing-plans` skill. Suggested phasing:

1. **Compose layer first** — `transitions.py`, schema additions,
   `cli_transition`. Independently useful: gives you transitions without
   any UI yet.
2. **Direct-action narration recorder** — `cli_narration set-source`,
   modal in dashboard, MediaRecorder + Whisper transcribe. Useful in
   isolation for replacing TTS with your own voice.
3. **JobQueue + Telegram long-poll + agent runtime** — backend plumbing
   for chat-driven edits.
4. **Edit-mode UI + composer + click-to-mint** — frontend.
5. **Trust gate, revert, SSE refresh** — polish layer.

Each phase ends with a usable subset; later phases stack on top.
