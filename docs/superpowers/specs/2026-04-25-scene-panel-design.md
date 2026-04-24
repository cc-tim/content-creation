# Scene Panel for Dashboard Preview

**Date:** 2026-04-25  
**Status:** Approved

## Goal

When reviewing a rendered video in the dashboard, show a scene strip below the player so the user always knows which scene is playing and can jump to any scene by clicking. Clicking a chip also expands the full narration text so the user can copy-paste specific lines when giving feedback (e.g. "scene 9, the subtitles are overlapping the text").

## Layout

The detail panel (already inside the existing `<tr class="detail-row">`) gets one new block inserted between the video and the meta grid:

```
[ variant tabs (existing) ]
[ video player (existing)  ]
[ scene strip              ]  ← new
[ narration panel          ]  ← new, hidden until a chip is clicked
[ meta grid (existing)     ]
```

### Scene strip

Horizontal scrollable row of compact chips. Each chip: `sN · section` in monospace. Three visual states:

- **Past** (played): dimmed, `#161616` bg, `#374151` text
- **Current** (now playing): blue highlight, `#1e3a5f` bg, `#93c5fd` text, `#3b82f6` border
- **Future** (not yet reached): neutral, `#1e1e1e` bg, `#4a5568` text

Current chip is tracked automatically via `video.addEventListener('timeupdate', ...)`. The active chip scrolls into view as the video plays.

### Narration panel

Hidden by default. Clicking a chip:
1. Jumps video to `scene.start_sec`
2. Opens the narration panel with `scene.id · scene.section · M:SS` header and full narration text
3. Closes the previously open panel (one open at a time)

Text in the narration panel is `user-select: text` — fully selectable and copy-pasteable. Clicking the same chip again collapses the panel.

## Data: scene timestamps

### Source (priority order)

1. **`compose/scenes.json`** — written by the compose stage with actual rendered durations. Present for all renders after this feature ships.
2. **`storyboard.json` fallback** — estimated timestamps (sum of `narration_est_sec + pause_after_sec`). Used for older projects that predate `scenes.json`. Timestamps may drift a few seconds by mid-video.

### `compose/scenes.json` schema

```json
[
  {
    "id": "s1",
    "section": "hook",
    "start_sec": 0.0,
    "duration_sec": 16.4,
    "narration": "Aisle seven. The cart. The yogurt pouch..."
  },
  ...
]
```

Written by `ComposeStage` after each scene clip is finalized, before `ffmpeg concat`.

### Fallback estimation (scanner)

```python
start = 0.0
for scene in storyboard.scenes:
    scenes.append({
        "id": scene.id,
        "section": scene.section,
        "start_sec": start,
        "duration_sec": scene.narration_est_sec + scene.pause_after_sec,
        "narration": scene.narration,
    })
    start += scene.narration_est_sec + scene.pause_after_sec
```

## Components changed

### `src/pipeline/stages/compose.py`

The scene loop already computes `duration` (actual audio-driven seconds) and `scene.pause_after_sec` for every scene. Accumulate these into a `scenes_data` list inside the loop, then write `compose/scenes.json` between step 4 (pause) and step 5 (concat). No extra `ffprobe` calls needed.

```python
scenes_data = []
running = 0.0
# ... inside the scene loop, after pause clip is handled:
scene_dur = duration + scene.pause_after_sec
scenes_data.append({
    "id": scene.id,
    "section": scene.section,
    "start_sec": running,
    "duration_sec": scene_dur,
    "narration": scene.narration,
})
running += scene_dur

# After the loop, before concat:
(compose_dir / "scenes.json").write_text(
    json.dumps(scenes_data, indent=2, ensure_ascii=False)
)
```

### `src/pipeline/dashboard/scanner.py`

`ProjectInfo` gains a `scenes` field:

```python
scenes: list[dict[str, object]] = field(default_factory=list)
```

`scan_projects` fills it:

```python
scenes_file = project_dir / "compose" / "scenes.json"
if scenes_file.exists():
    scenes = json.loads(scenes_file.read_text())
elif (project_dir / "storyboard.json").exists():
    scenes = _estimate_scenes_from_storyboard(project_dir / "storyboard.json")
```

### `src/pipeline/dashboard/server.py`

`_to_dict` passes through `scenes`:

```python
"scenes": p.scenes,
```

### `src/pipeline/dashboard/static/index.html`

- `makeDetailRow(p)` renders the chip strip and hidden narration panel
- `timeupdate` listener on the `<video>` element highlights the current chip and scrolls it into view
- Chip click: `video.currentTime = scene.start_sec`, toggle narration panel

## Error handling / edge cases

- **No scenes data**: strip is not rendered (panel shows only video + meta, as today)
- **Single variant**: strip works the same; no special case needed
- **Variant switch**: switching video variant clears the active chip highlight (timestamps may differ between variants)
- **Estimated timestamps**: no visual distinction needed; small drift is acceptable for a review tool

## Out of scope

- Editing narration from the dashboard
- Per-scene thumbnail previews
- Scenes for projects that have not yet been composed (storyboard-only status)
