---
date: 2026-04-23
topic: YouTube auto-upload pipeline (publish stage) with multi-channel support
status: draft
---

# YouTube publish pipeline

## Problem

The production pipeline ends at `compose`, producing `final.mp4` on disk. Today, uploading that video to YouTube is a fully manual process: signing into the right channel, filling in title/description/tags, uploading the thumbnail, checking the AI-content disclosure box, setting privacy, optionally scheduling. This friction scales poorly as the number of channels grows.

Specific pains:

1. **No automation for the mechanical steps.** Title/description/tags generation, thumbnail upload, metadata fields, disclosure checkbox — all clickwork after the creative work is already done.
2. **Multi-account switching is ad-hoc.** The operator runs multiple niche channels (parenting in zh-TW, tech in en, more to come). Each upload requires signing out and signing in, or using separate browser profiles.
3. **No reviewable output before YouTube touches the file.** The operator wants to eyeball the thumbnail in a real YouTube context (grid, recommended sidebar) before committing it to the channel — but not to the point of building a custom preview UI right now.
4. **No integration with the pipeline's notion of "project."** Each project directory already has `final.mp4`, a storyboard, a knowledge file — the publish step should read these as inputs and write the resulting `youtube_video_id` back, same pattern as the rest of the pipeline.

## Goals

- Automate the upload + metadata + thumbnail + disclosure sequence so a single command publishes a produced project.
- Support multiple channels via per-profile OAuth. Adding a new channel is a config-file change + one-time auth run, no code changes.
- Route projects to channels automatically via `(niche, locale) → profile` mapping, with explicit override.
- Treat YouTube Studio as the preview surface for day 1 (upload as unlisted; operator reviews thumbnail/metadata in Studio before flipping public).
- Idempotent, resumable, quota-aware — partial failures (video uploaded but thumbnail failed) resume cleanly on rerun.
- Failure notifications via an existing Telegram bot.

## Non-goals

- **Custom local preview web app.** Deferred. YouTube Studio is the preview for day 1.
- **AI-generated thumbnails.** Deferred. Operator hand-designs each thumbnail and drops it at a known path.
- **Bypass of human review.** No `--and-publish` flag on `produce`; every upload is an explicit second step after the operator has watched the final video.
- **Multi-audio-track uploads.** The pipeline produces one locale per project run; single-language uploads only.
- **Batch / queued scheduling.** One project per publish invocation.
- **Publish-success notifications.** Only failures page out for now.
- **Retargeting an already-uploaded video to a different channel.** YouTube doesn't support it anyway (videos belong to the channel they were uploaded to); a rerun with `--profile` on an already-uploaded project is an error.

## Scope

1. New submodule `src/pipeline/publish/` with OAuth, channel routing, YouTube API client, publish stage.
2. Config file `configs/youtube_channels.toml` (version-controlled; holds channel metadata + voice guides, no secrets).
3. Per-profile OAuth token files at `~/.config/content-creation/youtube/<profile>.json` (mode 0600, never committed).
4. New field on `PipelineContext`: `niche: str | None`. New flags: `thumbnail_uploaded: bool`, `disclosure_set: bool`.
5. `DirectStage` extended to emit `metadata.json` alongside the storyboard, using the resolved channel's voice guide.
6. New Typer sub-app `pipeline publish` (upload, auth, accounts, status).
7. New Typer sub-app `pipeline metadata` (show, set, regenerate, validate) — mirrors existing `storyboard` helper pattern.
8. New module `src/pipeline/notify/telegram.py` for failure notifications. Scoped to publish for now; easy to reuse elsewhere.
9. `produce` command gains optional `--niche NAME` flag, auto-detected from the routing table when omitted. `--niche none` explicitly skips metadata generation.
10. Tests: unit tests mocking the YouTube client at the SDK seam; optional integration tests behind `network` marker using a sandbox channel.

## Architecture

```
existing pipeline (unchanged):
  acquire → analyze → direct → tts → compose
                        │
                        └── emits storyboard.json + script.txt
new:                    └── ALSO emits metadata.json

new standalone stage (NOT in orchestrator auto-chain):
  publish    ← invoked explicitly via `pipeline publish <project-id>`
```

