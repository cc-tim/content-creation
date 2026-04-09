# Voice Pipeline + Gemini Image Provider + Composition Overhaul

**Date:** 2026-04-08
**Status:** Draft — awaiting user review
**Scope:** Three coupled features that together let us regenerate project `1775401082` to a higher production bar and raise the bar for every future video.

## Motivation

The first end-to-end production run (project `1775401082`, "AI can write full apps") surfaced three concrete problems:

1. **Visual problems in the composed video.**
   - `text` overlays render as a lower-third bar and collide with burned-in subtitles, making both illegible (confirmed in `compose/review_frames/review_000.jpg`).
   - The start scene is a single static generated image with a title overlay — visually flat, does not grab attention, does not outline the story.
   - Emotionally charged scenes (e.g. "Context Anxiety") are rendered the same as any other static image + overlay; no emotional emphasis.
   - The render evaluator sub-agent does not catch these issues, because its rules don't cover overlay placement, start scene quality, or emotional framing.

2. **Voice is locked to edge-tts.** There is no way to use the user's own voice or any custom voice. The TTS stage hardcodes edge-tts and selects a voice by locale from `PipelineConfig`. This limits production value and makes the output feel generic.

3. **Image generation is locked to DALL-E.** The only provider is OpenAI DALL-E 3 via `composer/image.py`. There is no Gemini provider and no fallback chain. Gemini's "nano banana" model (`gemini-2.5-flash-image-preview`) has a free tier that, if used as the primary, reduces monthly spend and gives better illustration quality for some prompts.

This spec addresses all three. The features are coupled by a single validation target: **regenerate `output/projects/1775401082/compose/final_zh-TW.mp4` to a higher bar using the new composition primitives, the new Gemini provider, and (for future videos) the new voice pipeline.**

## Non-goals

- Voice cloning for this specific regeneration. The regeneration uses edge-tts (default voice) to keep the critical path short. The voice pipeline ships in parallel and the user records a sample later.
- ElevenLabs, Google Cloud TTS, or other paid TTS engines. Edge-tts and CosyVoice2 cover the "free + my voice" requirement.
- Imagen 3 or other higher-cost image providers. Chain is Gemini → DALL-E → text-card fallback.
- New target locales. zh-TW stays the primary; ja and es remain future work.
- Shorts (9:16) regeneration. This spec focuses on the standard 16:9 long-form output.

---

## Feature 1 — Composition Overhaul

### 1.1 Overlay placement rules

**Rule (hard):** No overlay element may render below `y = 0.70` when subtitles are burned in. The subtitle zone is the bottom 30% of the frame.

**`overlay.py` refactor:** The current `text` overlay variant is removed. Replacements:

| Variant | Position | Use for |
|---|---|---|
| `title` | centered band `y=35%–65%` | Bold titles, hero statements. Unchanged. |
| `text_top` | top band `y=5%–17%` | Lower-third lines that currently collide — now at the top |
| `text_left` | left 35% panel, image scales into right 65% | Quote + supporting image layouts |
| `text_emphasis` | right 35% panel, with animation | Emotional emphasis (deferred to compartments, see 1.2) |
| `namecard` | upper-lower `y=65%–79%` | Speaker attribution. Unchanged. |

The `text` type is gone. Any existing storyboard entries with `"type": "text"` are migrated to `"text_top"` by a one-time migration script (`scripts/migrate_overlays.py`) that rewrites `storyboard.json` files in `output/projects/*/`.

### 1.2 Compartments

A **compartment** is a small looping animation anchored to a sub-region of a scene (typically 35% width × 60% height on the right). The base visual scales into the remaining area. Compartments are defined by the new `Scene.compartment` field:

```jsonc
{
  "id": "s3",
  "visual": { "type": "generated_image", "prompt": "..." },
  "compartment": {
    "type": "running_out",
    "position": "right",
    "size": { "width": 0.35, "height": 0.6 },
    "loop": true,
    "animation": { ... }
  },
  "overlay": null
}
```

**Compartment types** (in `src/pipeline/composer/compartments/`):

- `running_out` — countdown value + face progression + pulse/shake. Used for anxiety/deadline scenes.
- `loading_bar` — horizontal progress bar + percentage. Used for processing scenes.
- `score_counter` — number ticking up. Used for success/scaling scenes.
- `clock_ticking` — clock face. Used for time-pressure scenes.

**Rendering pipeline (per compartment):**

