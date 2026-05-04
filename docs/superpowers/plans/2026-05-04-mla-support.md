# MLA Support Implementation Plan

**Goal:** Enable Multi-Language Audio (zh-TW + EN) workflow end-to-end: dual TTS audio, no burned subtitles, subtitle upload via API, translated metadata via API. MLA audio track upload to YouTube Studio remains a manual step (no API).

**API verification (2026-05-04):**
- `captions.insert` — confirmed in Data API v3 ✅
- `snippet.localizations` on video resource — confirmed ✅
- Alternative audio track upload — **not in API**. YouTube Studio → Video → Audio tab only. Permanent.

---

## Design Decisions

### D1: Dual TTS strategy — total-duration constraint (Strategy A, total-only)

EN narration is written fresh per scene targeting zh-TW scene duration. Not time-stretched. Rationale: this is an explainer-path project where EN can be authored with duration awareness.

**Duration constraint is total, not per-scene.** For YouTube MLA the alternate audio is one contiguous file — per-scene drift is acceptable as long as totals reconcile. TTS stage:
- Warns per-scene if EN segment > zh-TW segment × 1.15 (authoring quality signal, not a blocker)
- **Hard-fails** if total EN audio duration deviates from total zh-TW audio duration by more than ±2s. User must re-author scenes or accept that misalignment. No silent padding/truncation.

This keeps the failure mode explicit: re-author the outlier scene(s), rerun TTS.

### D2: Storyboard schema — additive `narration_en` field

Add `narration_en: str | None = None` to the `Scene` dataclass. Backward-compatible — existing projects ignore it. `narration` remains zh-TW primary. Both fields participate in verifier haystack.

### D3: Verifier haystack — include `narration_en`

`_haystack_for_lines` in `verifier.py` must also concatenate `narration_en` per scene. The baby-walker verbatim_lines are English; the verifier would incorrectly mark them missing if only zh-TW narration is searched.

### D4: PipelineContext additions

```python
# MLA fields
mla: bool = False                          # activates dual-TTS + no-burn path
secondary_locale: str | None = None        # e.g. "en"
secondary_voice_id: str | None = None
secondary_narration_path: Path | None = None
secondary_subtitle_path: Path | None = None
captions_uploaded: dict[str, str] = {}     # locale → YouTube caption_id (for idempotency)
```

When `mla=True`, compose stage forces `preferred_variant = "no_overlay"` (no burned subtitles, no burned overlays). **Contract:** only primary (zh-TW) audio is muxed into the final mp4. Secondary narration is a sibling `.mp3` artifact uploaded separately to YouTube Studio. A test must assert the final mp4 has exactly one audio stream.

### D4a: defaultLanguage vs defaultAudioLanguage with MLA

Both stay `zh-TW` — primary audio is zh-TW. EN translations surface through `localizations.en`, not by changing the default audio language declaration.

### D5: Publish phase order

```
Phase A: videos.insert (upload)
Phase B: thumbnails.set
Phase C: videos.update (disclosure + localizations in same call — add part="snippet,localizations")
Phase D: captions.insert × N locales (zh-TW .srt + EN .srt)
[Manual]: YouTube Studio → Audio → Upload EN audio track
```

Phase C is updated (not new) — `localizations` is included in the `videos.update` call alongside disclosure so no extra API round-trip.

### D6: Metadata model — `localizations`

```python
class LocalizedMeta(BaseModel):
    title: str = Field(max_length=100)
    description: str = Field(max_length=5000)

class Metadata(BaseModel):
    ...existing fields...
    localizations: dict[str, LocalizedMeta] = Field(default_factory=dict)
    # keys are BCP-47 codes: "en", "zh-TW", etc.
```

`_build_upload_body`: include `localizations` in snippet only when non-empty (YouTube errors on empty dict in some paths). When `localizations` is present, add `"localizations"` to the `part` parameter string.

### D7: DirectStage — dual metadata generation

Single Claude call with structured output requesting both zh-TW and EN title + description simultaneously. Cheaper than two calls; prompt caching still applies on system prompt. Result: `metadata.json` gains `localizations.en.{title, description}`.

---

## File Map

