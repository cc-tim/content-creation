# Produce Video (Agent-Driven)

Full pipeline from URL to video. The agent does the creative work (analysis, storyboard creation) directly in conversation — no separate API calls needed.

## Input

- **Arguments:** $ARGUMENTS (YouTube URL)
- If no URL provided, ask for one.
- Default locale: zh-TW (unless user specifies otherwise)

## Voice selection

- Default: the registry picks the locale default (edge-tts).
- Override with `--voice <id>` to use a cloned voice (e.g. `tim-zhtw`).
- List available voices: `uv run pipeline voice list`.
- To record a new voice, see `scripts/record_voice.md`.
- If the user has not said otherwise, always use the default voice.

## Process

### Step 1: Acquire

Download video and extract transcript:

```bash
uv run pipeline acquire --url "<URL>"
```

Note the project ID from the output. Then read the transcript:

```bash
uv run python3 -c "
import json
from pathlib import Path
data = json.loads(Path('output/projects/<ID>/source/transcript.json').read_text())
text = ' '.join(d['text'] for d in data)
print(text[:3000])
print(f'... ({len(text)} total chars)')
"
```

Also fetch metadata:
```bash
uv run yt-dlp --dump-json --no-download "<URL>" 2>/dev/null | uv run python3 -c "
import json, sys
d = json.load(sys.stdin)
print(f'Title: {d[\"title\"]}')
print(f'Channel: {d[\"channel\"]}')
print(f'Views: {d[\"view_count\"]:,}')
print(f'Duration: {d[\"duration\"]//60}m{d[\"duration\"]%60}s')
"
```

### Step 1b: Highlight extraction (clip confidence)

Extract signal-scored highlight candidates — replaces raw keyframe scanning:

```bash
uv run python3 -c "
from pipeline.utils.highlight_extractor import extract_highlights
from pathlib import Path
import json

manifest = extract_highlights(
    Path('output/projects/<ID>/source/video.mp4'),
    transcript_path=Path('output/projects/<ID>/source/transcript.json'),
)
Path('output/projects/<ID>/source/clip_manifest.json').write_text(
    json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8'
)
print(f'Highlights: {len(manifest[\"candidates\"])} candidates ({manifest[\"duration_sec\"]}s video)')
for c in manifest['candidates']:
    print(f'  {c[\"timestamp_sec\"]:>6.0f}s  score={c[\"combined_score\"]:.2f}  keyframe={c[\"keyframe_path\"]}')
"
```

**IMPORTANT:** Read each keyframe image listed in `clip_manifest.json` candidates (only those 10, not all keyframes) to understand what's visually at each timestamp before assigning clips in the storyboard.

To swap in vision captions later (reduces image-reading to zero): pass `caption_provider=GptVisionCaptionProvider(api_key=...)` to `extract_highlights()`.

### Step 1c: ClipSelector sub-agent (QA gate)

**Dispatch a ClipSelector sub-agent** to validate the highlight candidates before proceeding. Do NOT self-evaluate.

```python
Agent(
  subagent_type="general-purpose",
  description="Validate highlight candidates for clip usability",
  prompt="""You are the CLIP SELECTOR — an independent QA agent.

Read: output/projects/<ID>/source/clip_manifest.json
Also read each keyframe image listed in candidates[].keyframe_path

For each candidate, apply the quality rubric:

PASS criteria (all must be true):
- Keyframe shows clear visual action or recognizable setting (not a talking head or blank)
- combined_score >= 0.5
- No sensitive content (explicit violence close-ups, private individuals in harmful context)

FAIL criteria (any triggers rejection):
- Keyframe shows ONLY: news anchor at desk, blank screen, static title card, empty room
- combined_score < 0.3
- Near-duplicate: another candidate within 10s covers the same content

Output STRICTLY in this format:
approved: [<timestamp_sec>, ...]
rejected: [{"timestamp_sec": X, "reason": "..."}]
summary: "X of Y candidates approved"

Under 150 words. Be critical."""
)
```

