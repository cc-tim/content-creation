# Prerecorded Voice Engine + Subtitle Toggle — Design

## Context

The current voice pipeline (landed 2026-04-08) supports Edge-TTS and CosyVoice2 engines. CosyVoice2 turned out to be infeasible for this workstation: the target hardware is a GTX 1050 with no NVIDIA driver installed, and CosyVoice's dependency pins (`tensorrt-cu12`, `deepspeed`, `torch==2.3.1`, `onnxruntime-gpu`) would conflict with the project's `.venv` and can't run on the available GPU anyway.

Hosted voice-cloning APIs (ElevenLabs, Fish Audio) are a valid future option but introduce per-video cost and a recurring dependency. For current usage, the preferred model is: **free stock voices (Edge-TTS) for most videos across four locales, with the creator's own voice only for occasional vlog-style content**. Rather than clone the creator's voice, they will pre-record audio per scene and drop files into the project.

This spec defines a hybrid `PrerecordedEngine` that uses a creator's recordings where they exist and falls back to Edge-TTS for the rest. It also adds a `--subtitles` CLI flag so videos can be produced without burned-in captions — important when recordings may not perfectly match the scripted narration.

CosyVoice2 support is rolled back as part of this change to keep the engine abstraction honest.

## Goals

- Let a creator produce a draft video with Edge-TTS, then iteratively replace scene audio with their own recordings without re-running earlier stages.
- Tolerate minor narration text drift: a recording remains usable after small edits to `storyboard.json`, with a visible warning when text no longer matches the snapshot taken at record time.
- Make the recording workflow ergonomic: clear CLI to show scene text before recording, list recording status, and make small storyboard edits without raw JSON surgery.
- Allow videos to be produced without burned-in subtitles.
- Remove the CosyVoice engine and its dead installer/docs.

## Non-Goals

- Voice cloning, local or hosted. Explicitly deferred.
- Changes to the `analyze`, `direct`, or `scriptwrite` stages.
- Automatic text-similarity heuristics. Snapshot comparison is exact-string after `.strip()`.
- Rewriting the subtitle rendering style. `burn_subtitles=True` continues to produce the current `Noto Sans CJK TC, size 24, bottom-center` output.
- Per-project recording scopes. Recordings live under a per-voice directory and are bound to the current storyboard's scene ids.

## Architecture

The existing voice abstraction stays. One new engine (`PrerecordedEngine`) is added. `TtsStage` is extended to pass `scene.id` down to the engine. `ComposeStage` and the produce CLI gain a `burn_subtitles` flag.

```
produce --voice tim-zhtw --no-subtitles
  └── TtsStage
       └── VoiceRegistry.resolve("tim-zhtw") → (PrerecordedEngine, profile)
            per scene in storyboard.scenes:
              engine.synthesize(narration, out_path, profile, scene_id=scene.id)
                ├── recording found     → transcode to MP3, snapshot check
                └── recording missing   → delegate to EdgeEngine via fallback profile
       output: one MP3 per scene, SRT subtitle file, segment_timings
  └── ComposeStage (ctx.burn_subtitles=False)
       skip the ffmpeg subtitles filter pass
```

## Components

### `PrerecordedEngine`

New class in `src/pipeline/voices/prerecorded_engine.py`. Implements `VoiceEngine`.

Responsibilities:
- Look up a recording file by `scene_id` inside the profile's `recording_dir`, matching any of `.wav`, `.mp3`, `.m4a` (first hit wins).
- If found:
  - Read the sibling snapshot file `<scene_id>.txt` if present. If absent or content (after `.strip()`) differs from the live narration text, emit a `prerecorded.stale_recording` structlog warning with `scene_id`, `recorded_text`, `live_text`. Proceed with the recording anyway.
  - Transcode the source audio to MP3 at `out_path` via a single ffmpeg call (`-c:a libmp3lame -q:a 2`). This keeps the concat path unchanged (MP3 binary append).
  - If the snapshot file was missing, write the current text to `<scene_id>.txt` so future runs can detect drift.
