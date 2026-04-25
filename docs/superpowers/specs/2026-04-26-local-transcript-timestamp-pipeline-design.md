# Local Transcript + Timestamp-Aware Pipeline Design

**Date:** 2026-04-26
**Status:** approved
**Scope:** ACQUIRE + ANALYZE stages only; no schema changes downstream

---

## Problem

Two inefficiencies in the current pipeline:

1. **Redundant work:** When a local transcript already exists (e.g. downloaded from YouTube manually, or from a previous run), the ACQUIRE stage re-fetches it from YouTube anyway. Same for local video files.

2. **Inaccurate clip timestamps:** ANALYZE receives only plain text (`ctx.transcript_text`). Claude infers fact timestamps as strings like `"M:SS"` from context clues. DIRECT uses these guesses to set `start_sec`/`end_sec` on `clip` visual scenes — but the values are unreliable.

The storyboard schema already has `start_sec`/`end_sec` on clip scenes. The fix is upstream: give ANALYZE precise float timestamps from the transcript file.

---

## Solution: Approach 2 — Local file flags + structured transcript to ANALYZE

Three files change. No PipelineContext fields added. No storyboard/knowledge schema changes.

### Architecture

```
CLI (cli.py)
  └── --transcript PATH, --video PATH on `produce`
        ↓
AcquireStage (acquire.py)
  └── local files → parse + copy instead of fetch/download
  └── writes source/transcript.json as [{"text", "start", "duration"}] (same shape as before)
        ↓
AnalyzeStage (analyze.py)
  └── loads ctx.transcript_path → structured data
  └── formats [0.08s–4.24s] text → Claude gets precise timestamps
  └── facts get accurate "timestamp" values
        ↓
DirectStage (unchanged)
  └── already outputs start_sec/end_sec on clip scenes — now accurate
```

---

## Component Changes

### 1. `src/pipeline/cli.py` — two new flags on `produce`

```
--transcript PATH   # .csv or .txt local transcript file (optional)
--video PATH        # local video file (.mp4, .mkv, etc.) (optional)
```

Both are independent — you can supply just one, or both. When omitted, the existing fetch/download runs as before.

Flags are passed to `AcquireStage` at construction time (not stored in `PipelineContext` — they're only relevant when ACQUIRE runs; `--start-from analyze` skips acquire entirely).

### 2. `src/pipeline/stages/acquire.py`

**New function: `parse_transcript_file(path: Path) -> tuple[str, list[dict]]`**

Returns `(full_text, raw_data)` — same shape as `extract_transcript()` today.

Supported formats:

| Format | Detection | Parsing |
|--------|-----------|---------|
| `.csv` | file extension | col 0 = display timestamp, col 1 = start_sec (float), col 2 = duration_sec (float), col 3 = text |
| `.txt` | file extension | `MM:SS text` per line; duration inferred as gap to next entry; last entry defaults to 2.0s |

Both formats filter blank-text rows and output `[{"text": str, "start": float, "duration": float}]` to `source/transcript.json`. The rest of the pipeline is unchanged.

**`AcquireStage.__init__`** gains two optional params:
```python
def __init__(self, local_transcript: Path | None = None, local_video: Path | None = None)
```

**`AcquireStage.run()` logic:**
```
if local_video:
    # copy to source/video.<ext> preserving original extension; yt-dlp always produces .mp4
    # so downstream compose expects .mp4 — copy and let FFmpeg handle non-mp4 at compose time
    shutil.copy2(local_video, source_dir / local_video.name)
    ctx.video_path = source_dir / local_video.name
else:
    # existing yt-dlp download (unchanged)

if local_transcript:
    full_text, raw_data = parse_transcript_file(local_transcript)
    write source/transcript.json
    ctx.transcript_path = ...
    ctx.transcript_text = full_text
else:
    # existing youtube-transcript-api / yt-dlp fallback (unchanged)
```

### 3. `src/pipeline/stages/analyze.py`

**`build_analysis_prompt()` gains `transcript_data: list[dict] | None = None`.**

When `transcript_data` is provided, replace the plain-text `TRANSCRIPT:` section with a timestamped table:

```
[0.08s–4.24s] Mrs. Henry, excuse me. You brought this case before the court.
[4.24s–9.68s] Well, I'm bringing my husband for child support.
[9.68s–13.04s] Uh he roughly pays about a thousand a month.
```

**Merging strategy:** consecutive entries are merged when the previous entry's text does not end with `.` `?` `!` or `…` (mid-sentence YouTube caption splits). The merged entry uses the first entry's `start` and the last entry's `start + duration` as its end. This reduces ~60% of entries while keeping timestamp accuracy to ±2 seconds — sufficient for 5–15s clip selection.

**`AnalyzeStage.run()` loads structured data before building the prompt:**

```python
transcript_data = None
if ctx.transcript_path and ctx.transcript_path.exists():
    raw = json.loads(ctx.transcript_path.read_text())
    if raw and isinstance(raw[0], dict) and "start" in raw[0]:
        transcript_data = [e for e in raw if e.get("text", "").strip()]

prompt = build_analysis_prompt(
    ctx.transcript_text, ctx.source_url, title,
    transcript_data=transcript_data,
)
```

**Backward compatibility:** existing projects without a structured `transcript.json` (or with an empty `start` field) fall back to plain text automatically.

---

## Cost Impact

| Item | Delta |
|------|-------|
| Token cost per video (ANALYZE) | +~$0.06 (20K chars × Sonnet input rate) |
| Time saved per video (no transcript fetch) | ~5–15s |
| Time saved per video (no video download, if local) | ~30–120s |

Within the existing $10/month Claude budget for ~100 videos ($6 total added vs $10 budget).

---

## Wiring: Orchestrator

The orchestrator instantiates `AcquireStage`. The `--transcript` and `--video` CLI values are passed through:

```python
AcquireStage(
    local_transcript=Path(transcript_flag) if transcript_flag else None,
    local_video=Path(video_flag) if video_flag else None,
)
```

Check `src/pipeline/orchestrator.py` for the exact instantiation point during implementation.

---

## Out of Scope

- Approach 3 (explicit source clip index in knowledge graph) — follow-up feature
- `.srt` / `.vtt` format support — add later if needed
- Modifying DIRECT, TTS, COMPOSE, or publish stages
- Changes to storyboard schema or knowledge schema

---

## Usage Examples

```bash
# Provide only transcript (video still downloaded from YouTube)
uv run pipeline produce --url "https://youtube.com/watch?v=..." --locale zh-TW \
  --transcript "data/my-video/transcript.csv"

# Provide both (fully offline ACQUIRE)
uv run pipeline produce --url "https://youtube.com/watch?v=..." --locale zh-TW \
  --transcript "data/my-video/transcript.csv" \
  --video "data/my-video/video.mp4"

# --url is still required for metadata (source attribution, knowledge graph source field)
# even when --video is provided
```

---

## Test Plan

- Unit: `parse_transcript_file()` handles .csv, .txt, blank rows, mid-sentence merging
- Unit: `build_analysis_prompt()` with `transcript_data` produces correctly formatted table
- Unit: `AnalyzeStage` falls back to plain text when `transcript_path` has no `start` field
- Integration: full `produce` run with `--transcript` flag, verify `knowledge.json` facts have accurate float timestamps
- Integration: full `produce` run with `--video` flag, verify video is not re-downloaded