| Action | File | Change |
|--------|------|--------|
| Modify | `src/pipeline/stages/base.py` | Add MLA fields to PipelineContext |
| Modify | `src/pipeline/storyboard.py` | Add `narration_en` to Scene |
| Modify | `src/pipeline/verifier.py` | Haystack includes `narration_en` |
| Modify | `src/pipeline/stages/tts.py` | Second-pass for secondary_locale |
| Modify | `src/pipeline/stages/compose.py` | Force `no_overlay` when `mla=True` |
| Modify | `src/pipeline/publish/metadata.py` | Add `LocalizedMeta` + `localizations` field |
| Modify | `src/pipeline/publish/stage.py` | Phase C includes localizations; add Phase D captions |
| Modify | `src/pipeline/publish/client.py` | Add `captions_insert` method |
| Modify | `src/pipeline/stages/direct.py` | Generate EN metadata in same call |
| Modify | `skills/produce/SKILL.md` | Note MLA flag, manual audio-track step |
| Modify | `CLAUDE.md` | Add MLA section to pipeline commands |

---

## Task 1: PipelineContext MLA fields + Scene narration_en

**Files:** `src/pipeline/stages/base.py`, `src/pipeline/storyboard.py`
**Tests:** `tests/unit/test_base.py`, `tests/unit/test_storyboard.py`

### Step 1 — Failing tests

In `tests/unit/test_base.py`, add:
```python
def test_mla_fields_roundtrip(tmp_path):
    ctx = PipelineContext(
        project_id=1, source_url="x", locale="zh-TW", work_dir=tmp_path,
        mla=True, secondary_locale="en",
        captions_uploaded={"zh-TW": "cap_abc", "en": "cap_def"},
    )
    data = ctx.to_dict()
    assert data["mla"] is True
    assert data["secondary_locale"] == "en"
    assert data["captions_uploaded"] == {"zh-TW": "cap_abc", "en": "cap_def"}
    ctx2 = PipelineContext.from_dict(data)
    assert ctx2.mla is True
    assert ctx2.captions_uploaded == {"zh-TW": "cap_abc", "en": "cap_def"}
```

In `tests/unit/test_storyboard.py`, add:
```python
def test_scene_narration_en_optional():
    from pipeline.storyboard import Scene
    s = Scene(id="s1", section="hook", narration="你好", narration_est_sec=2.0,
              visual={"type": "text_card", "text": "hi"})
    assert s.narration_en is None

def test_scene_narration_en_roundtrips():
    from pipeline.storyboard import Scene, Storyboard
    import json, tempfile, pathlib
    s = Scene(id="s1", section="hook", narration="你好", narration_est_sec=2.0,
              visual={"type": "text_card", "text": "hi"}, narration_en="Hello")
    sb = Storyboard(scenes=[s])
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "sb.json"
        sb.save(p)
        sb2 = Storyboard.load(p)
    assert sb2.scenes[0].narration_en == "Hello"
```

### Step 2 — Implementation

In `src/pipeline/stages/base.py`, add to PipelineContext after `preferred_variant`:
```python
# MLA (Multi-Language Audio)
mla: bool = False
secondary_locale: str | None = None
secondary_voice_id: str | None = None
secondary_narration_path: Path | None = None
secondary_subtitle_path: Path | None = None
captions_uploaded: dict[str, str] = field(default_factory=dict)
```

Add to `to_dict`/`from_dict` serialization (follow the pattern of `preferred_variant`).

In `src/pipeline/storyboard.py`, add to `Scene`:
```python
narration_en: str | None = None
```

---

## Task 2: Verifier haystack includes narration_en

**Files:** `src/pipeline/verifier.py`
**Tests:** `tests/unit/test_verifier.py`

### Step 1 — Failing test

```python
def test_verbatim_line_found_in_narration_en():
    from pipeline.explainer import Manifest
    from pipeline.verifier import run_auto_checks
    manifest = Manifest(intent="video", verbatim_lines=["english phrase"])
    storyboard = {"scenes": [
        {"id": "s1", "narration": "中文旁白", "narration_en": "english phrase", "visual": {}}
    ]}
    result = run_auto_checks(manifest, storyboard)
    line = next(i for i in result.items if i.item_id == "verbatim_line:0")
    assert line.status == "used"
```

### Step 2 — Implementation

In `verifier.py::_haystack_for_lines`, add `narration_en` to parts:
```python
parts.append(scene.get("narration_en", "") or "")
```

---

## Task 3: TTS stage — secondary locale pass

**Files:** `src/pipeline/stages/tts.py`
**Tests:** `tests/unit/test_tts.py`

### Design