- If not found:
  - Resolve the fallback voice id (`profile.params["fallback_voice_id"]`, defaulting to `registry.default_for_locale(profile.locale).id`). Use the fallback profile's engine to synthesize into `out_path`.
  - Emit a `prerecorded.fallback` structlog info event with `scene_id`, `fallback_voice_id`.
- If `scene_id` is `None`, raise `ValueError("PrerecordedEngine requires scene_id; invoke via TtsStage")`.

The engine does not hash narration text. Drift detection uses the snapshot file only.

### `VoiceEngine` signature change

`VoiceEngine.synthesize` gains an optional `scene_id: str | None = None` parameter. `EdgeEngine` ignores it. Tests call sites remain backward compatible.

### `VoiceRegistry`

`_engine_for` adds a branch for `engine == "prerecorded"` returning `PrerecordedEngine(registry=self)` (the engine needs a handle to resolve fallback profiles). The `cosyvoice` branch is removed; a profile with `engine == "cosyvoice"` now raises `VoiceNotFound` like any other unknown engine.

`VoiceProfile` gains no new top-level fields. Prerecorded-specific config lives in `params`:
- `recording_dir: str` — absolute or repo-relative path to the directory containing scene recordings.
- `fallback_voice_id: str | None` — defaults to `registry.default_for_locale(profile.locale).id` at resolve time.

### `TtsStage`

Already loads the storyboard for pause timing. One additional line: pass `scene.id` into `engine.synthesize(...)`. No other changes. `segment_timings` is still populated from ffprobe on the resulting MP3, so compose's scene re-timing continues to work unchanged.

### `ComposeStage`

`PipelineContext` gains `burn_subtitles: bool = True`. When `False`, compose skips the step-6 ffmpeg subtitles pass and copies `raw.mp4` to `final_<locale>.mp4`. No re-encode is needed: scene finals are already libx264/aac, so the concatenated `raw.mp4` is browser-ready.

The `check_overlay_allowed` call at line 162 is updated to pass `burn_subtitles=ctx.burn_subtitles`. This has no observable effect today (the legacy `text` overlay type is already forbidden unconditionally), but keeps the argument honest for future overlay rules.

### `produce` CLI flag

`pipeline produce` gains a `--subtitles / --no-subtitles` Typer flag. **Default: `--no-subtitles`.** The resolved boolean is written to `ctx.burn_subtitles` before running stages.

### Storyboard helper CLIs

New command group `pipeline storyboard` with three subcommands, all implemented in a new `src/pipeline/cli_storyboard.py`.

**`storyboard show [--scene <id>] [--work-dir <path>]`**

Without `--scene`: rich-table of all scenes — columns `id | section | narration (first 60 chars) | est_sec | pause`.
With `--scene`: full scene view — id, section, pause_after_sec, narration_est_sec, overlay type (if any), visual type (if any), full narration text.

**`storyboard recordings [--voice <voice_id>] [--work-dir <path>]`**

Table of scenes with per-scene status:

| scene_id | status | note |
|---|---|---|
| scene_001 | recorded | — |
| scene_002 | stale | text changed since record |
| scene_003 | missing | — |

Status values:
- `recorded` — file present, snapshot matches live text.
- `stale` — file present, snapshot absent or differs.
- `missing` — no recording file for this scene.

A trailing section lists `orphan` recordings: files in `recording_dir` whose `<scene_id>` has no matching entry in the storyboard.

If `--voice` is omitted, the command scans the registry for exactly one profile with `engine == "prerecorded"`. If found, it uses that profile. If zero or more than one exists, it prints an error instructing the user to pass `--voice`. The storyboard itself has no locale field, so locale-based inference is not possible.

**`storyboard set <scene_id> <field>=<value> [--work-dir <path>]`**

Non-interactive field setter. Supports a restricted allow-list of safe fields:
- `narration` — string
- `narration_est_sec` — float
- `pause_after_sec` — float
- `section` — string (validated against the known section values: `hook | context | rising | climax | aftermath | analysis | content | punchline`)

