# Highlight Extraction + Gallery System Design

**Date:** 2026-04-23
**Status:** Approved

## Problem

The `/produce` skill currently forces the agent to read ~50 keyframe images per video to identify usable source clips (token-expensive, slow). Generated images accumulate per-project but are never reused across videos (wasteful). There is no way to consult stock footage before paying for AI generation.

## Scope

Three new capabilities that bolt onto the existing produce flow without changing pipeline stages:

1. **Highlight Extractor** — signal-scored clip manifest replaces raw keyframe scanning
2. **Gallery System** — tiered asset lookup: local pool → stock APIs → generate new
3. **Evaluator sub-agents** — two new QA checkpoints (ClipSelector, AssetEvaluator) following the existing GAN pattern

## Future Enhancements (out of scope for this build)

- `GalleryStage` as a formal `PipelineStage` (pre-materializes assets before storyboard)
- Semantic embedding search on gallery index (sentence-transformers)
- Shared `evaluator_persona.md` as single source of truth for all evaluator sub-agents

---

## Component 1: Highlight Extractor

### New file: `src/pipeline/utils/highlight_extractor.py`

### Processing pipeline

**Step 1 — Signal scoring (pure FFmpeg, $0 cost)**

Per-5-second window, three signals:

| Signal | Method | Weight |
|---|---|---|
| `frame_diff_score` | ffprobe `signalstats` mean absolute difference | 0.4 |
| `audio_rms_score` | ffprobe `astats` RMS level | 0.3 |
| `keyword_score` | sliding transcript window, action-word count | 0.3 |

Action-word vocabulary (extensible):
```python
ACTION_WORDS = [
    "shot", "arrest", "fight", "crash", "verdict", "confronted",
    "screaming", "weapon", "chase", "attack", "guilty", "explosion",
    "threatening", "fleeing", "struggle", "collision", "fired"
]
```

`combined_score = 0.4*frame_diff + 0.3*audio_rms + 0.3*keyword_score` (all normalized 0–1)

**Step 2 — Candidate selection**

- Sort by `combined_score` descending
- Take top-10, enforce minimum 15s spacing (prevents clustering around one intense moment)

**Step 3 — Caption provider (pluggable)**

```python
class CaptionProvider(Protocol):
    def caption(self, frame_path: Path) -> str | None: ...

class NullCaptionProvider:
    """Default: no API call, caption field is null."""
    def caption(self, frame_path: Path) -> str | None:
        return None
```

Future providers drop in without changing the manifest format:
- `GptVisionCaptionProvider` — uses existing `openai` SDK, `gpt-4o-mini`, ~$0.001/video
- `GeminiCaptionProvider` — uses `google-generativeai`, ~$0.0003/video

**Step 4 — Reject filter**

With `NullCaptionProvider`, no reject filter runs (caption is null, `usable=true` for all top-10).
When a caption provider is active, reject if caption matches:
`["talking head at desk", "anchor", "blank screen", "empty room", "news lower third"]`

### Output: `source/clip_manifest.json`

```json
{
  "video_id": "1776356443",
  "duration_sec": 847,
  "caption_provider": "null",
  "candidates": [
    {
      "timestamp_sec": 45,
      "combined_score": 0.87,
      "frame_diff": 0.91,
      "audio_rms": 0.72,
      "keyword_score": 0.95,
      "caption": null,
      "keyframe_path": "source/keyframes/keyframe_0004.jpg",
      "usable": true
    }
  ],
  "rejected": []
}
```

The agent reads `clip_manifest.json` (JSON, ~2K tokens) and then reads only the 10 `keyframe_path` images for approved candidates — down from ~50 images in the current flow.

### Produce skill change (Step 1b)