After primary TTS completes, if `ctx.secondary_locale` is set:
1. Collect `narration_en` from each scene (falls back to empty string with a warning).
2. Run the same TTS engine resolution for `secondary_locale`/`secondary_voice_id`.
3. Produce `narration_en.mp3` + `subtitles_en.srt` in `audio/`.
4. Warn (log) for any scene where EN segment duration > zh-TW segment duration × 1.15.
5. Set `ctx.secondary_narration_path` and `ctx.secondary_subtitle_path`.

### Step 1 — Failing test

```python
def test_tts_produces_secondary_audio_when_mla(tmp_path, monkeypatch):
    """When mla=True and secondary_locale set, TTS writes secondary narration."""
    # ... setup ctx with mla=True, secondary_locale="en",
    # ... scenes with narration_en populated
    # monkeypatch TTS engine
    # assert ctx.secondary_narration_path is not None
    # assert ctx.secondary_narration_path.exists()
```

(Full test body follows the pattern of existing TTS tests.)

---

## Task 4: Compose — force no_overlay when mla=True + single-audio assertion

**Files:** `src/pipeline/stages/compose.py`
**Tests:** `tests/unit/test_compose_v2.py`

One-liner guard at the top of `_compose_from_storyboard`:
```python
if ctx.mla:
    ctx.preferred_variant = "no_overlay"
```

### Failing tests

```python
def test_compose_forces_no_overlay_when_mla(monkeypatch, tmp_path):
    # ctx.mla = True, ctx.preferred_variant = "subtitles"
    # After compose, ctx.preferred_variant == "no_overlay"
    # final_video_path points to *_no_overlay.mp4

def test_compose_mla_final_has_single_audio_stream(monkeypatch, tmp_path):
    # Full compose run with mla=True
    # ffprobe final_video_path → assert exactly 1 audio stream
    # Ensures secondary .mp3 is NOT muxed into the video
```

---

## Task 5: Metadata model + DirectStage dual metadata

**Files:** `src/pipeline/publish/metadata.py`, `src/pipeline/stages/direct.py`
**Tests:** `tests/unit/test_metadata.py`, `tests/unit/test_direct.py`

### metadata.py changes

```python
class LocalizedMeta(BaseModel):
    title: str = Field(max_length=100)
    description: str = Field(max_length=5000)

class Metadata(BaseModel):
    ...
    localizations: dict[str, LocalizedMeta] = Field(default_factory=dict)
```

### direct.py changes

When `ctx.mla=True`, append to Claude prompt:
```
Also produce English metadata in a "localizations.en" key:
{
  "localizations": {
    "en": { "title": "...", "description": "..." }
  }
}
```

Merge into `metadata.json` output.

**Also update the JSON schema** at `direct.py:324–334` (where `default_audio_language` and other top-level keys are declared) to include `localizations` as an optional object with `en.title` and `en.description`. Without the schema change, structured output validation will reject the EN metadata block.

### Failing tests

```python
def test_metadata_localizations_roundtrip():
    m = Metadata(title="T", description="D", tags=[], category_id=22,
                 default_language="zh-TW", default_audio_language="zh-TW",
                 localizations={"en": LocalizedMeta(title="T_en", description="D_en")})
    data = m.model_dump()
    m2 = Metadata(**data)
    assert m2.localizations["en"].title == "T_en"

def test_metadata_empty_localizations_allowed():
    m = Metadata(title="T", description="D", tags=[], category_id=22,
                 default_language="zh-TW", default_audio_language="zh-TW")
    assert m.localizations == {}
```

---

## Task 6: Publish Phase C + Phase D

**Files:** `src/pipeline/publish/client.py`, `src/pipeline/publish/stage.py`
**Tests:** `tests/integration/test_publish.py` (or new `test_publish_mla.py`)

### client.py — add captions_insert

```python
def captions_insert(
    self,
    *,
    video_id: str,
    language: str,
    name: str,
    srt_path: Path,
) -> str:
    """Upload an SRT caption track. Returns the YouTube caption_id."""
    # Multipart upload to /upload/youtube/v3/captions
    # Do NOT pass sync= parameter — it is deprecated (API docs confirmed 2026-05-04)
    # Quota cost: 400 units per call
    ...
    return caption_id
```

### stage.py — Phase C includes localizations

Update `_phase_c_disclosure`:
```python
def _phase_c_disclosure(self, client, ctx, metadata):
    if ctx.disclosure_set:
        return
    body = {
        "id": ctx.youtube_video_id,
        "status": {"containsSyntheticMedia": ...},
    }
    part = "status"
    if metadata.localizations:
        body["localizations"] = {
            lang: loc.model_dump()
            for lang, loc in metadata.localizations.items()
        }
        part = "status,localizations"
    client.videos_update(video_id=ctx.youtube_video_id, part=part, body=body)
    ctx.disclosure_set = True
    ctx.save()
```