Complex fields (`visual`, `overlay`, `compartment`, `facts_ref`) are rejected with a message pointing to direct JSON editing. The storyboard is re-saved in place after validation.

### CLAUDE.md commands section

Add to the Commands block:

```
# Storyboard editing
pipeline storyboard show                         # list all scenes
pipeline storyboard show --scene scene_003       # one scene's full text
pipeline storyboard recordings --voice tim-zhtw  # record status per scene
pipeline storyboard set scene_003 narration="..."
```

Plus a short "Natural-language triggers" note so `storyboard show --scene X` is the default response to "show me scene X's narration", `storyboard recordings` to "which scenes still need recording", etc.

### CosyVoice rollback

Files deleted:
- `src/pipeline/voices/cosy_engine.py`
- `tests/unit/test_cosy_engine.py` (if present)
- `scripts/install_cosyvoice.sh`

Files modified:
- `src/pipeline/voices/registry.py` — remove cosyvoice branch from `_engine_for`, add prerecorded branch.
- `pyproject.toml` — remove `[project.optional-dependencies].cosyvoice` and any transitive cosyvoice deps that leaked into main.
- `src/pipeline/cli_voice.py` — remove cosyvoice-specific handling from `voice add`; drop cosyvoice help text.
- `tests/unit/test_voice_cli.py` — drop cosyvoice assertions; add prerecorded coverage.

Files rewritten:
- `scripts/record_voice.md` — new content covering the prerecorded workflow (registry entry, recording directory, iteration loop, stale/orphan handling, reference script).

Files kept:
- `VoiceEngine` ABC, `VoiceProfile`, `VoiceRegistry`, `EdgeEngine`.
- `voices/cloned/` directory and `voices/prerecorded/` directory (placeholder `.gitkeep` for the latter).

The cleaned local clone at `~/.local/share/CosyVoice` is outside the repo; removal is left to the user.

## Data Flow: Iteration Loop

```
1. Creator runs `pipeline direct` (or hand-edits storyboard.json).
2. Creator runs `pipeline produce <url> --voice tim-zhtw`.
   All scenes use Edge fallback → draft video ready.
3. Creator runs `pipeline storyboard recordings --voice tim-zhtw`.
   Every scene is `missing`.
4. Creator runs `pipeline storyboard show --scene scene_003`.
   Reads the narration, records voices/prerecorded/tim-zhtw/scene_003.wav.
5. Creator reruns `pipeline produce <url> --voice tim-zhtw`.
   scene_003 uses the recording; others still use Edge.
   Snapshot file voices/prerecorded/tim-zhtw/scene_003.txt is written.
6. Creator iterates per scene. If they later hand-edit scene_003's
   narration in storyboard.json, the next produce run warns
   `prerecorded.stale_recording` but still uses the recording.
   `storyboard recordings` marks scene_003 as `stale`.
7. When satisfied, creator re-records scene_003; snapshot updates.
```

## Error Handling

- `PrerecordedEngine` with `scene_id=None` → `ValueError`.
- `PrerecordedEngine` with missing `recording_dir` param → `ValueError` at engine construction time (profile validation).
- Recording file present but unreadable → ffmpeg transcode raises; engine propagates. Not silently fallback-ed because it indicates user intent that something is there.
- Fallback engine raises → propagates unchanged.
- `storyboard set` on a forbidden field → `typer.BadParameter`.
- `storyboard recordings` with no storyboard at work_dir → typer error pointing to `--work-dir`.

## Testing Strategy

Unit tests, all mocking ffmpeg via monkeypatch unless otherwise noted:

1. `tests/unit/test_prerecorded_engine.py`
   - `scene_id` None → raises.
   - Recording found, no snapshot → transcodes, writes snapshot, no warning.
   - Recording found, snapshot matches → transcodes, no warning.
   - Recording found, snapshot differs → transcodes, emits `stale_recording` warning.
   - Recording missing → delegates to fallback engine with same args.
   - `fallback_voice_id` omitted → uses `registry.default_for_locale(profile.locale)`.

