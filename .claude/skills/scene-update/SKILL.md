---
name: scene-update
description: Fix wording, narration text, overlays, or audio in a specific scene. Use when asked to fix/rewrite/enhance a scene, change what a scene says, fix overlay text, or re-render a single scene. Triggers on phrases like "fix scene X", "change s2 to say Y", "the wording in s9 is off", "redo the overlay on s12", "tighten the narration in scene 3".
version: 1.1.0
metadata:
  openclaw:
    requirements:
      binaries: [uv, ffmpeg]
---

# Scene Update — Fix a Specific Scene

## Autonomy contract

**Once the user approves the wording changes, execute the full rebuild chain
automatically — no further confirmation needed.** The user only wants to review
the final video output. Do not stop mid-chain to ask "should I also regenerate
the audio?" or "want me to rescene now?" — if the change type requires it, do it.

The only gates where you pause for human input:
1. Before proposing wording changes (so they can approve the text)
2. If leftover variant files exist and need cleanup (ask once, then act)
3. If something fails unexpectedly

---

## Hard rule: minimum work only

**Only the changed scenes get re-synthesized and re-rendered. Every other scene
stays cached.** If the user changed s2/s9/s24, you pass `--scene s2 --scene s9
--scene s24` to `compose rescene` — never a sweep of every scene.

If you find yourself about to pass more than half the storyboard's scene IDs to
`compose rescene`, stop. That's not the right command — `compose reburn` is.

---

## Step 1 — Classify the change

Before touching anything, decide which chain runs:

| Change type | Full chain |
|-------------|-----------|
| Subtitle text only (no audio change) | Edit SRT → `compose reburn` |
| Narration text (audio changes) | Edit storyboard → synthesize audio for that scene → rechain timings → rebuild SRT → invalidate scene cache → `compose rescene --scene <id>` |
| Visual / overlay only | Edit storyboard → invalidate scene cache → `compose rescene --scene <id>` |
| Theme / font / color | Edit storyboard → `compose reburn` |

---

## Step 2 — Wording enhancement: read the whole scene first

When the task is enhancing or fixing wording, **never do a mechanical word swap
on the target sentence alone.**

Read before writing:
1. **Full scene narration** — what is the scene trying to accomplish emotionally? What's the arc (opening label → concrete image → felt conclusion)?
2. **Adjacent scenes** — what vocabulary or metaphors have already been introduced? What registers are consistent?
3. **Vocabulary threads** — look for recurring words across scenes (e.g., 接偏了 / 沒接準 / 感受落空了 / 沒接住). New wording should weave into the thread, not break it.
4. **Storytelling structure** — does the target sentence set up something later in the scene? Does it echo a closing line? Changing it may require changing other sentences to preserve the arc.

```bash
cd /home/tim-huang/content-creation
uv run pipeline storyboard show --scene <scene_id>
# Also read adjacent scenes
uv run python3 - <<'EOF'
import json
sb = json.load(open('output/projects/<ID>/storyboard.json'))
scenes = sb['scenes']
ids = [s['id'] for s in scenes]
idx = ids.index('<scene_id>')
for s in scenes[max(0,idx-1):idx+2]:
    print(f"--- {s['id']} ---")
    print(f"narration: {s.get('narration','')}")
    print(f"visual:    {s.get('visual',{})}")
    print(f"overlay:   {s.get('overlay',{})}")
EOF
```

**What to avoid:**
- Replacing abstract terms with other abstract terms
- Mechanical synonym swaps that don't change the register
- Changing the opening label without checking if the scene's closing line still resolves it

**What to aim for:**
- Zero-decoding zh-TW: the listener should feel it before they parse it
- Concrete sensory language over clinical compounds (情感錯配 → 接偏了; 情感伸手是危險的 → 哭了，也沒人接住)
- If one sentence changes, check whether another sentence in the same scene should change to maintain coherence

**You may — and often should — change multiple sentences.** Show your reasoning
for each change before editing.

---

## Step 3 — Variant cleanup check

Before rebuilding, check for leftover variant files:

```bash
uv run python3 - <<'EOF'
import json
from pathlib import Path
ID = "<ID>"
ctx = json.load(open(f'output/projects/{ID}/context.json'))
preferred = ctx.get('preferred_variant')
locale = ctx.get('locale', 'zh-TW')
finals = list(Path(f'output/projects/{ID}/compose').glob(f'final_{locale}*.mp4'))
print(f'preferred_variant: {preferred}')
print('Finals on disk:', [f.name for f in finals])
EOF
```