If 0 candidates are approved: warn the user and continue — all scenes will use designed visuals.
Note the approved timestamps. Reference ONLY approved timestamps when writing `clip` visual types in the storyboard.

### Step 2: Analyze (agent-driven — YOU do this)

Read the full transcript and extract:

1. **Facts** — individual factual statements with IDs (f1, f2...), timestamps, tags
2. **Entities** — people, organizations, locations with IDs (e1, e2...)
3. **Timeline** — key events in chronological order, referencing fact IDs
4. **Context bridges** — cultural context the target locale audience needs

Save as knowledge.json using the Knowledge schema:
```bash
uv run python3 -c "
import json
from pathlib import Path
knowledge = <YOUR_KNOWLEDGE_DICT>
Path('output/projects/<ID>/knowledge.json').write_text(
    json.dumps(knowledge, indent=2, ensure_ascii=False), encoding='utf-8'
)
print('Saved knowledge.json')
"
```

Present the knowledge summary to the user. Show top facts, entities, context bridges.

### Step 2b: Knowledge Quality Evaluation (SUB-AGENT)

**Dispatch a separate evaluator sub-agent** using the Agent tool. Do NOT self-evaluate — the article's own f2 insight proves self-evaluation is unreliable.

```
Agent(
  subagent_type="general-purpose",
  description="Evaluate knowledge extraction quality",
  prompt="""You are a KNOWLEDGE EVALUATOR — an independent QA agent. Your job is to
critically assess whether a knowledge extraction is complete and accurate.

Read these two files:
1. Source article: output/projects/<ID>/source/article.txt (or source/transcript.json for YouTube)
2. Knowledge extraction: output/projects/<ID>/knowledge.json

Score each dimension 1-5 with specific evidence:

1. **Completeness** — Compare source to facts. List any major claims/arguments in the source
   that have NO corresponding fact entry. Missing facts = low score.
2. **Accuracy** — Do facts faithfully represent the source? Flag any distortions or exaggerations.
3. **Granularity** — Are facts atomic (one claim each)? Flag any that bundle multiple claims.
4. **Entity coverage** — List key people/orgs/tools mentioned in source. Flag any missing from entities.
5. **Context bridges** — For locale <LOCALE>: would a viewer unfamiliar with the source culture
   understand the topic? Flag missing bridges.

Be CRITICAL, not generous. A 5 means genuinely excellent. Most extractions deserve 3-4.

Output format:
- Scores table with evidence
- List of SPECIFIC facts that should be added (with suggested text)
- List of facts that should be corrected
- Overall verdict: PASS (all ≥ 3) or NEEDS_WORK (any ≤ 2)

Report in under 300 words."""
)
```

If the evaluator returns NEEDS_WORK, fix the issues before presenting to the user.
Show the user the evaluator scores alongside your knowledge summary.

Ask: "Anything to correct or add before I create the storyboard?"

### Step 3: Human review of knowledge

Wait for user feedback. Apply edits using /knowledge operations.
If user approves, proceed.

### Step 3b: Gallery lookup + AssetEvaluator sub-agent

Before writing the storyboard, consult the gallery for candidate assets per story section.

For each of the 6 story sections (hook, context, rising, climax, aftermath, analysis), run:

```bash
uv run pipeline gallery search "<section_concept_keywords>" --niche <niche> --type image
```

Example for a bodycam video with a courthouse climax scene:
```bash
uv run pipeline gallery search "courthouse verdict guilty" --niche bodycam --type image
```

Accumulate results and write `assets/manifest.json`:

```python
import json
from pathlib import Path

assets = {
    "hook": {"tier": "local", "path": "output/gallery/images/abc123.png", "tags": ["police", "night"]},
    "context": {"tier": "generate", "suggested_prompt": "flat minimalist map of US state borders"},
    # ... one entry per section
}
Path('output/projects/<ID>/assets').mkdir(parents=True, exist_ok=True)
Path('output/projects/<ID>/assets/manifest.json').write_text(
    json.dumps(assets, indent=2), encoding='utf-8'
)
```