2. `tests/unit/test_storyboard_cli.py`
   - `show` without `--scene` → prints all scenes.
   - `show --scene scene_003` → prints full narration.
   - `recordings` with mixed states → classifies each correctly, lists orphans.
   - `set scene_003 narration="x"` → writes back; file is valid JSON.
   - `set scene_003 visual.type=still` → rejected.
   - `set scene_003 section=unknown` → rejected.

3. `tests/unit/test_tts.py` — add case: `voice_id` resolves to prerecorded profile, one scene has a recording, another doesn't; assert mixed audio paths and that fallback engine was called exactly once.

4. `tests/unit/test_voice_registry.py` — add: `_engine_for` returns `PrerecordedEngine` for `engine == "prerecorded"`; `cosyvoice` now raises `VoiceNotFound`.

5. `tests/unit/test_voice_cli.py` — replace cosyvoice add path with prerecorded add path.

6. `tests/unit/test_compose.py` — with `burn_subtitles=False`, ffmpeg command list does not contain `-vf subtitles=...`; with `True`, it does.

Integration (marked `@pytest.mark.integration`):

7. `tests/integration/test_prerecorded_end_to_end.py` — small storyboard (2 scenes), a real 1-second WAV at `voices/prerecorded/<voice>/scene_001.wav`, run `TtsStage` + `ComposeStage`, assert final mp4 exists and total duration within tolerance of the sum of ffprobe durations + pauses.

Fixtures:
- `tests/fixtures/short_narration.wav` — 1 second of silence, mono 16 kHz. Generated once with `ffmpeg -f lavfi -i anullsrc -t 1 -ar 16000 -ac 1 short_narration.wav`.

## File Plan

**New:**
- `src/pipeline/voices/prerecorded_engine.py`
- `src/pipeline/cli_storyboard.py`
- `tests/unit/test_prerecorded_engine.py`
- `tests/unit/test_storyboard_cli.py`
- `tests/integration/test_prerecorded_end_to_end.py`
- `tests/fixtures/short_narration.wav`
- `voices/prerecorded/.gitkeep`

**Modified:**
- `src/pipeline/voices/base.py` — add `scene_id: str | None = None` to `VoiceEngine.synthesize` signature.
- `src/pipeline/voices/edge_engine.py` — accept + ignore `scene_id`.
- `src/pipeline/voices/registry.py` — remove cosyvoice branch, add prerecorded branch, pass registry handle to `PrerecordedEngine`.
- `src/pipeline/stages/tts.py` — pass `scene.id` to `engine.synthesize`.
- `src/pipeline/stages/base.py` — add `burn_subtitles: bool = True` to `PipelineContext`.
- `src/pipeline/stages/compose.py` — conditional subtitle pass; update `check_overlay_allowed` call to use `ctx.burn_subtitles`.
- `src/pipeline/cli.py` — add `--subtitles / --no-subtitles` flag to `produce`; register `storyboard` subcommand group.
- `src/pipeline/cli_voice.py` — drop cosyvoice path; accept `--engine prerecorded` with `--recording-dir` and `--fallback-voice` flags.
- `pyproject.toml` — drop `[project.optional-dependencies].cosyvoice`.
- `CLAUDE.md` — Commands section: add storyboard subcommands + natural-language triggers.
- `scripts/record_voice.md` — rewritten for prerecorded workflow.
- `tests/unit/test_tts.py`, `tests/unit/test_voice_registry.py`, `tests/unit/test_voice_cli.py`, `tests/unit/test_compose.py` — per tests list.

**Deleted:**
- `src/pipeline/voices/cosy_engine.py`
- `tests/unit/test_cosy_engine.py` (if present)
- `scripts/install_cosyvoice.sh`

## Open Questions

None blocking. One future consideration: if creator uses the same recording across multiple storyboards (e.g., a channel intro line), the scene-id key will not reuse across projects. That's fine under current scope — channel intros, if any, would be composed separately.