**Architectural principles:**

- **Metadata is generated at produce time, not publish time.** Same rationale as storyboards — the creative context (hook, theme, source) is freshest in `DirectStage`, and the operator should be able to review/edit drafts before triggering upload. `metadata.json` is a reviewable artifact in the project directory.
- **Publish stays out of the auto-chain.** The orchestrator never runs publish automatically. A produced project sits on disk until the operator runs `pipeline publish <project-id>`. This is the human review gate, not a missing feature.
- **Channel is bound at produce time.** `--niche` on produce picks a profile via `(niche, locale)` lookup, auto-detected from the routing table when the flag is omitted (see §1 "Auto-detection"); the profile's voice guide shapes metadata generation. At publish time, `--profile` can override for last-minute rerouting (rare).
- **Per-profile OAuth.** Each channel has its own refresh token. One shared Google Cloud OAuth client (`client_secret.json`) is reused across profiles — profiles differ only in which Google account consented.
- **Idempotent by persistence.** Context fields (`youtube_video_id`, `thumbnail_uploaded`, `disclosure_set`) record how far the upload got. Rerun skips completed phases. No in-process retry loops — partial state + rerun is the pattern.

### Directory layout

```
src/pipeline/
  publish/
    __init__.py
    auth.py           # OAuth flow, token load/save/refresh, per-profile storage
    channels.py       # Config loader; profile resolution from (niche, locale) or override
    client.py         # Thin YouTube Data API wrapper (videos.insert, thumbnails.set, videos.update, channels.list)
    stage.py          # PublishStage implementing PipelineStage
    metadata.py       # Pydantic Metadata model; read/write/validate helpers
    cli.py            # `pipeline publish` Typer sub-app
  notify/
    __init__.py
    telegram.py       # Failure notifier (used by publish stage; easy to reuse)
  stages/
    direct.py         # EXTENDED: also writes metadata.json using channel voice guide
  cli_metadata.py     # `pipeline metadata` Typer sub-app (mirrors cli_storyboard.py)
configs/
  youtube_channels.toml   # Channel profiles + (niche, locale) → profile routing
tests/
  unit/publish/
  integration/publish/    # marker: network
  fixtures/
    sample_final.mp4      # 10s, 1280x720
    sample_thumbnail.png  # 1280x720, <500KB
    sample_metadata.json
```

## 1. Channel profile config

File: `configs/youtube_channels.toml` (version-controlled).

```toml
[profiles.ideal-parents-tw]
niche      = "parenting"
locale     = "zh-TW"
channel_id = "UCxxxxxxxxxxxxxxxxxxxx"   # fill in after first auth
voice_guide = """
Warm, reassuring parental tone. Avoid clickbait.
Lead with empathy. Title pattern: scenario + outcome
("孩子半夜哭鬧?三個步驟幫他冷靜下來").
Always end description with: "資料來源:..." + AI-disclosure notice.
"""
default_tags = ["育兒", "親子", "幼兒教育"]
category_id  = 27    # Education

[profiles.tech-bummer-en]
niche      = "tech"
locale     = "en"
channel_id = "UCyyyyyyyyyyyyyyyyyyyy"
voice_guide = """
Punchy, curious, slightly irreverent. OK to use "this is wild" energy.
Title pattern: hook + specificity ("I tried X for 30 days and...").
End description with source credits + AI-generated-narration disclosure.
"""
default_tags = ["tech", "AI", "productivity"]
category_id  = 28    # Science & Technology

[routing]
"parenting/zh-TW" = "ideal-parents-tw"
"tech/en"         = "tech-bummer-en"
```

**Contents are non-secret** — channel IDs, voice guides, category IDs. Safe to version-control.

**Profile resolution priority** (in `channels.py`):

1. `--profile NAME` explicit flag → use it.
2. `(ctx.niche, ctx.locale)` looked up in `[routing]` → use mapped profile.
3. No match → hard error: `No channel configured for (niche, locale). Add entry to configs/youtube_channels.toml or pass --profile.`

**Niche auto-detection** (in `channels.py`, called by `produce` before DirectStage runs):

Invoked when `--niche` is omitted on produce. Deterministic, no API cost.