Then **dispatch the AssetEvaluator sub-agent**:

```python
Agent(
  subagent_type="general-purpose",
  description="Validate gallery/stock assets against scene intent",
  prompt="""You are the ASSET EVALUATOR — an independent QA agent.

Read:
1. output/projects/<ID>/assets/manifest.json  (proposed assets per story section)
2. output/projects/<ID>/knowledge.json         (what the video is about)

For each proposed asset:
1. Relevance (1-5): does it illustrate its assigned section?
2. Quality (PASS/FAIL): resolution adequate? No watermarks? No AI faces?
3. Tone match (PASS/FAIL): does the visual mood match the narrative moment?

Hard rejects:
- Watermarked images
- AI photorealism on human faces
- Asset visually unrelated to the video topic

Output per asset: APPROVED / REPLACE (with alternative gallery search query) / GENERATE
Overall verdict: PASS (>80% approved) or NEEDS_WORK

Under 200 words. Be critical."""
)
```

If NEEDS_WORK: re-run gallery search with the suggested alternative queries, then re-evaluate. Fix before proceeding to storyboard.

Use the approved asset paths when setting `visual.type = "article_image"` with `visual.path` in storyboard scenes. Tier-3 (generate) sections will use `visual.type = "generated_image"` as usual.

### Step 4: Direct (agent-driven — YOU do this)

Create the storyboard directly based on the knowledge base:

1. Plan narrative arc (hook → context → rising → climax → aftermath → analysis)
2. Write narration text in target locale for each scene
3. Choose visual type per scene — IMPORTANT visual guidelines:
   - **Prefer designed visuals over clips** (text_card, slide, article_image, generated_image > clip)
   - Use clips ONLY for moments you're confident the source video visually matches the narration
   - Use **article_image** for scenes where a source article image directly illustrates the point (provide `path` to the local image file in `source/images/`)
   - Use slide for explaining concepts, structures, comparisons
   - Use text_card for key quotes, statistics, dramatic statements
   - Use generated_image for mood, transitions, scenes hard to show with clips or article images
   - Target: ~30% clips, ~70% designed visuals (article images count as designed)
4. Reference fact IDs for each scene
5. Add overlays where useful (title, namecard, text lower-thirds)
6. Keep each scene's narration concise — aim for 8-15 seconds per scene for good pacing

Save as storyboard.json and derive script.md:
```bash
uv run python3 -c "
import json
from pathlib import Path
from pipeline.storyboard import Storyboard
sb_data = <YOUR_STORYBOARD_DICT>
sb = Storyboard.from_dict(sb_data)
sb.save(Path('output/projects/<ID>/storyboard.json'))
script = sb.derive_script()
Path('output/projects/<ID>/script').mkdir(parents=True, exist_ok=True)
Path('output/projects/<ID>/script/script_<LOCALE>.md').write_text(script, encoding='utf-8')
print(f'Storyboard: {len(sb.scenes)} scenes, ~{sb.estimated_duration_sec():.0f}s')
print('Script derived')
"
```

### Step 4a: Start Scene Director (SUB-AGENT)

**Dispatch a separate Director sub-agent** to pick the most compelling intro
treatment for this specific video. The Director must read the whole context
(knowledge.json, draft storyboard, keyframes, article images if web source)
and propose TWO distinct candidate intros. You then present both to the user
and apply the one they pick. If the user already said which treatment they
want in their /produce arguments, skip the sub-agent and apply their choice
directly.

