# Dashboard Design

**Date:** 2026-04-23
**Status:** Approved

## Goal

A read-only web dashboard that lists every project under `output/projects/`, shows its pipeline status, and lets the operator preview the final video without leaving the browser. Solves the problem of forgetting to review rendered videos before they accumulate.

## Architecture

**Backend:** FastAPI (new dep: `fastapi`, `uvicorn[standard]`), registered as a Typer sub-app under `pipeline dashboard`.

**Frontend:** Single static `src/pipeline/dashboard/static/index.html` — no build step, no framework. Fetches `/api/projects` on load and every 30 seconds.

**Video serving:** FastAPI mounts `output/` at `/output` so `<video src="/output/projects/.../compose/final_zh-TW.mp4">` works directly.

**Port:** 8765 (hardcoded default, overridable via `--port`).

## Launch

```bash
uv run pipeline dashboard          # starts on http://localhost:8765
uv run pipeline dashboard --port 9000
```

Opens in the default browser automatically (`webbrowser.open`).

## Backend

### `GET /api/projects`

Scans `output/projects/*/context.json` and (if present) `output/projects/*/metadata.json` for each project. Returns a JSON array, one object per project, sorted by `project_id` descending (newest first).

`output/` is resolved relative to the current working directory at launch time (i.e. the project root when using `uv run`).

Each object:

```json
{
  "project_id": "1776850327_B",
  "status": "published",
  "title": "孩子愛玩工地不愛遊樂場？...",    // from metadata.json, null if missing
  "locale": "zh-TW",
  "niche": "parenting",
  "source_url": "https://www.youtube.com/watch?v=kRAl4Xgs_NU",
  "youtube_video_id": "-t52m9t7Lgw",
  "published_at": "2026-04-23T14:26:55+00:00",
  "final_video_path": "output/projects/1776850327_B/compose/final_zh-TW.mp4",
  "has_video": true,
  "tags": ["育兒", "親子", "..."]           // from metadata.json, [] if missing
}
```

### Status derivation (highest completed stage wins)

| Status | Condition |
|---|---|
| `published` | `context.youtube_video_id` is set |
| `rendered` | `compose/final_<locale>.mp4` exists on disk |
| `storyboard` | `storyboard.json` exists on disk |
| `analyzed` | `knowledge.json` exists on disk |
| `acquired` | `source/video.mp4` exists on disk |
| `new` | only `context.json` present |

### `GET /output/{path:path}`

FastAPI `StaticFiles` mount — serves the entire `output/` directory. Used for video streaming.

### `GET /`

Serves `src/pipeline/dashboard/static/index.html`.

## Frontend

Single `index.html` with inline `<style>` and `<script>`. No external CDN dependencies.

### Layout

**Header bar** (full width):
- Left: "Content Dashboard" title + project count
- Right: summary pills — `N published`, `N rendered`, `N storyboard`
- Far right: "↻ live" indicator (pulses on each refresh)

**Table** (full width, compact rows):

| Column | Content |
|---|---|
| Status | Color-coded badge pill |
| Title / ID | `metadata.title` if available, else `project_id`; sub-line shows raw ID |
| Locale · Niche | e.g. `zh-TW · parenting` or just `zh-TW` |
| Source | YouTube video ID extracted from `source_url`, links to `youtube.com/watch?v=…` |
| YouTube | `youtube_video_id` if published, links to `youtube.com/watch?v=…` |
| Date | `published_at` formatted as `MMM DD`, or `—` |

Rows without a rendered video (status `storyboard`, `analyzed`, `acquired`, `new`) are dimmed (opacity 0.5) and not clickable.

### Status badge colors

| Status | Color |
|---|---|
| published | green `#16a34a` |
| rendered | amber `#d97706` |
| storyboard | indigo `#6366f1` |
| analyzed | blue `#3b82f6` |
| acquired | slate `#475569` |
| new | dark `#374151` |

### Row click → detail panel

Clicking a rendered or published row opens a detail panel that expands below the table (accordion style, one open at a time). The panel contains:

- `<video controls>` tag pointing to `/output/projects/<id>/compose/final_<locale>.mp4`
- Metadata grid: Title, Locale, YouTube link, Published date, Tags (first 5), Source link

Clicking the same row again collapses the panel. Clicking a different rendered/published row closes the current panel and opens the new one.

### Auto-refresh

`setInterval` calls `GET /api/projects` every 30 seconds and re-renders the table in place. The open detail panel stays open if the same project_id is still present.

## File layout

```
src/pipeline/
  dashboard/
    __init__.py
    server.py          # FastAPI app, /api/projects endpoint, mounts
    scanner.py         # scans output/projects/, derives status, returns list
    static/
      index.html       # complete frontend (HTML + CSS + JS inline)
  cli.py               # adds `dashboard` sub-command → calls server.py
```

## Dependencies

Add to `pyproject.toml`:
- `fastapi>=0.111`
- `uvicorn[standard]>=0.29`

Both are lightweight and have no conflicts with the existing stack.

## Out of scope

- Authentication (local tool, not exposed to internet)
- Action buttons (publish, re-render) — future enhancement
- Sorting / filtering by status — future enhancement
- Shorts versions (storyboard_short_*.json) — shown as part of parent project, not separate rows