1. Collect all routing keys `"*/<ctx.locale>"`. Extract the niche side of each.
2. **Exactly one niche** for this locale → return it. Log: `niche auto-detected from routing: <niche>`.
3. **Zero niches** for this locale → error: `No channel configured for locale=<X>. Add a [routing] entry in configs/youtube_channels.toml or pass --niche NAME / --niche none.`
4. **Multiple niches** for this locale → error: `Ambiguous: locale=<X> maps to niches: <list>. Specify --niche NAME.`

Explicit `--niche NAME` always wins and skips auto-detection entirely (including `--niche none`, which skips metadata generation).

## 2. OAuth and token management

**Google Cloud prerequisites** (one-time operator setup, documented in spec; not blocking for development):

1. Create a GCP project (or reuse existing).
2. Enable `YouTube Data API v3`.
3. Create OAuth 2.0 Client ID → **Desktop app** type.
4. Download JSON → save to `~/.config/content-creation/youtube/client_secret.json` (mode 0600).
5. Add each channel's Google account as a test user on the OAuth consent screen (required while the app is in "Testing" status; avoids the 7-day refresh-token expiry).

**Token storage:**

```
~/.config/content-creation/youtube/
  client_secret.json              # shared across profiles, mode 0600
  ideal-parents-tw.json           # per-profile token, mode 0600
  tech-bummer-en.json
```

Token JSON stores: `refresh_token`, `access_token`, `expiry`, `scopes`, `channel_id` (captured at auth time for verification).

**OAuth flow (`pipeline publish auth --profile NAME`):**

1. Read `profiles.NAME` from config; error cleanly if missing (show template to copy-paste).
2. Use `google-auth-oauthlib` `InstalledAppFlow.from_client_secrets_file(...)` with scopes:
   - `https://www.googleapis.com/auth/youtube.upload`
   - `https://www.googleapis.com/auth/youtube.readonly`
3. `flow.run_local_server(port=0)` opens browser → loopback redirect → no manual paste.
4. On success, verify the authenticated account owns the configured `channel_id`:
   - Call `channels.list(mine=true)`.
   - Compare returned `id` against `profiles.NAME.channel_id`.
   - If mismatch: abort, do NOT write token, tell operator which Google account was used vs. which channel was expected.
   - If config's `channel_id` is still the placeholder `"UCxxx..."`: write the discovered `channel_id` to config (interactive `add` command handles this; direct `auth` just warns).
5. Write token JSON to `~/.config/content-creation/youtube/<profile>.json`, mode 0600.

**`--reauth`**: force re-running the consent flow (token was revoked, or scopes expanded). Deletes existing token file before running flow.

**Token refresh** is automatic inside the YouTube client wrapper — the `google-auth` library handles refresh via the stored refresh token. If refresh fails (revoked / stale / 6-month inactivity expiry): hard error pointing at `pipeline publish auth --profile NAME --reauth`.

## 3. Metadata generation (in `DirectStage`)

**Output artifact:** `<project-dir>/metadata.json`.

```json
{
  "title": "孩子半夜哭鬧?三個步驟幫他冷靜下來",
  "description": "詳細的描述...\n\n資料來源:<source_url>\n\n本影片旁白由 AI 合成。",
  "tags": ["育兒", "親子", "寶寶", "哭鬧", "安撫技巧"],
  "category_id": 27,
  "default_language": "zh-TW",
  "default_audio_language": "zh-TW",
  "made_for_kids": false,
  "altered_or_synthetic_content": "synthetic_voice",
  "_generated_at": "2026-04-23T14:00:00+08:00",
  "_source_url": "...",
  "_profile": "ideal-parents-tw"
}
```

Underscore-prefixed fields are *about* the metadata (trace, provenance) — not uploaded to YouTube.

**`altered_or_synthetic_content` values:**

- `"synthetic_voice"` — AI narration (default for edge-tts / Google TTS / OpenAI TTS).
- `"altered"` — heavily edited source (reserved; not currently auto-set).
- `"none"` — no disclosure needed (rare; requires explicit hand-edit).

**Pydantic model** (`publish/metadata.py`):