```
Agent(
  subagent_type="general-purpose",
  description="Pick best intro for this video",
  prompt="""You are the START SCENE DIRECTOR. Your job is to design the opening
scene (s1) of a short video so it grabs attention and sets up the story.

Read these files carefully — do not skim:
1. output/projects/<ID>/knowledge.json
2. output/projects/<ID>/storyboard.json
3. ls output/projects/<ID>/source/keyframes/ (YouTube sources)
4. ls output/projects/<ID>/source/images/ (web sources, if present)
5. .claude/commands/produce.md (visual guidelines)

Your output is TWO distinct candidate intro treatments. They should differ in
style — not two variants of the same idea. For each candidate provide:

- Name (e.g. "Kinetic stat slam", "Montage of reactions", "Quiet question")
- Rationale (1-2 sentences: why this opening suits THIS video's topic and tone)
- A concrete storyboard patch for s1:
  ```json
  {
    "id": "s1",
    "visual": { "type": "...", "...": "..." },
    "overlay": { "type": "...", "text": "..." },
    "compartment": null,
    "narration": "...",
    "narration_est_sec": 8
  }
  ```
- The visual type must be one of: generated_image, article_image, clip,
  text_card, slide. Do not invent new types.
- If you pick generated_image, write a concrete prompt in the visual.
- Do not put text overlays on text_card or slide visuals.
- Overlay types must be one of: title, namecard, text_top, text_left,
  text_emphasis. The legacy "text" type is banned.
- Never place overlays below y=0.70 (collides with subtitles).

Return STRICTLY in this format:

```
## Candidate A: <name>
Rationale: ...
Patch:
<json block>

## Candidate B: <name>
Rationale: ...
Patch:
<json block>
```

Be opinionated. Under 500 words."""
)
```

Present both candidates to the user. Ask which to apply. If they picked one up
front via /produce arguments, apply that one directly without asking.

Then patch `storyboard.json` with the chosen s1 block and re-save.

### Step 4b: Storyboard Quality Evaluation (SUB-AGENT)

**Dispatch a separate evaluator sub-agent.** The creator should never grade its own storyboard.

```
Agent(
  subagent_type="general-purpose",
  description="Evaluate storyboard quality",
  prompt="""You are a STORYBOARD EVALUATOR — an independent QA agent reviewing a video storyboard.
You did NOT create this storyboard. Your job is to find weaknesses.

Read these files:
1. Knowledge base: output/projects/<ID>/knowledge.json
2. Storyboard: output/projects/<ID>/storyboard.json
3. Available images: ls output/projects/<ID>/source/images/ (if web source)

Score each dimension 1-5 with specific evidence:

1. **Narrative arc** — Does the scene sequence build tension/interest?
   Hook grabs attention? Rising action escalates? Climax delivers? Ending resonates?
   Flag any scenes that feel out of order or anti-climactic.
2. **Pacing** — Check narration_est_sec per scene. Flag any < 8s (rushed) or > 18s (draggy).
   Calculate total duration — does it match target_duration_sec?
3. **Visual variety** — List visual types in order. Flag 3+ consecutive same type.
   What % are designed vs source clips? Target: ≥ 60% designed.
4. **Fact coverage** — Compare facts_ref across all scenes to knowledge.json facts.
   List facts NOT referenced by any scene. Are important facts orphaned?
5. **Locale adaptation** — Read narration text. Is it natural <LOCALE>?
   Flag any awkward translations, missing context bridges, or cultural mismatches.
6. **Article images** — (If web source) How many available images are used vs available?
   Are they assigned to scenes where they're contextually relevant?

**Anti-pattern checks (hard fail if any are true):**
- Any overlay with `type == "text"` (banned legacy type — collides with subtitles).
- Any text_* overlay applied to a text_card or slide visual (text-on-text is unreadable).
- Any scene where the opening shot (s1) is a plain text_card and no
  generated_image or article_image variant was considered.
- Any scene with a compartment whose `position == "bottom"` (collides with subs).
- Duration mismatch: storyboard total estimate vs target_duration_sec diverges
  by more than 15%.

Be CRITICAL. A great storyboard has no score below 3.

Output format:
- Scores table with evidence
- Top 3 specific improvements (e.g. "swap s5 visual to article_image", "split s12 — too long")
- Overall verdict: PASS (all ≥ 3) or NEEDS_WORK (any ≤ 2)

Report in under 400 words."""
)
```

