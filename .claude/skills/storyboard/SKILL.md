---
name: storyboard
description: View, list, edit, regenerate, or compare the storyboard for a project. Use when asked about specific scenes, narration, visual types, overlays, or storyboard structure.
version: 1.0.0
metadata:
  openclaw:
    requirements:
      binaries: [uv]
---

# Storyboard — View & Edit

## View

```bash
cd /home/tim-huang/content-creation

# List all scenes (id, visual type, narration preview)
uv run pipeline storyboard show

# Full detail for one scene
uv run pipeline storyboard show --scene <scene_id>

# Recording status (for prerecorded voice)
uv run pipeline storyboard recordings --voice <voice-id>
```

## Edit a scene field

```bash
# Safe fields (no re-render needed for text changes before TTS)
uv run pipeline storyboard set <scene_id> narration="新文字"
uv run pipeline storyboard set <scene_id> pause_after_sec=2.0

# Visual dotted-path fields
uv run pipeline storyboard set <scene_id> visual.style_modifier="dark cinematic"
uv run pipeline storyboard set <scene_id> visual.edit_mode="zoom_in"
```

## Read storyboard directly

```bash
cat output/projects/<ID>/storyboard.json | python3 -c "
import json, sys
sb = json.load(sys.stdin)
for s in sb.get('scenes', []):
    v = s.get('visual', {})
    print(f\"{s['id']:8} [{v.get('type','?'):16}] {s.get('narration','')[:80]}\")
"
```

## Regenerate after edits

After manual storyboard edits, re-derive the script:
```bash
uv run python3 -c "
from pipeline.storyboard import Storyboard; from pathlib import Path
sb = Storyboard.from_dict(__import__('json').loads(Path('output/projects/<ID>/storyboard.json').read_text()))
script = sb.derive_script()
Path('output/projects/<ID>/script/script_zh-TW.md').write_text(script, encoding='utf-8')
print('Script updated')
"
```

Then re-render changed scenes (see `render` skill) or full reburn.

## Key storyboard fields

```json
{
  "id": "s3",
  "visual": {
    "type": "generated_image",
    "prompt": "flat minimalist illustration of a courtroom",
    "edit_mode": null
  },
  "overlay": {"type": "text_top", "text": "關鍵時刻"},
  "narration": "就在庭審的最後一天...",
  "narration_est_sec": 10,
  "pause_after_sec": 0.5,
  "facts_ref": ["f4", "f7"]
}
```

Visual types: `generated_image`, `article_image`, `clip`, `text_card`, `slide`, `still_frame`
Overlay types: `title`, `namecard`, `text_top`, `text_left`, `text_emphasis` (never `text`)

## Manifest constraints (explainer-path projects only)

When the project was started from a wiki explainer (i.e.
`output/projects/<ID>/source/explainer.md` exists with `intent: video`),
the manifest in its frontmatter is a HARD INPUT to storyboard generation:

| Manifest block | Constraint when generating storyboard |
|---|---|
| `verbatim_lines` | Each entry must appear *unmodified* in some scene's `narration`, `overlay.text`, or subtitle text. Don't paraphrase; the user marked these as exact. |
| `key_facts` | Each fact must be *stated* somewhere (narration is fine). Paraphrasing is OK. |
| `required_images` | Each `path` must appear as the `visual.path` of at least one scene. Use the `role` hint to choose placement (e.g. `intro_candidate` → s1 or s2). |
| `required_clips` | Same rule as `required_images`. |
| `required_sequence` | Phrases are free-form; honor the implied ordering when arranging scenes. |
| `video_brief` | Shapes pacing, transitions, intro feel. Read it before starting. Mention any constraints in your storyboard summary so the user can check. |

After writing the storyboard, do a self-check pass:

```bash
uv run python3 -c "
import json
from pathlib import Path
from pipeline.explainer import load_explainer
from pipeline.verifier import run_auto_checks
proj = Path('output/projects/<ID>')
ex = load_explainer(proj / 'source/explainer.md')
sb = json.loads((proj / 'storyboard.json').read_text())
result = run_auto_checks(ex.manifest, sb)
for it in result.items:
    if it.status == 'missing' and it.auto_checked:
        print(f'MISSING: {it.category} — {it.label}')
print(f'used={result.used_count} missing={result.missing_count}')
"
```

If any auto-checked item is `MISSING`, surface it to the user before proceeding to TTS.

### MLA projects (mla=True in context.json)

When `ctx.mla=True`, every scene must also have a `narration_en` field:
- Write EN narration for the same scene concept, targeting the **same duration** as `narration` (zh-TW)
- EN narration is NOT a translation — it is the same idea written naturally in English
- Duration guidance: count ~2.5 words/second for EN TTS. If zh-TW scene is 8s, aim for ~20 EN words.
- Flag per-scene if EN word count implies >1.15× the zh-TW duration — TTS will warn on these
- Total EN duration must be within ±2s of total zh-TW duration. Adjust scene-level EN text until this holds.