```python
class Metadata(BaseModel):
    title: str = Field(max_length=100)
    description: str = Field(max_length=5000)
    tags: list[str]
    category_id: int
    default_language: str
    default_audio_language: str
    made_for_kids: bool = False
    altered_or_synthetic_content: Literal["synthetic_voice", "altered", "none"] = "synthetic_voice"

    @field_validator("tags")
    @classmethod
    def tags_total_length(cls, v: list[str]) -> list[str]:
        # YouTube counts separators: sum of tag chars + (N-1) commas, or 0 when empty.
        total = sum(len(t) for t in v) + max(len(v) - 1, 0)
        if total > 500:
            raise ValueError(f"tags total length {total} exceeds YouTube limit of 500")
        return v
```

**Generation in `DirectStage`** (new step after storyboard is written):

1. Resolve profile via `channels.resolve(niche=ctx.niche, locale=ctx.locale)`. If no match and `ctx.niche == "none"`: skip metadata generation; emit no file.
2. Build Claude prompt:
   - **System:** profile's `voice_guide` + hard constraints (title ≤ 100 chars, description ≤ 5000, tags total ≤ 500, output as JSON).
   - **User:** scene-by-scene synopsis from storyboard + source URL + relevant KG facts (for credit-worthy claims).
3. Claude call uses the `claude-api` skill conventions (prompt caching on the system prompt since voice guides don't change often). Structured JSON output via tool use (the SDK's `input_schema` tool pattern — not `response_format`, which is OpenAI-only).
4. Merge with defaults from config: `default_tags` prepended to model's tags (deduped); `category_id` filled if model omitted.
5. Append standardized footer to description:
   - Source credit line: `資料來源:<source_url>` or `Source:<source_url>` (locale-selected).
   - AI disclosure line: `本影片旁白由 AI 合成。` or `This video uses AI-generated narration.` (locale-selected).
