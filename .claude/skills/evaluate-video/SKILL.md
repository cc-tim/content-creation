---
name: evaluate-video
description: Evaluate whether a YouTube video is worth porting to zh-TW (or other locale). Score niche match, portability, recency, view velocity, and narrative quality. Use when asked "should we port this?", "is this worth doing?", or "evaluate this video".
version: 1.0.0
metadata:
  openclaw:
    requirements:
      binaries: [uv]
---

# Evaluate Video — Porting Candidate Scoring

## Input

YouTube URL (required). Optionally a target locale (default: zh-TW).

## Step 1 — Fetch metadata

```bash
cd /home/tim-huang/content-creation
uv run yt-dlp --dump-json --no-download "<URL>" 2>/dev/null | python3 -c "
import json, sys
d = json.load(sys.stdin)
print(f'Title:    {d[\"title\"]}')
print(f'Channel:  {d[\"channel\"]}')
print(f'Views:    {d[\"view_count\"]:,}')
print(f'Duration: {d[\"duration\"]//60}m{d[\"duration\"]%60}s')
print(f'Date:     {d.get(\"upload_date\",\"?\")}')
print(f'Tags:     {d.get(\"tags\",[])}')
"
```

## Step 2 — Score the opportunity

Score each dimension 1-5, then compute weighted total.

| Dimension | Weight | What to check |
|-----------|--------|---------------|
| **Gap ratio** | 30% | EN views / zh-TW views on same topic (>10:1 = high gap) |
| **Portability** | 25% | Universal emotions (justice/survival) > local politics |
| **Visual intensity** | 20% | Bodycam/dashcam/action > talking head |
| **Narrative completeness** | 15% | Clear arc with resolution > open-ended saga |
| **Recency** | 10% | <72h from publish = maximum virality window |

## Step 3 — Check the zh-TW gap

Search YouTube for zh-TW content on the same topic:
```bash
# Use web search to find zh-TW YouTube videos on the topic
# Compare view counts to estimate the gap ratio
```

## Step 4 — Verdict

Present:
- Scores table with evidence
- Weighted total (out of 5)
- **Verdict**: STRONG_BUY (>4.0) / BUY (3.0-4.0) / PASS (<3.0)
- One-line rationale

## Opportunity formula

```
Opportunity = (EN_views / target_locale_views) × portability_score
```

High opportunity = ratio > 10 with portability ≥ 3.