1. `render(work_dir, scene_id, size_px, animation_spec) -> Path`
2. Generates N keyframes using PIL. For `running_out`, each keyframe composes: background rounded-rect, label text, counter value, and a Twemoji PNG face.
3. Encodes frames into a small loop MP4 (5 fps is enough for face transitions; more for shake).
4. Caches by `hash(type, stages, label, size_px)`.
5. Returned MP4 is composited onto the base visual by FFmpeg using `-stream_loop -1`, letting the loop wrap automatically when the scene duration exceeds the loop length.

**Twemoji assets:** Checked into `assets/twemoji/` under the CC-BY 4.0 license (Twemoji images are MIT; emoji designs are CC-BY 4.0 — attribution goes in a top-level `NOTICE` file). Only ~30 face emojis are checked in, not the full Twemoji set.

**Face name → Twemoji mapping** (face key used in `animation.stages[*].face`):
- `neutral` → `1f610.png` (neutral face)
- `worried` → `1f625.png` (sad but relieved face)
- `panicked` → `1f628.png` (fearful face)
- `exhausted` → `1f629.png` (weary face)
- `triumphant` → `1f924.png` (money-mouth face)
- `thinking` → `1f914.png` (thinking face)

(Complete mapping lives in `compartments/faces.py`.)

### 1.3 Intro primitives

Four new visual types in `src/pipeline/composer/intro/`:

- `intro_montage` — multi-image with crossfade or slide transitions and per-image Ken Burns zoom
  ```jsonc
  {
    "type": "intro_montage",
    "images": [
      { "prompt": "...", "duration_sec": 2.0, "ken_burns": "zoom_in" },
      { "prompt": "...", "duration_sec": 2.0, "ken_burns": "pan_left" }
    ],
    "transition": "crossfade",   // crossfade | slide | cut
    "transition_sec": 0.4
  }
  ```
- `intro_clip_cuts` — multi-cut from source video with transitions
  ```jsonc
  {
    "type": "intro_clip_cuts",
    "cuts": [{ "start_sec": 12.0, "duration_sec": 1.5 }, ...],
    "transition": "whoosh"
  }
  ```
- `intro_kinetic` — animated text-only scene
  ```jsonc
  {
    "type": "intro_kinetic",
    "words": ["AI", "自己", "寫", "完整", "應用"],
    "style": "word_reveal",     // word_reveal | scale_pulse | slide_in
    "background": "#1e293b"
  }
  ```
- `intro_compound` — interleaves any of the above
  ```jsonc
  {
    "type": "intro_compound",
    "elements": [
      { "type": "intro_montage", ... },
      { "type": "intro_kinetic", ... }
    ]
  }
  ```

### 1.4 Start Scene Director sub-agent

A new step in `/produce` dispatched **after** the draft storyboard exists for s2 onwards.

**Invocation:** `Agent(subagent_type="general-purpose", prompt=<director prompt>)` — runs in an independent context so it brings fresh creative eyes (same pattern as existing knowledge/storyboard/render evaluators).

**Director inputs:**
- `knowledge.json` — the full fact/entity/timeline base
- `storyboard.json` — draft storyboard with scenes s2 onwards (s1 is a placeholder)
- `source/keyframes/` — if available (YouTube source)
- `source/images/` — if available (web source)
- Optional user directive via `--start-scene "<text>"` passed to `/produce`

**Director prompt responsibilities** (summarized):
1. **Research phase.** Identify the central tension, the strongest visual metaphor, and at least one foreshadowing opportunity to a specific later scene.
2. **Brainstorm phase.** Generate ≥3 distinct start scene options using different primitives (`intro_montage`, `intro_clip_cuts`, `intro_kinetic`, `intro_compound`).
3. **Decision phase.** Rank the options. Output the **top 2** with:
   - Full `s1` scene definition (using one of the `intro_*` types)
   - A "creative brief" explaining what this s1 does for the video and which later scene it foreshadows
4. **Image sourcing.** The director may:
   - Reuse cached images from `compose/scenes/image_cache/`
   - Reuse source images from `source/images/` or keyframes from `source/keyframes/`
   - Request **new** image generations via the Gemini provider (by calling a helper `generate_image(prompt)` exposed to it)
5. **Constraints.** A single static image is auto-fail. At least 3 visual events in the first 5 seconds (image transition, kinetic text reveal, or clip cut each count as events).