If the evaluator returns NEEDS_WORK, fix the issues before presenting to the user.
Show the user the evaluator scores alongside your storyboard summary.

Present the storyboard summary. Ask: "Ready to render, or want to adjust anything?"

### Step 5: Human review of storyboard

Wait for user feedback. Apply edits using /storyboard operations.

### Step 6: Render

Run TTS + compose:
```bash
uv run pipeline produce --url "<URL>" --project-id <ID> --locale <LOCALE> --start-from tts --skip-review [--voice <voice-id>]
```

### Step 7: Post-render review

Check the output and verify visual quality:

```bash
ls -lh output/projects/<ID>/compose/final_*.mp4
ffprobe -v quiet -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 output/projects/<ID>/compose/final_*.mp4
```

Extract review frames from the final video to spot-check visual quality:
```bash
uv run python3 -c "
from pathlib import Path
from pipeline.utils.video_analysis import extract_review_frames
video = Path('output/projects/<ID>/compose/final_<LOCALE>.mp4')
review_dir = Path('output/projects/<ID>/compose/review_frames')
frames = extract_review_frames(video, review_dir, count=8)
for f in frames:
    print(f'{f[\"timestamp_sec\"]:.0f}s: {f[\"path\"]}')
"
```

**Read the review frames** to verify:
- Are text cards readable? Font size OK?
- Do clip segments show relevant footage?
- Are overlays visible and properly positioned?
- Is there visual variety across scenes?

### Step 7b: Render Quality Evaluation (SUB-AGENT)

**Dispatch a separate evaluator sub-agent** to review the rendered output with fresh eyes.

```
Agent(
  subagent_type="general-purpose",
  description="Evaluate rendered video quality",
  prompt="""You are a RENDER EVALUATOR — an independent QA agent reviewing a rendered video.

Extract and read 8 review frames from the final video:
```python
from pathlib import Path
from pipeline.utils.video_analysis import extract_review_frames
video = Path('output/projects/<ID>/compose/final_<LOCALE>.mp4')
review_dir = Path('output/projects/<ID>/compose/review_frames')
frames = extract_review_frames(video, review_dir, count=8)
```

Then read each frame image and the storyboard:
- Review frames: output/projects/<ID>/compose/review_frames/
- Storyboard: output/projects/<ID>/storyboard.json

Score each dimension 1-5 by actually looking at the frames:

1. **Text readability** — Can you read text on text_card/slide frames?
   Is font size adequate? Any cut-off text? Any encoding issues with CJK chars?
2. **Visual coherence** — Do the visuals match what the storyboard intended?
   Are article images relevant to their scenes? Any black/broken frames?
3. **Pacing** — Check video duration vs storyboard target_duration_sec.
   Are review frames spread across the video or clustered?
4. **Visual variety** — Looking at the 8 frames, do they look different from each other?
   Different colors, layouts, content? Or monotonous?
5. **Production quality** — Overall polish. Would this look professional on YouTube?
   Any amateur-looking elements?

Be CRITICAL. Flag specific frames by timestamp if there are problems.

**Anti-pattern checks (hard fail if any are true):**
- Any frame where overlay text overlaps the burned subtitles (lower 30%).
- Any frame where overlay is on a text_card or slide visual.
- Any scene with a compartment but no visible compartment in any review frame.
- Rendered duration diverges by more than 15% from storyboard.target_duration_sec.
- The s1 intro frame looks like a generic text_card with no visual hook —
  the Start Scene Director's choice should be visible.

Output format:
- Scores table with evidence from specific frames
- List of SPECIFIC fixes (e.g. "frame at 45s: text too small, increase font")
- Overall verdict: PASS (all ≥ 3 and zero anti-pattern hits) or NEEDS_WORK

Report in under 300 words."""
)
```

