---
name: evaluate-video
description: Evaluate whether a YouTube video is worth porting to a target locale. Scores niche match, portability, recency, view velocity, and narrative quality.
---

# Evaluate Video for Porting

Evaluate whether a YouTube video is worth porting to a target locale.

## Input

- **URL:** $ARGUMENTS (YouTube video URL)
- If no URL provided, ask the user for one.
- Default target locale: zh-TW (unless user specifies otherwise)

## Process

### Step 1: Check tools are available

Run `which yt-dlp` to check if yt-dlp is installed. If not, install it:
```bash
pip install yt-dlp youtube-transcript-api
```

### Step 2: Fetch metadata

```bash
yt-dlp --dump-json --no-download "<URL>"
```

Extract and note:
- Title
- Channel name
- View count
- Upload date
- Duration (seconds)
- Tags / categories
- Description (first 500 chars)

### Step 3: Fetch transcript

Try youtube-transcript-api first (faster, lighter):
```bash
python3 -c "
from youtube_transcript_api import YouTubeTranscriptApi
api = YouTubeTranscriptApi()
transcript = api.fetch('<VIDEO_ID>', languages=['en'])
for entry in transcript:
    print(entry.text)
"
```

If that fails, fall back to yt-dlp subtitles:
```bash
yt-dlp --write-auto-sub --sub-lang en --skip-download --output "/tmp/eval_%(id)s" "<URL>"
```
Then read the downloaded subtitle file.

### Step 4: Evaluate against porting criteria

Score each criterion and give a SHORT explanation:

**1. Niche Match** (PASS / FAIL)
Target niches by locale:
- zh-TW: US bodycam, court/legal drama, scam exposes
- ja-JP: True crime deep dives, disaster/survival
- es-MX: Suspense narratives

Does the video fit a target niche? Check title, tags, and transcript content.

**2. Self-Contained Story** (PASS / FAIL)
- Is it a standalone story with beginning, middle, end?
- Red flags: "Part 2", "Episode X", "continued from", references to previous videos
- Check transcript for resolution/conclusion indicators

**3. Duration Sweet Spot** (PASS / FAIL)
- 8-25 minutes source = ideal (produces 12-18 min ported video)
- <5 min = too thin, >40 min = too expensive to process

**4. Recency** (PASS / WARN / FAIL)
- Published <3 days ago = PASS (within porting window)
- 3-7 days = WARN (tight but doable)
- >7 days = FAIL for trending play (may still work for evergreen)

**5. View Velocity** (PASS / WARN / FAIL)
- Calculate views/day since publish
- >50K views/day = high signal
- 10K-50K = moderate
- <10K = low (unless niche is small)

**6. Visual Style** (from transcript/description clues)
- Bodycam/dashcam footage = HIGH portability (universal, no faces to worry about)
- News footage / documentary = MEDIUM
- Talking head / reaction = LOW (personality-dependent, hard to port)

**7. Cultural Portability** (PASS / WARN / FAIL)
- Universal themes (justice, survival, crime, scam) = PASS
- US-specific but explainable (legal system, geography) = WARN (needs context bridges)
- Hyper-local (local politics, sports, inside jokes) = FAIL

**8. Narrative Quality** (from transcript)
- Does the transcript have clear dramatic tension?
- Is there a hook moment that can open the video?
- Are there identifiable story beats (inciting incident → escalation → climax → resolution)?

### Step 5: Gap check (if YouTube Data API key available)

If `PIPELINE_YOUTUBE_API_KEY` is set in environment or `.env`:
- Search YouTube for the same topic in the target locale
- Compare view counts
- Calculate opportunity ratio (EN views / target locale views)

If no API key, skip this step and note it.

### Step 6: Output verdict

Format the output as:

```
## Evaluation: [Video Title]

**URL:** [url]
**Channel:** [channel] | **Views:** [views] | **Published:** [date] | **Duration:** [duration]
**Target locale:** [locale]

### Criteria Scorecard
| Criterion | Result | Notes |
|-----------|--------|-------|
| Niche match | PASS/FAIL | ... |
| Self-contained | PASS/FAIL | ... |
| Duration | PASS/FAIL | ... |
| Recency | PASS/WARN/FAIL | ... |
| View velocity | PASS/WARN/FAIL | ... |
| Visual style | HIGH/MED/LOW | ... |
| Cultural portability | PASS/WARN/FAIL | ... |
| Narrative quality | STRONG/MODERATE/WEAK | ... |

### Opportunity gap
[Gap ratio if available, or "API key not configured — skip"]

### Verdict: PORT / MAYBE / SKIP
[1-2 sentence reasoning]

### If porting — key adaptation notes
- [What cultural context needs to be added for target audience]
- [Suggested hook moment from transcript]
- [Any risks or concerns]
```

## Important rules

- Do NOT download the actual video file. Metadata + transcript only.
- Clean up any temp files after evaluation.
- If transcript is unavailable (no subs, no auto-subs), note this as a WARN — the video can still be ported using Whisper, but it adds processing time.
- Be honest in the verdict. A SKIP saves more time than a bad port.
- If verdict is PORT, suggest: "Run `/produce <URL>` to start the full pipeline."