**User interaction:** After the director outputs the top 2 options, `/produce` shows both briefs and scene definitions to the user. The user picks one, picks the alternate, or requests re-research with new constraints.

### 1.5 Render evaluator rules

Updates to the Step 7b evaluator sub-agent in `/produce`:

**New hard-fail rules (NEEDS_WORK if any fail):**

1. **Subtitle collision.** For each scene with subtitles enabled, the evaluator reads the storyboard overlay metadata. If any overlay's effective y-range extends below `0.70`, flag NEEDS_WORK with the specific scene id. Auto-check from storyboard; doesn't need pixel inspection.
2. **Start scene quality.** s1 must use one of the `intro_*` visual types. A static `generated_image` or `text_card` as s1 is auto-fail. Additionally, the first 5 seconds of the rendered video must show ≥3 visual events (the evaluator extracts 5 frames at `t=0, 1, 2, 3, 4` and compares them — three identical frames means no events).
3. **Anxiety/emotion soft check.** Evaluator scans each scene's narration for a per-locale regex catalog of emotion keywords (`running out`, `deadline`, `anxiety`, `上下文焦慮`, `時間不夠`, etc.). For each match, if the scene has no `compartment`, emit a **soft warning** (not a hard fail) in the evaluator report.

**Unchanged rules:** text readability, visual coherence, pacing, visual variety, production quality — scores as before.

---

## Feature 2 — Voice Pipeline

### 2.1 Module structure

```
src/pipeline/voice/
  __init__.py
  registry.py         # load/save voices/registry.json, resolve id → VoiceProfile
  profile.py          # VoiceProfile dataclass
  engines/
    base.py           # VoiceEngine ABC
    edge.py           # wraps edge-tts
    cosyvoice.py      # CosyVoice2 zero-shot cloning
  cli.py              # typer subcommands: list, add, test, remove, record-script
```

### 2.2 Engine interface

```python
class VoiceEngine(ABC):
    name: str

    def supports(self, locale: str) -> bool: ...

    async def synthesize(
        self,
        text: str,
        locale: str,
        voice_profile: VoiceProfile,
        out_path: Path,
    ) -> SynthesisResult: ...
        # returns SynthesisResult(path, duration_ms)
```

- `EdgeEngine`: `voice_profile.voice` is the Azure voice id. Current code moves here.
- `CosyVoiceEngine`: lazy-loads CosyVoice2 model on first call. Uses `voice_profile.sample` + `voice_profile.transcript` for zero-shot cloning. Runs on CUDA if available, else CPU with a warning.

### 2.3 `stages/tts.py` refactor

- `PipelineContext` gains `voice_id: str | None = None`.
- `TtsStage.run` resolves the voice:
  ```python
  registry = VoiceRegistry.load()
  voice_profile = registry.resolve(ctx.voice_id or registry.default, ctx.locale)
  engine = get_engine(voice_profile.engine)
  await engine.synthesize(text, ctx.locale, voice_profile, seg_path)
  ```
- Segment chunking, subtitle building, and timing logic are **unchanged** — they operate on synthesized audio regardless of engine.
- If the resolved voice doesn't support the locale (`supports(locale) == False`), `TtsStage` raises a clear error listing the registered voices that do support that locale.

### 2.4 Voice library layout

```
voices/                        # gitignored except registry and sample scripts
  .gitkeep
  registry.json
  _samples/
    recording_script_zh-TW.md
    recording_script_en.md
    recording_script_ja.md
  tim_zh/                      # created by `voice add`
    sample.wav
    transcript.txt
    profile.json
```

`.gitignore` addition: `voices/*/` (profile dirs) but not `voices/registry.json` or `voices/_samples/`.

### 2.5 `registry.json` schema

```jsonc
{
  "default": "edge_hsiao_chen",
  "voices": [
    {
      "id": "edge_hsiao_chen",
      "engine": "edge-tts",
      "voice": "zh-TW-HsiaoChenNeural",
      "locales": ["zh-TW"],
      "notes": "default free voice"
    },
    {
      "id": "tim_zh",
      "engine": "cosyvoice2",
      "sample": "voices/tim_zh/sample.wav",
      "transcript": "voices/tim_zh/transcript.txt",
      "locales": ["zh-TW"],
      "notes": "Tim's voice, recorded 2026-04-08"
    }
  ]
}
```

Registry resolution rules:
1. `registry.resolve(None, locale)` → use `registry.default`; raise if it doesn't support `locale`.
2. `registry.resolve(id, locale)` → look up by id; raise if not found or doesn't support `locale`.

