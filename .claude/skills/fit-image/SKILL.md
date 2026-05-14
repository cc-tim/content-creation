---
name: fit-image
description: Refit article_image and image scenes so source images fill the active frame inset without clipping the subject. Use when asked to "fit-image", "refit s2", "remove image padding", "fix book-page letterboxing", or before rendering after storyboard approval.
version: 1.0.0
metadata:
  openclaw:
    requirements:
      binaries: [uv, ffmpeg]
---

# Fit Image

Refit file-backed scene images into the active render target. This skill is the vision layer:
the agent reads each source image directly, decides whether crop or outpaint preserves the
subject, then calls the pure helpers in `pipeline.composer.refit`.

## Inputs

- `fit-image` - dry-run current/newest project, all eligible scenes.
- `fit-image --apply` - apply decisions for all eligible scenes.
- `fit-image s2 s7 --apply` - apply only listed scenes.
- `fit-image --project-id <ID>` - choose `output/projects/<ID>` explicitly.

Default mode is dry-run. Never overwrite `visual.path`; write sidecars under
`output/projects/<ID>/edits/` and set `visual.refit_path`.

## Candidate Rules

Process only scenes whose `visual.type` is `article_image` or `image`.
Skip `text_card`, `generated_image`, `clip`, `slide`, `rich_slide`, `map`, and `namecard`.

Use the target box from:

```python
from pipeline.composer import refit
storyboard = json.load(open(PROJECT / "storyboard.json"))
canvas_w, canvas_h = refit.canvas_size(storyboard)
target_w, target_h = refit.target_box(storyboard.get("theme") or {}, canvas_w, canvas_h)
```

## Workflow

1. Resolve project.
2. Load `storyboard.json`.
3. For each requested candidate scene:
   - Resolve `visual.path` relative to repo root first, then project root.
   - Open/read the image directly in this agent session.
   - If aspect diff is at or below 8 percent, decision is `leave-as-is`.
   - If an existing `visual.refit_path` exists and is newer than the source, decision is `cached`.
   - If source min dimension is under 480 px and the target is much larger, prefer `outpaint`.
   - If the source has enough resolution and subject-safe crop exists, choose `crop` with bias `(cx, cy)`.
   - Otherwise choose `outpaint`.
4. In dry-run mode, print a decision table only.
5. In apply mode:
   - Run the chosen operation.
   - If outpaint output aspect still differs from target by more than 1 percent, run a PIL post-crop to the exact target.
   - Set `visual.refit_path` with `uv run pipeline storyboard set <scene> visual.refit_path=<repo-relative-output> --work-dir <project>`.
   - Append a JSON object to `<project>/edits/refit_log.json`.

## Decision Table Format

Print one row per candidate:

```text
scene  type           source_size  target_size  decision     reason
s1     article_image  557x534      947x484      outpaint     square manuscript into 1.96:1 book inset; crop would remove page content
s4     article_image  3868x2601    947x484      crop         mild landscape mismatch; subject remains centered
```

## Apply Snippet

Use this snippet after the vision decision is made for each scene. Set the uppercase
variables to the current scene values from the decision table before running it.

```bash
cd /home/tim-huang/content-creation
uv run python3 - <<'PY'
import json
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image
from pipeline.composer import refit

PROJECT = Path("output/projects/<ID>")
SCENE_ID = "<scene_id>"
SOURCE = Path("<repo_relative_or_absolute_source>")
DECISION = "<crop|outpaint>"
BIAS = (<cx>, <cy>)
INSTRUCTION = "<outpaint instruction or empty>"
TARGET_W = <target_w>
TARGET_H = <target_h>

source_hash = "sha256:" + __import__("hashlib").sha256(SOURCE.read_bytes()).hexdigest()
edits = PROJECT / "edits"
edits.mkdir(parents=True, exist_ok=True)
short_hash = source_hash.split(":", 1)[1][:6]
out = edits / f"{SCENE_ID}_{DECISION}_{short_hash}.png"

with Image.open(SOURCE) as img:
    source_size = [img.width, img.height]

post_crop = False
if DECISION == "crop":
    refit.apply_crop(SOURCE, out, TARGET_W, TARGET_H, bias=BIAS)
elif DECISION == "outpaint":
    refit.apply_outpaint(SOURCE, out, TARGET_W, TARGET_H, INSTRUCTION)
    if refit.aspect_diff(out, TARGET_W, TARGET_H) > 0.01:
        post = edits / f"{SCENE_ID}_outpaint_postcrop_{short_hash}.png"
        refit.apply_crop(out, post, TARGET_W, TARGET_H)
        out = post
        post_crop = True
else:
    raise SystemExit(f"unsupported decision: {DECISION}")

repo_relative_out = out.as_posix()
log_path = edits / "refit_log.json"
entries = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else []
entries.append({
    "scene_id": SCENE_ID,
    "decision": DECISION,
    "rationale": "<one-line rationale>",
    "source_path": SOURCE.as_posix(),
    "source_hash": source_hash,
    "source_size": source_size,
    "target_size": [TARGET_W, TARGET_H],
    "output_path": out.relative_to(PROJECT).as_posix(),
    "storyboard_refit_path": repo_relative_out,
    "instruction": INSTRUCTION,
    "model": "fal-ai/flux-pro/kontext" if DECISION == "outpaint" else None,
    "cost_estimate_usd": 0.04 if DECISION == "outpaint" else 0.0,
    "post_crop": post_crop,
    "ts": datetime.now(timezone.utc).isoformat(),
})
log_path.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
print(repo_relative_out)
PY

uv run pipeline storyboard set <scene_id> visual.refit_path="<repo-relative-output>" --work-dir "output/projects/<ID>"
```

## Baby-Walker Smoke Target

For `output/projects/20260504-115232-baby-walker-story`, s1-s5 are the motivating
range. Process all `article_image` and `image` scenes in that range and skip any `text_card`
by rule. After `--apply`, s1-s5 should have no dark image padding inside the book-page inset;
s2 must not crop the child or painting frame against a hard edge.

## Failure Handling

- `[KEY EXHAUSTED]`: report the stderr line from `gen-image-edit.py`, record `decision=failed_quota`, leave `visual.refit_path` unset.
- FAL/API failure after retry: record `decision=failed_api`, leave `visual.refit_path` unset.
- Missing source path: fail loud and stop; this is a storyboard/source bug.
- Storyboard write failure: keep the sidecar and log entry; report the exact failed `pipeline storyboard set` command.