`extract_highlights()` internally calls `extract_keyframes()` first (so keyframes are still extracted for the manifest's `keyframe_path` references), then applies signal scoring on top. The old standalone `extract_keyframes` + `detect_scene_changes` calls in Step 1b are replaced by this single call.

Replace the current keyframe scanning block with:

```bash
uv run python3 -c "
from pipeline.utils.highlight_extractor import extract_highlights
from pathlib import Path
manifest = extract_highlights(
    Path('output/projects/<ID>/source/video.mp4'),
    transcript_path=Path('output/projects/<ID>/source/transcript.json'),
)
print(f'Highlights: {len(manifest[\"candidates\"])} candidates')
for c in manifest['candidates']:
    score = c['combined_score']
    caption = c['caption'] or '(no caption)'
    print(f'  {c[\"timestamp_sec\"]}s score={score:.2f}: {caption}')
"
```

Then read each `keyframe_path` image to make clip decisions.

---

## Component 2: Gallery System

### Directory structure

```
output/
  gallery/
    gallery_index.json      # global index, all entries
    images/                 # generated + downloaded images
    clips/                  # downloaded video clips from stock APIs
```

`output/gallery/` is gitignored and persists across all projects.

### Index schema: `output/gallery/gallery_index.json`

```json
{
  "version": 1,
  "entries": [
    {
      "id": "a3f9c1",
      "path": "output/gallery/images/a3f9c1.png",
      "type": "image",
      "origin": "dalle",
      "prompt": "flat minimalist illustration of US courtroom, warm lighting",
      "tags": ["courtroom", "legal", "interior"],
      "niche": ["bodycam", "courtroom"],
      "created_at": "2026-04-23"
    },
    {
      "id": "b72de4",
      "path": "output/gallery/clips/b72de4.mp4",
      "type": "clip",
      "origin": "pixabay",
      "query": "police lights night",
      "tags": ["police", "night", "lights"],
      "niche": ["bodycam"],
      "created_at": "2026-04-23"
    }
  ]
}
```

### New file: `src/pipeline/utils/gallery.py`

### Tiered lookup

```
Tier 1 — Local gallery:
  Keyword match against tags + niche filter
  Match score = (matching tags / query terms) — threshold 0.6
  Hit → return entry path, done

Tier 2 — Stock APIs:
  Pexels API (photos): GET https://api.pexels.com/v1/search?query=<q>&per_page=3
  Pixabay API (video): GET https://pixabay.com/api/videos/?q=<q>&per_page=3
  Download best result → save to output/gallery/images/ or clips/
  Add to gallery_index.json
  Cache: keyed by query hash, TTL 30 days (skip download if cached)

Tier 3 — Signal to generate:
  Return {"tier": "generate", "suggested_prompt": "<enriched prompt>"}
  Agent runs existing DALL-E flow
  Compose stage saves result back to gallery_index.json
```

### CLI command

```bash
uv run pipeline gallery search "<query>" [--niche bodycam] [--type image|clip]
```

Returns ranked results with tier label. Example:

```
tier=local  score=0.82  output/gallery/images/a3f9c1.png  tags=[courtroom,legal]
tier=pexels score=0.71  output/gallery/images/d3e9f2.jpg  query="courtroom hallway"
tier=generate           suggested_prompt="flat minimalist courtroom exterior, dusk"
```

### API keys

Add to `.env` (placeholders — operator fills in):

```
PEXELS_API_KEY=your_key_here
PIXABAY_API_KEY=your_key_here
```

Both free tiers: Pexels 200 req/hr, Pixabay 100 req/min. No cost within normal production volume.

### Gallery write-back (compose stage)

When the compose stage renders a `generated_image` scene, it appends the entry to `gallery_index.json` with origin=`dalle`, prompt, tags derived from scene narration keywords, and niche from `PipelineContext`.

---

## Component 3: Evaluator Sub-agents

Two new checkpoints in the produce skill, following the existing GAN pattern (Steps 2b, 4b, 7b).

### Step 1c — ClipSelector sub-agent

Runs after highlight extraction (Step 1b), before knowledge analysis (Step 2).

**Dispatch:**
```python
Agent(
  subagent_type="general-purpose",
  description="Validate highlight candidates for clip usability",
  prompt="""You are the CLIP SELECTOR — an independent QA agent.

Read: output/projects/<ID>/source/clip_manifest.json
Also read each keyframe image listed in candidates[].keyframe_path

For each candidate, apply the quality rubric:

PASS criteria (all must be true):
- Keyframe shows clear visual action or setting
- combined_score >= 0.5
- No sensitive content (explicit violence close-ups, identifiable private individuals in harmful context)

FAIL criteria (any triggers rejection):
- Keyframe shows only: news anchor at desk, blank screen, static title card, empty room
- combined_score < 0.3
- Near-duplicate: another candidate within 10s covers identical content

Output:
- approved: list of timestamp_sec values cleared for storyboard use
- rejected: list with reason per timestamp
- summary: "X of Y candidates approved"

Under 150 words. Be critical."""
)
```

If 0 candidates approved: warn user, continue with designed visuals only.

### Step 3b — AssetEvaluator sub-agent

Runs after gallery lookup, before storyboard creation (Step 4).

The agent creates `assets/manifest.json` by running `pipeline gallery search` once per planned scene section (using concept keywords extracted from `knowledge.json`), accumulating results, and writing the manifest. The AssetEvaluator then validates that accumulated manifest.

**Dispatch:**
```python
Agent(
  subagent_type="general-purpose",
  description="Validate gallery/stock assets against scene intent",
  prompt="""You are the ASSET EVALUATOR — an independent QA agent.

Read:
1. output/projects/<ID>/assets/manifest.json  (proposed assets per scene)
2. output/projects/<ID>/knowledge.json         (what the video is about)

For each proposed asset:
1. Relevance (1-5): does it illustrate the scene it's assigned to?
2. Quality (PASS/FAIL): resolution adequate? No watermarks? No obvious AI artifacts on faces?
3. Tone match (PASS/FAIL): does the visual mood match the narrative moment?

Hard rejects:
- Watermarked images
- AI photorealism on human faces
- Asset from mismatched niche (e.g. cheerful stock photo in a crime video)

Output per asset: APPROVED / REPLACE (with alternative search query) / GENERATE
Overall verdict: PASS (>80% approved) or NEEDS_WORK

Under 200 words. Be critical."""
)
```

If NEEDS_WORK: fix flagged assets before presenting storyboard to user.

---

## Data Flow Summary

```
acquire (existing)
  → source/video.mp4, source/transcript.json

Step 1b: extract_highlights()  [new]
  → source/clip_manifest.json  (10 scored candidates)

Step 1c: ClipSelector sub-agent  [new]
  → approved timestamp list

[knowledge analysis, human review — existing]

Step 3b: gallery search + AssetEvaluator  [new]
  → assets/manifest.json  (per-scene asset proposals)

[storyboard creation — existing, now references clip_manifest + assets/]

[render, post-render eval — existing]

compose (existing, extended)
  → gallery_index.json write-back for any new DALL-E images
```

---

## Error Handling

| Failure | Behaviour |
|---|---|
| ffprobe/signalstats unavailable | Fall back to scene-change timestamps only (existing behavior) |
| Transcript missing | keyword_score = 0 for all windows; signal scoring continues |
| Pexels/Pixabay API key missing | Skip tier 2 silently, go to tier 3 (generate) |
| Gallery index corrupted/missing | Rebuild empty index; all lookups hit tier 2+ |
| 0 clip candidates approved by ClipSelector | Warn user, produce continues with 0 clips (all designed visuals) |
| All gallery tiers fail | Return tier=generate with suggested prompt |

---

## Testing

| Test file | Coverage |
|---|---|
| `tests/unit/test_highlight_extractor.py` | Mock ffprobe; assert manifest shape, spacing enforcement, score normalization |
| `tests/unit/test_gallery.py` | Mock Pexels/Pixabay HTTP (httpx); assert tier fallthrough, index read/write round-trip, TTL cache |
| `tests/integration/test_highlight_extractor.py` | `@pytest.mark.integration` — real short video from fixtures, real ffprobe |

No new integration tests for evaluator sub-agents (prompt-driven, validated via produce runs).

## New Dependencies

| Package | Reason | Already present? |
|---|---|---|
| `httpx` | Pexels + Pixabay HTTP calls | Yes (Telegram notifier) |

No new packages required. `CaptionProvider` protocol is in-tree — future vision providers add their SDK dependency only when activated.