### 2.6 CLI (`uv run pipeline voice ...`)

- `list` — prints voices in a table (id, engine, locales, default marker)
- `add <id> --sample <wav> --transcript-file <txt> --locale <code> [--engine cosyvoice2] [--default]`
  - Validates sample via `ffprobe`: duration 10–60s, channels OK, sample rate ≥ 22050
  - Copies sample and transcript into `voices/<id>/`
  - Writes `voices/<id>/profile.json`
  - Updates `registry.json`; if `--default`, sets `default` to this id
- `test <id> --text "<text>" [--locale zh-TW]` — synthesizes to `voices/<id>/test_<timestamp>.wav`, prints path
- `remove <id>` — deletes `voices/<id>/` and unregisters
- `record-script [--locale zh-TW]` — prints the recording script to stdout with line-by-line reading tips (pacing, consistent distance from mic, quiet environment)

### 2.7 `/produce` CLI flag

- New arg: `--voice <id>` (default: `registry.default`)
- `/produce` skill markdown updated to mention:
  > To use your own voice, first run `uv run pipeline voice add tim_zh --sample <recording.wav> --transcript-file <text.txt> --locale zh-TW`, then call `/produce <url> --voice tim_zh`.

### 2.8 Recording scripts

`voices/_samples/recording_script_zh-TW.md` (full content written into repo):

```markdown
# zh-TW Voice Cloning Sample Script

**Instructions:**
- Read the passage below at your normal speaking pace (not too fast, not too slow)
- Keep consistent distance from the mic (hand-width)
- Record in a quiet room
- Save as WAV or MP3; the tool will convert

**Passage (~30 seconds):**

大家好，歡迎來到今天的影片。今天我想跟各位分享一個非常有趣的研究。
在人工智慧快速發展的時代，我們常常聽到像是 GPT、Claude 這些名字。
但你知道嗎？讓 AI 真正能夠寫出完整應用程式的關鍵，其實不在於模型本身，
而在於整個系統的設計。從規劃、執行到評估，每一個環節都不能少。
那麼，接下來就讓我們一起來看看，研究員到底是怎麼做到的？
```

Equivalent `_en.md` and `_ja.md` scripts ship too, each ~30 seconds with phonetic coverage for their language.

### 2.9 Dependencies

`pyproject.toml` additions:
- `torch>=2.1` — already likely present; verify
- `torchaudio>=2.1`
- `google-genai>=0.8` (for Feature 3, listed here because pinning happens in one place)
- CosyVoice2 is installed from source (not on PyPI) via a post-install script: `scripts/install_cosyvoice.sh` clones `FunAudioLLM/CosyVoice` at a pinned commit into `third_party/cosyvoice/` and installs in editable mode. Weights (~2 GB) download on first use into `~/.cache/cosyvoice/`.

**First-run confirmation:** `voice add ... --engine cosyvoice2` prints a clear warning that ~2 GB will download and waits for `y/N` confirmation.

---

## Feature 3 — Gemini Image Provider

### 3.1 Module structure

```
src/pipeline/composer/providers/
  __init__.py        # try_chain(prompt, width, height) -> bytes
  base.py            # ImageProvider ABC, RateLimitError, ProviderError
  gemini.py          # Gemini 2.5 Flash Image
  dalle.py           # OpenAI DALL-E 3 (moved from composer/image.py)
```

### 3.2 Provider base

```python
class ImageProvider(ABC):
    name: str

    def is_available(self) -> bool: ...           # has key + not in cooldown
    def generate(self, prompt: str, width: int, height: int) -> bytes: ...
```

Exceptions (in `providers/base.py`):
- `RateLimitError` — put provider in 5-minute cooldown
- `QuotaExceededError` — put provider in 1-hour cooldown
- `ProviderError` — transient error, no cooldown, move to next provider

### 3.3 Gemini provider (`providers/gemini.py`)

- SDK: `google-genai`
- Model: `gemini-2.5-flash-image-preview`
- Reads key from env via pydantic-settings (see 3.5)
- Maps target `(width, height)` to the closest Gemini-supported aspect ratio (square, landscape, portrait)
- Returns raw PNG bytes
- Catches `google.genai.errors.ResourceExhausted` → raises `RateLimitError`
- Catches other `google.genai.errors.*` → raises `ProviderError`

### 3.4 Try-chain (`providers/__init__.py`)