If the evaluator returns NEEDS_WORK, suggest specific storyboard edits and offer to re-render.

Suggest: play with mpv, generate shorts with /shorts, review storyboard with /storyboard.

## Important

- YOU do the analysis and storyboard creation directly — no API calls
- This means you can ask questions, the user guides in real-time, quality is higher
- You have full conversation context — use it for better creative decisions
- Always let the user review between stages
- Cost: $0 for analysis + storyboard (only TTS + compose cost compute time)

## Seeking more materials

Before creating the storyboard, actively seek additional context:
- Search the web for related news articles, background info, or expert analysis about the topic
- Look for additional data points, statistics, or context that would strengthen the narrative
- For complex topics (politics, science, history), verify key claims against reliable sources
- Add any new facts found to knowledge.json with `source: "enrichment"`
- This enrichment makes the knowledge layer more robust and enables better storytelling
- Tell the user what additional context you found and why it matters

## Evaluator sub-agent philosophy (GAN pattern)

This pipeline uses the GAN-inspired pattern from the article itself:
- **The main /produce agent is the GENERATOR** — creates knowledge, storyboard, narration
- **Sub-agents dispatched at Steps 2b, 4b, 7b are EVALUATORS** — independent QA with fresh context
- Self-evaluation is unreliable (the generator will praise its own mediocre work)
- Evaluators must be dispatched as SEPARATE agents (Agent tool) so they don't share the generator's context biases
- If an evaluator returns NEEDS_WORK, the generator MUST fix issues before presenting to the user
- The evaluator prompt should instruct it to be CRITICAL, not generous — default score is 3, not 5

## Visual design philosophy

- **Avoid "presentation mode"**: Too many consecutive slides/text_cards makes the video feel like a boring PowerPoint. Maximum 2 text-only scenes in a row.
- **generated_image is your friend**: When the OpenAI API key is available, use `generated_image` for conceptual scenes (moods, metaphors, abstract ideas). A relevant image with a text overlay is far more engaging than a slide with bullets.
- **article_image is the best visual for web sources**: Source article screenshots/diagrams are authentic and relevant. Use them liberally.
- **Overlays only on image-based visuals**: Never put overlays on text_card or slide — it creates unreadable text-on-text overlap. Use overlays on article_image, generated_image, clip, or still_frame.
- Clips should only be used when the source footage clearly matches the narration moment
- Each scene should be short (8-15s narration) for good pacing
- **Visual variety rule**: No 3+ consecutive same visual type. Alternate between image-based and text-based scenes.

### Visual type priority (when choosing for a scene):
1. `article_image` — if a source image directly illustrates the point
2. `generated_image` — for concepts, moods, metaphors (when API key available)
3. `slide` — for structured info (comparisons, lists, processes) — max 2 in a row
4. `text_card` — for key quotes, dramatic statements — use sparingly
5. `clip` — only with confirmed visual match from keyframe review

### Generated image style guidance:
- **AVOID photorealistic AI art** — it looks fake and generic ("AI slop")
- **PREFER simple illustration styles**: flat design, minimalist line art, clean vector style
- The storyboard `theme.image_style` is appended to every DALL-E prompt automatically
- Default style: "flat minimalist illustration, simple clean lines, limited color palette"
- Only use photorealistic for specific subjects that demand it (e.g., a 3D gallery room)
- When a generated image is used, add a **text overlay** on it — image + text > image alone

### Theme & intro:
- Set a coherent `theme` in the storyboard: background color, accent, text color, image style
- **Intro scene (s1) must be visually special** — use `generated_image` with a striking concept, NOT a boring text_card
- Avoid dark/dim color themes unless the topic demands it. Default to modern, clean, slightly warm palettes.