### stage.py — Phase D captions

```python
def _phase_d_captions(self, client, ctx):
    """Upload SRT files for all locales. Idempotent via caption_id tracking."""
    tracks = [
        (ctx.locale, ctx.subtitle_path),
    ]
    if ctx.secondary_locale and ctx.secondary_subtitle_path:
        tracks.append((ctx.secondary_locale, ctx.secondary_subtitle_path))

    for locale, srt_path in tracks:
        if locale in ctx.captions_uploaded:
            logger.info("publish.phase_d.skipped", locale=locale)
            continue
        if not srt_path or not srt_path.exists():
            logger.warning("publish.phase_d.srt_missing", locale=locale)
            continue
        caption_id = client.captions_insert(
            video_id=ctx.youtube_video_id,
            language=locale,
            name=f"Subtitles ({locale})",
            srt_path=srt_path,
        )
        ctx.captions_uploaded[locale] = caption_id
        ctx.save()
        logger.info("publish.phase_d.complete", locale=locale, caption_id=caption_id)
```

Add to main `run()` after Phase C:
```python
self._phase_d_captions(client, ctx)
```

And after publish completes, if `ctx.mla`:
```python
typer.echo(
    "\n⚠ MLA manual step required:\n"
    "  YouTube Studio → Content → [this video] → Audio tab\n"
    f"  Upload: {ctx.secondary_narration_path}\n"
    "  Set language: English"
)
```

---

## Task 7: skills/produce/SKILL.md + skills/storyboard/SKILL.md + CLAUDE.md

**Files:** `skills/produce/SKILL.md`, `skills/storyboard/SKILL.md`, `CLAUDE.md`

### storyboard/SKILL.md — MLA narration_en authoring instruction

Append to the "Manifest constraints" section:

```markdown
### MLA projects (mla=True in context.json)

When `ctx.mla=True`, every scene must also have a `narration_en` field:
- Write EN narration for the same scene concept, targeting the **same duration** as `narration` (zh-TW)
- EN narration is NOT a translation — it is the same idea written naturally in English
- Duration guidance: count ~2.5 words/second for EN TTS. If zh-TW scene is 8s, aim for ~20 EN words.
- Flag per-scene if EN word count implies >1.15× the zh-TW duration — TTS will warn on these
- Total EN duration must be within ±2s of total zh-TW duration. Adjust scene-level EN text until this holds.
```

### produce/SKILL.md — MLA flag and manual step

Add to produce skill's "Create project + copy explainer in" block:
```bash
# For MLA projects, set secondary locale:
# ctx.mla=True, ctx.secondary_locale="en" — set these in context.json after project creation
uv run python3 -c "
from pathlib import Path; from pipeline.stages.base import PipelineContext
ctx = PipelineContext.load(Path('output/projects/$PROJECT_ID/context.json'))
ctx.mla = True; ctx.secondary_locale = 'en'; ctx.save()
"
```

Add to CLAUDE.md under Pipeline Commands:
```bash
# MLA (multi-language audio) — set before TTS
uv run pipeline produce <url/path> --locale zh-TW --mla --secondary-locale en
# After publish: go to YouTube Studio → Audio tab → upload secondary_narration_path manually
```

---

## Scope boundary

| Item | In scope |
|------|----------|
| zh-TW TTS | ✅ existing |
| EN TTS (secondary pass) | ✅ Task 3 |
| No burned subtitles (no_overlay variant) | ✅ Task 4 |
| Single-audio-stream assertion in compose | ✅ Task 4 |
| zh-TW subtitle upload (captions.insert) | ✅ Task 6 |
| EN subtitle upload (captions.insert) | ✅ Task 6 |
| zh-TW + EN metadata (localizations) | ✅ Task 5–6 |
| MLA audio upload to YouTube | ❌ Manual — YouTube Studio only (no API) |
| EN narration_en in storyboard | ✅ Task 1 |
| Verifier EN verbatim check | ✅ Task 2 |
| narration_en authoring instruction in skills | ✅ Task 7 |

## Quota impact

Per MLA publish: `videos.insert` (1600) + `thumbnails.set` (50) + `videos.update` (50) + `captions.insert` × 2 (800) = **~2500 units**. At 10,000 daily quota: ~4 full MLA publishes/day. Batch-publishing multiple videos in one day will hit quota. Plan for quota increase request if this becomes regular workflow.
