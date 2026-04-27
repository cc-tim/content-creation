# Scene Update

Handle wording enhancements, narration edits, and targeted scene rebuilds.

## Input

- **Arguments:** $ARGUMENTS
- Formats: `<project-id> <scene-id>`, or infer from conversation context.

---

## Autonomy contract

**Once the user approves the wording changes, execute the full rebuild chain automatically — no further confirmation needed.**

The user only wants to review the final video output. Do not stop mid-chain to ask "should I also regenerate the audio?" or "want me to rescene now?" — if the change type requires it, do it.

The only gates where you pause for human input:
1. Before proposing wording changes (so they can approve the text)
2. If leftover variant files exist and need cleanup (ask once, then act)
3. If something fails unexpectedly

---

## Step 1 — Classify the change

Before touching anything, determine what type of change is being made:

| Change type | Full chain |
|-------------|-----------|
| Subtitle text only (no audio change) | Edit SRT → `compose reburn` |
| Narration text (audio changes) | Edit storyboard → synthesize audio for scene → rechain timings → rebuild SRT → invalidate scene cache → `compose rescene` |
| Visual / overlay only | Edit storyboard → invalidate scene cache → `compose rescene` |
| Theme / font / color | Edit storyboard → `compose reburn` |

**Never run more than the minimum.** Only the changed scene gets re-synthesized and re-rendered — all others stay cached.

---

## Step 2 — Wording enhancement: read the whole scene first

When the task is enhancing or fixing wording, **never do a mechanical word swap on the target sentence alone.**

Read before writing:
1. **Full scene narration** — what is the scene trying to accomplish emotionally? What's the arc (opening label → concrete image → felt conclusion)?
2. **Adjacent scenes** — what vocabulary or metaphors have already been introduced? What registers are consistent?
3. **Vocabulary threads** — look for recurring words across scenes (e.g., 接偏了 / 沒接準 / 感受落空了 / 沒接住). New wording should weave into the thread, not break it.
4. **Storytelling structure** — does the target sentence set up something later in the scene? Does it echo a closing line? Changing it may require changing other sentences to preserve the arc.

**What to avoid:**
- Replacing abstract terms with other abstract terms
- Mechanical synonym swaps that don't change the register
- Changing the opening label without checking if the scene's closing line still resolves it

**What to aim for:**
- Zero-decoding zh-TW: the listener should feel it before they parse it
- Concrete sensory language over clinical compounds (情感錯配 → 接偏了; 情感伸手是危險的 → 哭了，也沒人接住)
- If one sentence changes, check whether another sentence in the same scene should change to maintain coherence

**You may — and often should — change multiple sentences.** Show your reasoning for each change before editing.

---

## Step 3 — Variant cleanup check

Before rebuilding, check for leftover variant files:

```bash
python3 -c "
import json
from pathlib import Path
ctx = json.load(open('output/projects/<ID>/context.json'))
preferred = ctx.get('preferred_variant')
locale = ctx.get('locale', 'zh-TW')
compose_dir = Path('output/projects/<ID>/compose')
finals = list(compose_dir.glob(f'final_{locale}*.mp4'))
print(f'preferred_variant: {preferred}')
print('Finals on disk:', [f.name for f in finals])
"
```

If `preferred_variant` is set and other `final_*.mp4` files still exist on disk, ask once:

> "Preferred variant is locked to `{variant}`. I also see `{others}` still on disk — want me to clean them up?"

Then act on the answer and continue immediately.

---

## Step 4 — Execute the full rebuild chain

### Narration text changed
```python
# Run as a single inline script — do not break into manual steps
import asyncio, json
from pathlib import Path
from pipeline.stages.base import PipelineContext
from pipeline.voices.registry import VoiceRegistry
from pipeline.stages.tts import _get_audio_duration_ms, _build_subtitle_entries
from pipeline.utils.srt import write_srt
from pipeline.storyboard import Storyboard

work_dir = Path("output/projects/<ID>")
ctx = PipelineContext.load(work_dir / "context.json")
seg_index = <SCENE_INDEX>  # 0-based: s1=0, s2=1, s3=2, ...

# 1. Update storyboard narration
# (done before running this script)

# 2. Re-synthesize audio for the changed scene
reg = VoiceRegistry(Path("voices"))
engine, profile = reg.default_for_locale(ctx.locale)
new_text = "<NEW_NARRATION>"
seg_path = Path(ctx.segment_timings[seg_index]["path"])
engine.synthesize(new_text, seg_path, profile)
new_duration_ms = _get_audio_duration_ms(seg_path)

# 3. Update segment_timings — patch text + duration, rechain start_ms
storyboard = Storyboard.load(ctx.storyboard_path)
scene_pauses_ms = [int(s.pause_after_sec * 1000) for s in storyboard.scenes]
segs = ctx.segment_timings
segs[seg_index]["text"] = new_text
segs[seg_index]["duration_ms"] = new_duration_ms
cum = segs[seg_index]["start_ms"]
for i in range(seg_index, len(segs)):
    segs[i]["start_ms"] = cum
    cum += segs[i]["duration_ms"]
    if i < len(scene_pauses_ms):
        cum += scene_pauses_ms[i]
ctx.segment_timings = segs
ctx.save()

# 4. Rebuild SRT
write_srt(_build_subtitle_entries(segs), ctx.subtitle_path)

# 5. Invalidate scene cache
scene_id = storyboard.scenes[seg_index].id
for suffix in ("_final.mp4", "_final_no_overlay.mp4"):
    p = work_dir / "compose" / "scenes" / f"{scene_id}{suffix}"
    if p.exists():
        p.unlink()
```

Then:
```bash
uv run pipeline compose rescene --project-id <ID> --scene <SCENE_ID>
```

### Subtitle text only
```bash
# Edit SRT directly (keep timings, change text only), then:
uv run pipeline compose reburn --project-id <ID>
```

### Visual / overlay only
```bash
# Edit storyboard.json, delete scene cache files, then:
uv run pipeline compose rescene --project-id <ID> --scene <SCENE_ID>
```

---

## Step 5 — Update test fixture

If the change is a wording pattern (abstract → vivid zh-TW), add a case to `tests/unit/test_srt_locale_patch.py`:
- Add `S{N}_ORIGINAL` and `S{N}_VIVID` constants for the changed block
- Add a test class with at minimum: abstract term removed, vivid terms present, timing preserved

---

## Rebuild decision tree

```
User: "enhance/fix/update wording in scene X"
  ↓
Read full scene + adjacent scenes + vocabulary threads
  ↓
Propose changes (may be multiple sentences) — wait for approval
  ↓
[User approves]
  ↓
Check: leftover variant finals on disk? → ask once, act, continue
  ↓
Classify change type → run full chain automatically (no further prompts)
  ↓
Final video ready → tell user to review output
```