If `preferred_variant` is set and other `final_*.mp4` files still exist on disk,
ask once: "Preferred variant is locked to `{variant}`. I also see `{others}`
still on disk — want me to clean them up?" Then act and continue immediately.

---

## Step 4 — Apply the change

### Subtitle text only

```bash
# Edit the SRT directly (keep timings, change text only), then:
uv run pipeline compose reburn --project-id <ID>
```

### Visual / overlay only

```bash
# Edit storyboard.json with `storyboard set` for safe fields:
uv run pipeline storyboard set <scene_id> overlay.text="新的標題"

# For complex visual changes, edit storyboard.json directly via Python.
# Then re-render only the affected scene:
uv run pipeline compose rescene --project-id <ID> --scene <scene_id>
```

### Narration text (audio changes)

This is the most complex case — TTS must be regenerated, segment timings must
be rechained, the SRT must be rebuilt, and the scene cache invalidated. Do it
in one inline script; don't break it into manual steps:

```bash
uv run python3 - <<'EOF'
import asyncio, json
from pathlib import Path
from pipeline.stages.base import PipelineContext
from pipeline.voices.registry import VoiceRegistry
from pipeline.stages.tts import _get_audio_duration_ms, _build_subtitle_entries
from pipeline.utils.srt import write_srt
from pipeline.storyboard import Storyboard

ID = "<ID>"
SCENE_INDEX = 0          # 0-based: s1=0, s2=1, s3=2, ...
NEW_TEXT = "<NEW_NARRATION>"

work_dir = Path(f"output/projects/{ID}")
ctx = PipelineContext.load(work_dir / "context.json")

# 1. Storyboard must already be updated (do this BEFORE running this script).

# 2. Re-synthesize audio for the changed scene
reg = VoiceRegistry(Path("voices"))
engine, profile = reg.default_for_locale(ctx.locale)
seg_path = Path(ctx.segment_timings[SCENE_INDEX]["path"])
engine.synthesize(NEW_TEXT, seg_path, profile)
new_duration_ms = _get_audio_duration_ms(seg_path)

# 3. Update segment_timings — patch text + duration, rechain start_ms forward
storyboard = Storyboard.load(ctx.storyboard_path)
scene_pauses_ms = [int(s.pause_after_sec * 1000) for s in storyboard.scenes]
segs = ctx.segment_timings
segs[SCENE_INDEX]["text"] = NEW_TEXT
segs[SCENE_INDEX]["duration_ms"] = new_duration_ms
cum = segs[SCENE_INDEX]["start_ms"]
for i in range(SCENE_INDEX, len(segs)):
    segs[i]["start_ms"] = cum
    cum += segs[i]["duration_ms"]
    if i < len(scene_pauses_ms):
        cum += scene_pauses_ms[i]
ctx.segment_timings = segs
ctx.save()

# 4. Rebuild SRT
write_srt(_build_subtitle_entries(segs), ctx.subtitle_path)

# 5. Invalidate this scene's cache files
scene_id = storyboard.scenes[SCENE_INDEX].id
for suffix in ("_final.mp4", "_final_no_overlay.mp4"):
    p = work_dir / "compose" / "scenes" / f"{scene_id}{suffix}"
    if p.exists():
        p.unlink()

print(f"Ready. Now run: uv run pipeline compose rescene --project-id {ID} --scene {scene_id}")
EOF
```

Then:
```bash
uv run pipeline compose rescene --project-id <ID> --scene <scene_id>
```

---

## Step 5 — Final video

The `compose rescene` step already produces the new final under
`compose/final_<locale>_<variant>.mp4`. If `preferred_variant` is locked,
the output is the focused variant only. No separate `reburn` is needed unless
you also changed subtitles or theme.

---

## Rules

- Read full scene + adjacent scenes FIRST — changes must flow naturally
- Overlay types: `title`, `namecard`, `text_top`, `text_left`, `text_emphasis` (never `text`)
- Never put overlay on `text_card` or `slide` visuals — creates text-on-text overlap
- Overlay y position ≤ 0.70 to avoid subtitle collision
- After narration changes: always rescene to regenerate TTS before reburn
- Pass `--scene <id>` for every changed scene — and only the changed scenes

---

## Rebuild decision tree

```
User: "fix wording in scene X"
  ↓
Read full scene + adjacent scenes + vocabulary threads
  ↓
Propose changes (may be multiple sentences) — wait for approval
  ↓
[User approves]
  ↓
Check: leftover variant finals on disk? → ask once, act, continue
  ↓
Classify change type → run minimum chain automatically (no further prompts)
  ↓
Final video ready → tell user to review the output
```