```python
def try_chain(prompt: str, width: int, height: int) -> bytes:
    chain = get_provider_chain()   # from PIPELINE_IMAGE_PROVIDERS env, default "gemini,dalle"
    errors = []
    for name in chain:
        provider = get_provider(name)
        if not provider.is_available():
            errors.append((name, "unavailable"))
            continue
        try:
            return provider.generate(prompt, width, height)
        except RateLimitError:
            logger.info("provider.rate_limited", provider=name)
            _mark_cooldown(name, seconds=300)
            errors.append((name, "rate_limited"))
            continue
        except QuotaExceededError:
            logger.warning("provider.quota_exceeded", provider=name)
            _mark_cooldown(name, seconds=3600)
            errors.append((name, "quota_exceeded"))
            continue
        except ProviderError as e:
            logger.warning("provider.error", provider=name, error=str(e))
            errors.append((name, str(e)))
            continue
    raise AllProvidersFailedError(errors)
```

Cooldowns stored in a module-level dict keyed by provider name; resets across process restarts (fine — each `/produce` run is a fresh process).

### 3.5 Config

`src/pipeline/config.py` additions:

```python
GEMINI_API_KEY: str = Field(
    default="",
    validation_alias=AliasChoices("GEMINI_API_KEY", "PIPELINE_GEMINI_API_KEY"),
)
IMAGE_PROVIDERS: str = "gemini,dalle"   # comma-separated chain
```

Key resolution order (pydantic-settings):
1. `GEMINI_API_KEY` from shell env (primary path, set in `~/.bashrc`)
2. `PIPELINE_GEMINI_API_KEY` from `.env`
3. Empty string → provider reports `is_available() == False`

### 3.6 `composer/image.py` refactor

- Replace `_download_dalle_image` with `providers.try_chain(prompt, width, height)`
- On `AllProvidersFailedError`, fall through to the existing text-card placeholder (unchanged)
- Cache key still `md5(prompt)` — provider-agnostic
- Cache metadata: write `<hash>.json` sibling with `{provider, generated_at, prompt, width, height}`

### 3.7 Dependencies

- `google-genai>=0.8` added to `pyproject.toml`

---

## Feature 4 — Regenerating Project 1775401082

### 4.1 Prerequisites

Features 1 and 3 must be shipped. Feature 2 ships in parallel but is not on the critical path — this regeneration uses edge-tts (current default voice).

### 4.2 Storyboard edits

Applied to `output/projects/1775401082/storyboard.json`:

**s1 (hook)** — rebuilt by the Start Scene Director sub-agent. Central metaphor candidates: "AI judging its own work" / "GAN generator-critic loop" / "harness components as assumptions". Director brainstorms ≥3 options, returns top 2, user picks.

**s2 (self-evaluation)** — overlay `text` → `text_top`. Narration unchanged.

**s3 (Context Anxiety)** — add compartment:

```jsonc
{
  "id": "s3",
  "visual": {
    "type": "generated_image",
    "prompt": "A focused developer at a calm clean workspace, simple flat illustration, white background, blue accents"
  },
  "compartment": {
    "type": "running_out",
    "position": "right",
    "size": { "width": 0.35, "height": 0.6 },
    "loop": true,
    "animation": {
      "label": "上下文焦慮",
      "stages": [
        { "value": "20%", "face": "neutral",  "color": "#fbbf24" },
        { "value": "10%", "face": "worried",  "color": "#fb923c" },
        { "value": "5%",  "face": "panicked", "color": "#ef4444" }
      ],
      "stage_duration_sec": 1.5,
      "shake": true
    }
  },
  "overlay": null
}
```

**s4, s5, s9, s15** — overlay `text` → `text_top`. Base images unchanged (cache hit).

**s6 (art gallery)** — overlay `text` → `text_top`. Consider cache-busting for regeneration via Gemini if image quality improves.

**s10 (comparison)** — overlay text fixed from the malformed string `"單獨AI： / 壞掉 vs 多代理：00 / 16功能完整"` to `"單獨 AI：$9 / 壞掉  vs  多代理：$200 / 16 功能完整"`. Overlay type `text_top`.

**s16 (conclusion)** — overlay `title` (unchanged, centered title is OK).

### 4.3 Execution order