6. Validate against `Metadata` Pydantic model. Fail loudly on constraint violations (don't silently truncate).
7. Write to `<project-dir>/metadata.json`. **Never overwrite if file exists** — preserves operator's hand-edits on re-runs. Use `pipeline metadata regenerate` to force.

**Claude API call:** uses Sonnet (consistent with other creative stages). Cost is modest (~2k input + ~1k output tokens per call) — well within the $10/mo Claude budget.

## 4. Metadata editor CLI

Mirrors the existing `storyboard` helper pattern (`src/pipeline/cli_storyboard.py`). New file: `src/pipeline/cli_metadata.py`.

```
pipeline metadata show [--project-id X]
  # Pretty-prints current metadata.json. Defaults to latest project if --project-id omitted.

pipeline metadata set <field>=<value> [--project-id X]
  # Edits one field. Examples:
  #   pipeline metadata set title="新標題"
  #   pipeline metadata set tags='["新標籤","更多"]'   # JSON-encoded for lists
  # Safe fields only: title, description, tags, category_id, made_for_kids,
  # altered_or_synthetic_content. Unsafe fields (e.g., _generated_at) rejected.

pipeline metadata regenerate [--project-id X]
  # Re-runs Claude generation (clobbers hand edits). Confirms before overwriting.

pipeline metadata validate [--project-id X]
  # Validates against Pydantic + YouTube limits. Useful before publish.
```

**Natural-language triggers** (for the assistant, following `CLAUDE.md` convention):

```
"change project X's title to Y"    → pipeline metadata set title=Y --project-id X
"show me project X's metadata"      → pipeline metadata show --project-id X
"regenerate metadata for X"         → pipeline metadata regenerate --project-id X
```

## 5. Publish stage internals

**Entry point:** `pipeline publish <project-id> [options]`.

### Preflight (no API calls)

1. `work_dir = OUTPUT_DIR / "projects" / <project-id>` exists.
2. `context.json` exists, `final_video_path` set and file exists, video ≤ 128GB (YouTube hard limit; we'll also warn at 10GB for sanity).
3. `metadata.json` exists and passes Pydantic validation.
4. `thumbnail.png` exists, ≤ 2MB, dimensions ≥ 640×360 (YouTube minimum; recommend 1280×720).
5. Profile resolved (`--profile` or `(ctx.niche, ctx.locale)` lookup); token file exists at expected path.
6. If `--schedule ISO8601`: parses, is in future, and `--privacy` is not `public` (YouTube requires `privacyStatus=private` for scheduled publish).

Every preflight failure prints the exact remediation command.

### Upload sequence

All three phases are idempotent. Context is saved after each phase so partial state survives crashes.

```
# Phase A — video upload (1600 quota units)
if ctx.youtube_video_id is None:
    body = {
        "snippet": {
            "title": metadata.title,
            "description": metadata.description,
            "tags": metadata.tags,
            "categoryId": str(metadata.category_id),
            "defaultLanguage": metadata.default_language,
            "defaultAudioLanguage": metadata.default_audio_language,
        },
        "status": {
            "privacyStatus": effective_privacy,       # "unlisted" default
            "publishAt": schedule_iso if schedule else None,
            "selfDeclaredMadeForKids": metadata.made_for_kids,
        },
    }
    video_id = client.videos_insert(
        body=body,
        media_body=MediaFileUpload(ctx.final_video_path, chunksize=-1, resumable=True),
    )
    ctx.youtube_video_id = video_id
    ctx.save()

# Phase B — thumbnail (50 quota units)
if not ctx.thumbnail_uploaded:
    client.thumbnails_set(
        video_id=ctx.youtube_video_id,
        media_body=MediaFileUpload(thumbnail_path),
    )
    ctx.thumbnail_uploaded = True
    ctx.save()

# Phase C — synthetic-content disclosure (50 quota units)
if not ctx.disclosure_set:
    client.videos_update(
        video_id=ctx.youtube_video_id,
        part="contentDetails",
        body={"contentDetails": {
            "contentRating": {},
            "hasCustomThumbnail": True,
            # altered/synthetic flag set via the "selfDeclaredMadeForKids"-style API field
            # See YouTube API 2026 addition for exact field path
        }},
    )
    ctx.disclosure_set = True
    ctx.save()
```

> Note: YouTube's synthetic-content disclosure API field name and exact path should be confirmed against the live API docs during implementation — the 2026 policy may use `alteredContent` or a similar field under `status` or `contentDetails`. Implementation verifies via Context7 / live docs, not assumption.

**On success:**

- Log to structlog: `publish.success { project_id, video_id, profile, privacy, scheduled_at }`.
- Print Studio URL: `https://studio.youtube.com/video/<video_id>/edit`.
- Print watch URL: `https://youtu.be/<video_id>` (even when unlisted — operator uses it to share).
- Update project DB row (if DB is active): `stage=published`, `youtube_video_id=<id>`, `published_at=<now>`.
- Exit 0.

### Flags

```
--profile NAME              override channel selection
--privacy unlisted|private|public     default: unlisted
--schedule ISO8601          upload private with publishAt; conflicts with --privacy=public
--dry-run                   run preflight + print upload body JSON, no API calls
--force-metadata            re-run videos.update on already-uploaded video (title/desc/tags change)
--force-thumbnail           re-upload thumbnail on already-uploaded video
```

`--force-metadata` and `--force-thumbnail` target the already-uploaded `youtube_video_id` — they do NOT re-upload video.

### Quota budget

Per full publish: **1700 units** (1600 insert + 50 thumbnail + 50 update). Daily per-key limit is 10000 → ≈5 full publishes/day, 6 at the edge. Plenty for planned cadence.

Spec recommendation: request a quota increase from GCP console only if daily volume exceeds 5.

## 6. Error handling

| Failure | Cause | Recovery |
|---|---|---|
| Missing video / thumbnail / metadata | Preflight | Error prints exact path + which command to run |
| `client_secret.json` missing | GCP setup incomplete | Error with link to setup section of this spec |
| Token file missing | First use of profile | `pipeline publish auth --profile NAME` |
| Token refresh fails | Revoked, stale, or 6mo inactivity | `pipeline publish auth --profile NAME --reauth` |
| Channel ID mismatch at auth | Wrong Google account consented | Auth aborts before writing token; tells operator expected vs. actual channel |
| Quota exceeded (403 `quotaExceeded`) | Day's 10k units burned | Hard fail. Do NOT retry. "Quota resets at PT midnight." |
| Network / 5xx during video upload | Transient | `MediaFileUpload(resumable=True)` auto-retries with exponential backoff. If ultimately fails, `youtube_video_id` not written → rerun starts over. |
| Upload ok, thumbnail fails | Thumbnail too big / wrong format / 5xx | `youtube_video_id` persisted. Fix thumbnail; rerun `pipeline publish <id>` → skips phase A. |
| Upload ok, disclosure-set fails | API oddity | `disclosure_set=False` persisted. Rerun skips A and B. |
| `publishAt` in past | Delayed operator action | Preflight catches before API call |
| `--schedule` + `--privacy=public` | Invalid combo | Preflight error |
| Niche not configured and no `--profile` | Config gap | Error with TOML template to add |

**Policy:** on any failure we **do NOT delete** the partially-uploaded video. Operator decides in Studio whether to delete or fix — auto-delete would be a footgun.

**Structured logging** (existing `structlog` conventions):

- `publish.preflight.ok` / `publish.preflight.failed { reason, path }`
- `publish.profile_resolved { profile, channel_id }`
- `publish.upload.start { project_id, bytes }`
- `publish.upload.complete { video_id, duration_s }`
- `publish.thumbnail.complete`, `publish.disclosure.complete`
- `publish.quota.exceeded` — grep-friendly.

## 7. Telegram failure notifications

New module: `src/pipeline/notify/telegram.py`.

**Env vars:** `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. Both required. If either missing: notifications silently no-op (not an error — notifier is optional).

**API used:** [Telegram Bot API `sendMessage`](https://core.telegram.org/bots/api#sendmessage) via `httpx.post`. No third-party SDK — one endpoint, one JSON body.

**Firing policy (day 1):**

- Fires only on failure in the publish stage (upload exceptions, preflight failures that reach the stage — command-line validation errors do not fire).
- Does NOT fire on success (no notification fatigue).
- If the notifier itself fails: log at WARNING level, never propagate. A broken Telegram bot must not obscure the actual pipeline error.

**Message format** (markdown-escaped for Telegram MarkdownV2):

```
🚨 *Publish failed*

Project: `1234567890`
Profile: `ideal-parents-tw`
Phase: `thumbnail`
Error: File too large \(3\.2MB \> 2MB limit\)

Fix: shrink thumbnail.png, then
`pipeline publish 1234567890`
```

**Scope is intentionally narrow (publish only) for day 1.** Future enhancement: wire the same notifier into produce / acquire stages — the module exists and is generic.

## 8. Diagnostic command

```
pipeline publish status <project-id> [--remote]
```

**Local mode (default, 0 quota):**

- Reads `context.json`.
- Prints:
  - `project_id`, `niche`, `locale`, resolved `profile`.
  - Phase completion: `video ✓ / ✗`, `thumbnail ✓ / ✗`, `disclosure ✓ / ✗`.
  - `youtube_video_id` if set + Studio URL.
  - Next recommended command (e.g., "retry with `pipeline publish 1234`").

**`--remote` mode (1 quota unit):**

- Calls `videos.list(id=youtube_video_id, part=status,snippet,contentDetails)`.
- Prints live privacy status, scheduled `publishAt` if any, title as it appears on YouTube, thumbnail URL.
- Useful if operator deleted the video in Studio but local context still thinks it's up.

## 9. CLI surface (consolidated)

```
# Publish (new)
pipeline publish <project-id> [--profile NAME] [--privacy unlisted|private|public]
                              [--schedule ISO8601] [--dry-run]
                              [--force-metadata] [--force-thumbnail]
pipeline publish auth --profile NAME [--reauth]
pipeline publish accounts list
pipeline publish accounts show NAME     # 1 quota unit
pipeline publish accounts add NAME      # interactive: fills config + runs auth
pipeline publish accounts revoke NAME   # deletes local token file
pipeline publish status <project-id> [--remote]

# Metadata helper (new)
pipeline metadata show [--project-id X]
pipeline metadata set <field>=<value> [--project-id X]
pipeline metadata regenerate [--project-id X]
pipeline metadata validate [--project-id X]

# Produce (existing, extended)
pipeline produce --url X --locale zh-TW                        # --niche auto-detected from routing
pipeline produce --url X --locale zh-TW --niche parenting      # explicit override
pipeline produce --url X --locale zh-TW --niche none           # opt-out of routing + metadata
```

**Natural-language triggers** for the assistant (to be appended to `CLAUDE.md` on implementation):

```
"upload project X to YouTube"               → pipeline publish X
"schedule X for tomorrow 7pm"               → pipeline publish X --schedule <ISO8601>
"what's the publish state of X?"            → pipeline publish status X
"what's actually live for project X?"       → pipeline publish status X --remote
"re-authorize the parenting channel"        → pipeline publish auth --profile ideal-parents-tw --reauth
"change project X's title to Y"             → pipeline metadata set title=Y --project-id X
"show me project X's metadata"              → pipeline metadata show --project-id X
```

## 10. Context and model changes

### `PipelineContext`

New fields in `src/pipeline/stages/base.py`:

```python
# Routing
niche: str | None = None        # parenting, tech, drama, ... or "none"; resolved by produce
                                # from --niche flag OR auto-detected via routing table
                                # before DirectStage runs

# Stage 6: Publish
youtube_video_id: str | None = None   # (already present, placeholder)
thumbnail_uploaded: bool = False      # new
disclosure_set: bool = False          # new
published_at: str | None = None       # ISO8601, new
publish_profile: str | None = None    # the profile used at publish time, new
```

`from_dict` / `to_dict` already handle primitives — no serialization work beyond adding fields.

### Project DB row (if active)

Add columns: `niche TEXT`, `publish_profile TEXT`, `published_at TEXT`. Existing columns `stage`, `youtube_video_id` are already sized for this.

## 11. Testing

### Unit tests (`tests/unit/publish/`)

Mock `googleapiclient.discovery.build` at the seam. Cover:

- **Channel resolution**: `--profile` overrides; `(niche, locale)` lookup; unmapped pair raises with helpful message.
- **Niche auto-detection**: exactly-one-niche case returns niche without prompting; zero-niche case errors cleanly; multi-niche case errors with the list of candidates.
- **Preflight**: each missing-file case produces the correct error string.
- **Upload sequence idempotency**: with `youtube_video_id` set, phase A is skipped and phase B runs.
- **Phase B idempotency**: with `thumbnail_uploaded=True`, phase B skipped.
- **Metadata validation**: title > 100 chars rejected; tags total > 500 rejected; `category_id` must be int.
- **Scheduling preflight**: `--schedule` + `--privacy=public` rejected; past `publishAt` rejected.
- **Quota-exceeded 403**: mapped to hard fail, no retry.
- **Channel-ID mismatch at auth**: no token written; error mentions expected vs. actual.
- **Notifier**: failure produces message with right fields; missing env vars → silent skip; notifier exception → logged, not raised.

### Integration tests (`tests/integration/publish/`, marker `network`)

Run only when `pytest -m network` or explicit opt-in.

- End-to-end upload to a documented **sandbox channel** (test profile set up by operator). Fixture: 10s MP4 + 1280×720 PNG.
- Flow: `publish → verify via videos.list → delete`. Clean teardown.
- Verifies: token refresh works; resumable upload works; thumbnails.set works; videos.update works; disclosure field is actually accepted by current API.

Spec will include a short "sandbox channel setup" appendix.

### Fixtures

- `tests/fixtures/sample_final.mp4` — 10s, 1280×720, sample narration audio.
- `tests/fixtures/sample_thumbnail.png` — 1280×720, < 500KB.
- `tests/fixtures/sample_metadata.json` — valid per Pydantic model.
- `tests/fixtures/sample_context.json` — minimal `PipelineContext` for publish tests.

### What's deliberately not tested

- `google-api-python-client` resumable upload retry logic — trust the SDK.
- YouTube's own server-side validation — we pre-validate; integration tests catch drift.

## 12. Dependencies

New deps added to `pyproject.toml`:

```toml
"google-auth>=2.30",
"google-auth-oauthlib>=1.2",
"google-api-python-client>=2.130",
# httpx already in pyproject (>=0.28) — used for Telegram notifier
```

No change to budget (all Google API usage is within free quota).

## 13. Security considerations

- **Token files**: mode 0600, `~/.config/content-creation/youtube/` directory mode 0700. Created programmatically on first auth.
- **`client_secret.json`**: same — 0600 permissions.
- **`.gitignore`**: user config lives outside the repo, so no changes needed. Local `credentials.json` (if operator ever drops one in the repo by mistake) — add `**/client_secret.json` and `**/credentials.json` defensively.
- **Log scrubbing**: structlog output must not echo token values. Wrapper functions redact `authorization` headers.
- **OAuth scopes**: request only `youtube.upload` + `youtube.readonly`. Never `youtube.force-ssl` or broader.
- **Revocation workflow**: `pipeline publish accounts revoke NAME` deletes the local token file. Operator revokes server-side via Google Account settings (linked from the help text).

## 14. Future enhancements (explicitly deferred)

- **LLM-based niche disambiguation.** Current auto-detection only handles the single-niche-per-locale case (deterministic). When multiple niches map to the same locale and `--niche` is omitted, a Claude Haiku call using source URL + `knowledge.json` could pick the best match. Invoked only in the ambiguous case; deterministic cases never pay for it. Deferred until multiple niches per locale is actually a day-to-day problem.
- **Custom local preview web app** — FastAPI/Streamlit showing thumbnail-in-grid mockup, side-by-side A/B thumbnail variants. Was option B in brainstorming.
- **AI-generated thumbnail candidates** — DALL-E/Imagen + picker UX. Was option D in brainstorming.
- **`--and-publish` flag on produce** — skip review gate for trusted workflows.
- **Publish-success notifications** — `--notify-on success` extension to the notifier.
- **Notifier wiring across produce / acquire stages** — reuse `src/pipeline/notify/telegram.py`; trivial extension.
- **Batch publish + scheduling queue** — multiple projects with staggered `publishAt`.
- **Multi-audio-track uploads** — if pipeline ever produces synchronized multi-locale audio for one video.
- **Publish-time channel re-routing** — allow re-uploading a produced project to a different channel. YouTube doesn't let you move videos between channels, so this would mean re-uploading, which creates duplicates. Deferred.
- **Dashboard integration** — `pipeline publish` events surfaced in the observability dashboard.

## 15. Prerequisites for first run

Operator-facing setup (NOT blocking for development):

1. GCP project with YouTube Data API v3 enabled.
2. OAuth 2.0 Desktop client created → `client_secret.json` saved at `~/.config/content-creation/youtube/client_secret.json`.
3. Each channel's Google account added as test user on the OAuth consent screen.
4. Telegram bot created (via @BotFather), `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` set in `.env`.
5. `configs/youtube_channels.toml` populated with profile entries for day 1 channels (parenting-zh-TW, tech-en).
6. Run `pipeline publish auth --profile ideal-parents-tw`, then `pipeline publish auth --profile tech-bummer-en` to seed tokens.

## 16. Acceptance criteria

- [ ] `pipeline publish <project-id>` uploads video, sets metadata, uploads thumbnail, sets disclosure, returns Studio + watch URLs.
- [ ] `pipeline publish <project-id>` is idempotent: rerun after any-phase failure resumes correctly.
- [ ] `pipeline publish auth --profile NAME` runs browser OAuth and writes token.
- [ ] `pipeline publish status <project-id>` prints local phase state without quota cost.
- [ ] `pipeline publish status <project-id> --remote` confirms live state on YouTube.
- [ ] `pipeline produce --url X --locale zh-TW --niche parenting` writes `metadata.json` tailored to `ideal-parents-tw` voice guide.
- [ ] `pipeline produce --url X --locale zh-TW` (no `--niche`) auto-detects `parenting` when it's the only zh-TW routing entry; errors clearly when ambiguous.
- [ ] `pipeline metadata show` / `set` / `regenerate` / `validate` all work as documented.
- [ ] Adding a third channel is: add `[profiles.xxx]` + `[routing]` entry + run `pipeline publish auth --profile xxx`. No code change.
- [ ] Failure in the publish stage fires a Telegram message (when env vars set).
- [ ] Unit tests pass with no network access.
- [ ] Integration test (marker `network`) uploads → verifies → deletes a test video on a sandbox channel.