1. `uv run pipeline produce --url <url> --project-id 1775401082 --start-from direct --locale zh-TW` — re-enters at the `direct` (storyboard generation) stage, reusing existing `source/` and `knowledge.json`. The implementation plan will add `--start-from director` as a finer-grained entry point if needed.
2. Start Scene Director proposes top 2 s1 options; user (or Tim directly in this conversation) picks
3. Storyboard edits above are applied
4. TTS re-runs only for scenes whose narration text changed (in practice, only s3 if its narration changes; everything else cache-hits on audio by text hash)
5. Compose re-runs; scenes whose `(visual, compartment, overlay)` didn't change reuse their cached `<scene_id>_final.mp4`; changed scenes re-render
6. Render evaluator runs with new rules; on PASS, present final video; on NEEDS_WORK, iterate
7. Review frames go to `compose/review_frames_v4/`; previous `review_frames*` directories are preserved for diffing

### 4.4 Success criteria

- Final video plays from start to finish with no caption/overlay collisions (evaluator PASS on subtitle collision rule)
- s1 is visibly more dynamic than the old single-static-image version (evaluator PASS on start scene quality rule, ≥3 visual events in first 5s)
- s3 shows a looping anxiety compartment on the right with the 20% → 10% → 5% progression and face transitions
- s10 overlay text renders correctly (no garbled unicode)
- Total render time under 5 minutes on current hardware

---

## Testing

### Unit tests

- `tests/unit/test_overlay_placement.py` — parametrized over `(overlay_type, subtitles_enabled)`, asserts effective y-range
- `tests/unit/test_compartments.py` — renders each compartment type with a tiny frame count, asserts output file exists + has expected duration
- `tests/unit/test_intro_primitives.py` — renders each `intro_*` type with mocked image generation
- `tests/unit/test_voice_registry.py` — registry load/save, resolution, error cases
- `tests/unit/test_voice_engines.py` — mocks both engines, asserts synthesize is called with correct args
- `tests/unit/test_image_providers.py` — mocks provider chain, verifies fallback order, cooldown behavior, "all failed" path
- `tests/unit/test_gemini_provider.py` — mocks `google-genai` client, verifies request format and error mapping
- `tests/unit/test_render_evaluator_rules.py` — synthesized storyboard inputs, asserts the new rules fire

### Integration tests (marked `slow` or `network`)

- `tests/integration/test_compose_with_compartment.py` — end-to-end render of a single scene with a `running_out` compartment; asserts final MP4 has the expected duration and frame count
- `tests/integration/test_voice_edge_engine.py` — actually calls edge-tts, asserts audio is produced (`network` mark)
- `tests/integration/test_gemini_provider.py` — actually hits Gemini with a trivial prompt (`network` mark, skip if `GEMINI_API_KEY` missing)

### Manual validation

- Regeneration of `1775401082` itself is the primary manual validation
- Diff old review frames vs new ones visually
- Play the final MP4 and confirm the anxiety compartment looks right

---

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| CosyVoice2 install is non-trivial and may fail on the target machine | Install script `scripts/install_cosyvoice.sh` with clear failure modes; voice pipeline ships independently so its failure doesn't block composition or Gemini work |
| Gemini rate-limit cooldowns may cascade into DALL-E billing | Log all provider transitions; add a budget cap config `PIPELINE_DALLE_MAX_IMAGES_PER_RUN` that hard-stops DALL-E after N calls in a run |
| Twemoji assets increase repo size | Only check in ~30 specific face PNGs (~100 KB total), add a `NOTICE` file for CC-BY 4.0 attribution |
| Start Scene Director sub-agent may generate impractical scenes (e.g. 20 images, 30-second intro) | Director prompt caps: ≤5 images, ≤8-second total intro duration, must reuse cached images when possible |
| Compartment rendering adds significant per-scene render time | Aggressive caching by animation spec hash; compartments are small (35% × 60%) so they render fast |
| Overlay migration script misses edge cases in old storyboards | Migration is opt-in per project; dry-run mode prints the diff before applying |

---

## Rollout

1. Land Feature 3 (Gemini provider) first — smallest, unblocks the director's ability to generate new images
2. Land Feature 1 (composition fixes, compartments, intro primitives, director sub-agent, evaluator rules)
3. Land Feature 2 (voice pipeline) in parallel with Feature 1 — independent touchpoints
4. Regenerate project `1775401082` (Feature 4) as the validation gate
5. Update `CLAUDE.md` with new voice library location, new overlay variants, new compartment system, and provider chain env vars

## Open questions

None remaining at design-time. All decisions confirmed with user in brainstorm conversation on 2026-04-08.
