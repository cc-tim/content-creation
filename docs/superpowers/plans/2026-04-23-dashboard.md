# Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `uv run pipeline dashboard` command that starts a FastAPI server on port 8765 and serves a read-only web dashboard listing all projects from `output/projects/` with status badges, metadata, and inline video preview.

**Architecture:** FastAPI backend with a single `/api/projects` endpoint that scans `output/projects/*/context.json` + `metadata.json` on each request. Frontend is a dependency-free single `index.html` served from the package. The `output/` directory is mounted at `/output` for video streaming.

**Tech Stack:** `fastapi>=0.111`, `uvicorn[standard]>=0.29`, Typer CLI integration, vanilla HTML/CSS/JS (no build step).

---

## File Map

| Action | Path | Purpose |
|---|---|---|
| Create | `src/pipeline/dashboard/__init__.py` | package marker |
| Create | `src/pipeline/dashboard/scanner.py` | scan `output/projects/`, derive status, return `ProjectInfo` list |
| Create | `src/pipeline/dashboard/server.py` | FastAPI app factory, `/api/projects` endpoint, static mounts |
| Create | `src/pipeline/dashboard/static/index.html` | complete single-file frontend |
| Modify | `src/pipeline/cli.py` | register `dashboard` command |
| Modify | `pyproject.toml` | add `fastapi`, `uvicorn[standard]` deps |
| Create | `tests/unit/test_dashboard_scanner.py` | scanner unit tests |
| Create | `tests/unit/test_dashboard_server.py` | server unit tests |

---

## Task 1: Add dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add fastapi and uvicorn to pyproject.toml**

In `pyproject.toml`, add to the `dependencies` list (after `httpx>=0.28`):

```toml
    "fastapi>=0.111",
    "uvicorn[standard]>=0.29",
```

- [ ] **Step 2: Sync dependencies**

```bash
uv sync
```

Expected: resolves and installs without conflicts.

- [ ] **Step 3: Verify imports work**

```bash
uv run python -c "import fastapi, uvicorn; print('ok')"
```

Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add fastapi + uvicorn deps for dashboard"
```

---

## Task 2: Scanner — ProjectInfo + scan_projects()

**Files:**
- Create: `src/pipeline/dashboard/__init__.py`
- Create: `src/pipeline/dashboard/scanner.py`
- Create: `tests/unit/test_dashboard_scanner.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_dashboard_scanner.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.dashboard.scanner import scan_projects


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_project(
    tmp_path: Path,
    project_id: str,
    *,
    ctx_extra: dict | None = None,
    meta: dict | None = None,
    files: list[str] | None = None,
) -> Path:
    """Create a minimal fake project directory."""
    project_dir = tmp_path / "output" / "projects" / project_id
    project_dir.mkdir(parents=True)

    ctx: dict = {
        "project_id": project_id,
        "locale": "zh-TW",
        "source_url": "https://www.youtube.com/watch?v=abc123",
        "niche": None,
        "youtube_video_id": None,
        "published_at": None,
        **(ctx_extra or {}),
    }
    (project_dir / "context.json").write_text(json.dumps(ctx))

    if meta is not None:
        (project_dir / "metadata.json").write_text(json.dumps(meta))

    for rel in files or []:
        p = project_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("")

    return project_dir


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_returns_empty_when_no_projects_dir(tmp_path: Path) -> None:
    result = scan_projects(tmp_path / "output")
    assert result == []


def test_status_new_when_only_context(tmp_path: Path) -> None:
    _make_project(tmp_path, "1000")
    [p] = scan_projects(tmp_path / "output")
    assert p.status == "new"
    assert p.has_video is False
    assert p.final_video_url_path is None


def test_status_acquired(tmp_path: Path) -> None:
    _make_project(tmp_path, "1001", files=["source/video.mp4"])
    [p] = scan_projects(tmp_path / "output")
    assert p.status == "acquired"


def test_status_analyzed(tmp_path: Path) -> None:
    _make_project(tmp_path, "1002", files=["source/video.mp4", "knowledge.json"])
    [p] = scan_projects(tmp_path / "output")
    assert p.status == "analyzed"


def test_status_storyboard(tmp_path: Path) -> None:
    _make_project(
        tmp_path, "1003",
        files=["source/video.mp4", "knowledge.json", "storyboard.json"],
    )
    [p] = scan_projects(tmp_path / "output")
    assert p.status == "storyboard"


def test_status_rendered(tmp_path: Path) -> None:
    _make_project(
        tmp_path, "1004",
        files=["source/video.mp4", "knowledge.json", "storyboard.json",
               "compose/final_zh-TW.mp4"],
    )
    [p] = scan_projects(tmp_path / "output")
    assert p.status == "rendered"
    assert p.has_video is True
    assert p.final_video_url_path == "/output/projects/1004/compose/final_zh-TW.mp4"


def test_status_published(tmp_path: Path) -> None:
    _make_project(
        tmp_path, "1005",
        ctx_extra={"youtube_video_id": "xyz999", "published_at": "2026-04-23T00:00:00+00:00"},
        files=["compose/final_zh-TW.mp4"],
    )
    [p] = scan_projects(tmp_path / "output")
    assert p.status == "published"
    assert p.youtube_video_id == "xyz999"
    assert p.published_at == "2026-04-23T00:00:00+00:00"


def test_title_and_tags_from_metadata(tmp_path: Path) -> None:
    _make_project(
        tmp_path, "1006",
        meta={"title": "My Video Title", "tags": ["tag1", "tag2"]},
    )
    [p] = scan_projects(tmp_path / "output")
    assert p.title == "My Video Title"
    assert p.tags == ["tag1", "tag2"]


def test_title_none_tags_empty_when_no_metadata(tmp_path: Path) -> None:
    _make_project(tmp_path, "1007")
    [p] = scan_projects(tmp_path / "output")
    assert p.title is None
    assert p.tags == []


def test_projects_sorted_newest_first(tmp_path: Path) -> None:
    _make_project(tmp_path, "1000")
    _make_project(tmp_path, "2000")
    _make_project(tmp_path, "1500")
    results = scan_projects(tmp_path / "output")
    assert [p.project_id for p in results] == ["2000", "1500", "1000"]


def test_locale_and_niche_populated(tmp_path: Path) -> None:
    _make_project(tmp_path, "1008", ctx_extra={"locale": "ja", "niche": "crime"})
    [p] = scan_projects(tmp_path / "output")
    assert p.locale == "ja"
    assert p.niche == "crime"
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/unit/test_dashboard_scanner.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'pipeline.dashboard'`

- [ ] **Step 3: Create package marker**

Create `src/pipeline/dashboard/__init__.py` (empty):

```python
```

- [ ] **Step 4: Implement scanner.py**

Create `src/pipeline/dashboard/scanner.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ProjectInfo:
    project_id: str
    status: str
    title: str | None
    locale: str
    niche: str | None
    source_url: str | None
    youtube_video_id: str | None
    published_at: str | None
    has_video: bool
    final_video_url_path: str | None
    tags: list[str] = field(default_factory=list)


def scan_projects(output_dir: Path) -> list[ProjectInfo]:
    projects_dir = output_dir / "projects"
    if not projects_dir.exists():
        return []

    ctx_files = sorted(
        projects_dir.glob("*/context.json"),
        key=lambda p: _sort_key(p.parent.name),
        reverse=True,
    )

    results: list[ProjectInfo] = []
    for ctx_file in ctx_files:
        project_dir = ctx_file.parent
        try:
            ctx = json.loads(ctx_file.read_text())
        except (json.JSONDecodeError, OSError):
            continue

        meta: dict = {}
        meta_file = project_dir / "metadata.json"
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text())
            except (json.JSONDecodeError, OSError):
                pass

        locale: str = ctx.get("locale", "")
        final_mp4 = _find_final_video(project_dir, locale)
        has_video = final_mp4 is not None
        final_video_url_path: str | None = None
        if final_mp4 is not None:
            final_video_url_path = "/output/" + str(final_mp4.relative_to(output_dir))

        results.append(
            ProjectInfo(
                project_id=project_dir.name,
                status=_derive_status(ctx, project_dir, locale),
                title=meta.get("title"),
                locale=locale,
                niche=ctx.get("niche"),
                source_url=ctx.get("source_url"),
                youtube_video_id=ctx.get("youtube_video_id"),
                published_at=ctx.get("published_at"),
                has_video=has_video,
                final_video_url_path=final_video_url_path,
                tags=meta.get("tags", []),
            )
        )

    return results


def _derive_status(ctx: dict, project_dir: Path, locale: str) -> str:
    if ctx.get("youtube_video_id"):
        return "published"
    if _find_final_video(project_dir, locale) is not None:
        return "rendered"
    if (project_dir / "storyboard.json").exists():
        return "storyboard"
    if (project_dir / "knowledge.json").exists():
        return "analyzed"
    if (project_dir / "source" / "video.mp4").exists():
        return "acquired"
    return "new"


def _find_final_video(project_dir: Path, locale: str) -> Path | None:
    compose_dir = project_dir / "compose"
    if not compose_dir.exists():
        return None
    specific = compose_dir / f"final_{locale}.mp4"
    if specific.exists():
        return specific
    matches = list(compose_dir.glob("final_*.mp4"))
    return matches[0] if matches else None


def _sort_key(project_id: str) -> tuple[int, str]:
    parts = project_id.split("_", 1)
    try:
        return (int(parts[0]), parts[1] if len(parts) > 1 else "")
    except ValueError:
        return (0, project_id)
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
uv run pytest tests/unit/test_dashboard_scanner.py -v
```

Expected: all 10 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/dashboard/ tests/unit/test_dashboard_scanner.py
git commit -m "feat(dashboard): scanner — ProjectInfo + scan_projects()"
```

---

## Task 3: Server — FastAPI app + /api/projects endpoint

**Files:**
- Create: `src/pipeline/dashboard/server.py`
- Create: `tests/unit/test_dashboard_server.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_dashboard_server.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from pipeline.dashboard.server import create_app


def _output_dir(tmp_path: Path) -> Path:
    d = tmp_path / "output"
    d.mkdir()
    return d


def test_api_projects_empty(tmp_path: Path) -> None:
    client = TestClient(create_app(_output_dir(tmp_path)))
    resp = client.get("/api/projects")
    assert resp.status_code == 200
    assert resp.json() == []


def test_api_projects_returns_project(tmp_path: Path) -> None:
    output_dir = _output_dir(tmp_path)
    project_dir = output_dir / "projects" / "9999"
    project_dir.mkdir(parents=True)
    (project_dir / "context.json").write_text(json.dumps({
        "project_id": "9999",
        "locale": "zh-TW",
        "source_url": "https://www.youtube.com/watch?v=test123",
        "niche": "parenting",
        "youtube_video_id": None,
        "published_at": None,
    }))

    client = TestClient(create_app(output_dir))
    resp = client.get("/api/projects")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    p = data[0]
    assert p["project_id"] == "9999"
    assert p["status"] == "new"
    assert p["locale"] == "zh-TW"
    assert p["niche"] == "parenting"
    assert p["has_video"] is False
    assert p["tags"] == []


def test_api_projects_published_fields(tmp_path: Path) -> None:
    output_dir = _output_dir(tmp_path)
    project_dir = output_dir / "projects" / "8888"
    project_dir.mkdir(parents=True)
    (project_dir / "context.json").write_text(json.dumps({
        "project_id": "8888",
        "locale": "zh-TW",
        "source_url": "https://www.youtube.com/watch?v=src",
        "niche": None,
        "youtube_video_id": "pub123",
        "published_at": "2026-04-23T12:00:00+00:00",
    }))
    compose_dir = project_dir / "compose"
    compose_dir.mkdir()
    (compose_dir / "final_zh-TW.mp4").write_text("")
    (project_dir / "metadata.json").write_text(json.dumps({
        "title": "Test Title",
        "tags": ["a", "b"],
    }))

    client = TestClient(create_app(output_dir))
    resp = client.get("/api/projects")
    assert resp.status_code == 200
    [p] = resp.json()
    assert p["status"] == "published"
    assert p["youtube_video_id"] == "pub123"
    assert p["title"] == "Test Title"
    assert p["tags"] == ["a", "b"]
    assert p["has_video"] is True
    assert p["final_video_url_path"] == "/output/projects/8888/compose/final_zh-TW.mp4"


def test_index_serves_html(tmp_path: Path) -> None:
    client = TestClient(create_app(_output_dir(tmp_path)))
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert b"Content Dashboard" in resp.content
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/unit/test_dashboard_server.py -v 2>&1 | head -20
```

Expected: `ImportError: cannot import name 'create_app'`

- [ ] **Step 3: Implement server.py**

Create `src/pipeline/dashboard/server.py`:

```python
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from pipeline.dashboard.scanner import ProjectInfo, scan_projects

_STATIC_DIR = Path(__file__).parent / "static"


def create_app(output_dir: Path) -> FastAPI:
    output_dir.mkdir(parents=True, exist_ok=True)
    app = FastAPI(title="Content Dashboard")

    @app.get("/api/projects")
    def get_projects() -> list[dict]:
        return [_to_dict(p) for p in scan_projects(output_dir)]

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(_STATIC_DIR / "index.html")

    app.mount("/output", StaticFiles(directory=str(output_dir)), name="output")

    return app


def _to_dict(p: ProjectInfo) -> dict:
    return {
        "project_id": p.project_id,
        "status": p.status,
        "title": p.title,
        "locale": p.locale,
        "niche": p.niche,
        "source_url": p.source_url,
        "youtube_video_id": p.youtube_video_id,
        "published_at": p.published_at,
        "has_video": p.has_video,
        "final_video_url_path": p.final_video_url_path,
        "tags": p.tags,
    }
```

- [ ] **Step 4: Create static dir placeholder so the package exists**

```bash
mkdir -p src/pipeline/dashboard/static
touch src/pipeline/dashboard/static/.gitkeep
```

- [ ] **Step 5: Run tests — the index test will fail (no index.html yet); others should pass**

```bash
uv run pytest tests/unit/test_dashboard_server.py -v
```

Expected: 3 tests PASS, `test_index_serves_html` FAIL with `FileNotFoundError`.
This is expected — we add the HTML in the next task.

- [ ] **Step 6: Commit scanner + server (partial — HTML next)**

```bash
git add src/pipeline/dashboard/server.py src/pipeline/dashboard/static/.gitkeep \
        tests/unit/test_dashboard_server.py
git commit -m "feat(dashboard): FastAPI server + /api/projects endpoint"
```

---

## Task 4: Frontend — static/index.html

**Files:**
- Create: `src/pipeline/dashboard/static/index.html`

No unit tests for HTML/JS. Verification is the `test_index_serves_html` test from Task 3 (it checks `Content Dashboard` appears in the HTML).

- [ ] **Step 1: Create index.html**

Create `src/pipeline/dashboard/static/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Content Dashboard</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { background: #0f0f0f; color: #e2e8f0; font-family: system-ui, -apple-system, sans-serif; font-size: 14px; }

    .header { display: flex; align-items: center; justify-content: space-between; padding: 14px 20px; border-bottom: 1px solid #1e1e1e; }
    .header-title { font-size: 16px; font-weight: 600; }
    .header-count { margin-left: 10px; color: #4a5568; font-size: 12px; }
    .header-stats { display: flex; gap: 8px; align-items: center; }
    .stat-pill { font-size: 11px; padding: 3px 8px; border-radius: 4px; }
    .pill-published { background: #16a34a22; color: #16a34a; }
    .pill-rendered  { background: #d9770622; color: #d97706; }
    .pill-storyboard{ background: #6366f122; color: #6366f1; }
    .live-ind { color: #374151; font-size: 11px; padding: 3px 8px; transition: color .3s; }
    .live-ind.pulse { color: #16a34a; }

    table { width: 100%; border-collapse: collapse; }
    thead tr { border-bottom: 1px solid #1e1e1e; }
    th { text-align: left; padding: 8px 16px; font-size: 10px; text-transform: uppercase;
         letter-spacing: .05em; color: #4a5568; font-weight: 500; }
    tbody tr { border-bottom: 1px solid #141414; }
    tbody tr.clickable { cursor: pointer; transition: background .1s; }
    tbody tr.clickable:hover, tbody tr.active { background: #161616; }
    tbody tr.dimmed { opacity: .45; }
    td { padding: 10px 16px; vertical-align: middle; }

    .badge { font-size: 9px; padding: 2px 8px; border-radius: 10px; color: #fff; white-space: nowrap; }
    .s-published  { background: #16a34a; }
    .s-rendered   { background: #d97706; }
    .s-storyboard { background: #6366f1; }
    .s-analyzed   { background: #3b82f6; }
    .s-acquired   { background: #475569; }
    .s-new        { background: #374151; }

    .t-main { color: #cbd5e1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 280px; }
    .t-id   { color: #374151; font-size: 10px; margin-top: 2px; }
    .t-miss { color: #4a5568; font-style: italic; }
    a { color: #3b82f6; text-decoration: none; }
    a:hover { text-decoration: underline; }
    a.yt { color: #16a34a; }
    .nil { color: #2d3748; }

    .detail-row td { padding: 0; }
    .detail-panel { padding: 16px 20px; background: #111; border-bottom: 1px solid #1e1e1e; }
    video { width: 100%; max-width: 720px; border-radius: 4px; background: #000; display: block; margin-bottom: 14px; }
    .meta-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 12px; color: #64748b; }
    .meta-grid .lbl { color: #475569; }
  </style>
</head>
<body>

<div class="header">
  <div>
    <span class="header-title">Content Dashboard</span>
    <span class="header-count" id="hcount"></span>
  </div>
  <div class="header-stats">
    <span id="sp" class="stat-pill pill-published" style="display:none"></span>
    <span id="sr" class="stat-pill pill-rendered"  style="display:none"></span>
    <span id="ss" class="stat-pill pill-storyboard" style="display:none"></span>
    <span id="live" class="live-ind">↻ live</span>
  </div>
</div>

<table>
  <thead><tr>
    <th>Status</th>
    <th>Title / ID</th>
    <th>Locale · Niche</th>
    <th>Source</th>
    <th>YouTube</th>
    <th>Date</th>
  </tr></thead>
  <tbody id="tbody"></tbody>
</table>

<script>
let activeId = null;

function ytId(url) {
  if (!url) return null;
  const m = url.match(/[?&]v=([^&]+)/);
  return m ? m[1] : null;
}

function fmtDate(iso) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleDateString('en-US', {month:'short', day:'numeric'}); }
  catch { return '—'; }
}

function render(data) {
  const counts = {published:0, rendered:0, storyboard:0};
  data.forEach(p => { if (p.status in counts) counts[p.status]++; });

  document.getElementById('hcount').textContent =
    `${data.length} project${data.length !== 1 ? 's' : ''}`;

  [['sp','published'],['sr','rendered'],['ss','storyboard']].forEach(([id, s]) => {
    const el = document.getElementById(id);
    if (counts[s] > 0) { el.textContent = `${counts[s]} ${s}`; el.style.display=''; }
    else el.style.display = 'none';
  });

  const tbody = document.getElementById('tbody');
  const prevActive = activeId;
  tbody.innerHTML = '';

  data.forEach(p => {
    const canClick = p.has_video;
    const isActive = canClick && p.project_id === prevActive;
    const srcId = ytId(p.source_url);

    const tr = document.createElement('tr');
    tr.dataset.id = p.project_id;
    tr.className = canClick
      ? ('clickable' + (isActive ? ' active' : ''))
      : 'dimmed';

    tr.innerHTML = `
      <td><span class="badge s-${p.status}">● ${p.status}</span></td>
      <td style="max-width:280px">
        <div class="t-main ${p.title ? '' : 't-miss'}">${p.title || 'No title yet'}</div>
        <div class="t-id">${p.project_id}</div>
      </td>
      <td style="color:#64748b">${p.locale}${p.niche ? ' · '+p.niche : ''}</td>
      <td>${srcId
        ? `<a href="https://www.youtube.com/watch?v=${srcId}" target="_blank">${srcId} ↗</a>`
        : '<span class="nil">—</span>'}</td>
      <td>${p.youtube_video_id
        ? `<a class="yt" href="https://www.youtube.com/watch?v=${p.youtube_video_id}" target="_blank">${p.youtube_video_id} ↗</a>`
        : '<span class="nil">—</span>'}</td>
      <td style="color:#4a5568;font-size:11px">${fmtDate(p.published_at)}</td>`;

    if (canClick) tr.addEventListener('click', () => toggleDetail(p));
    tbody.appendChild(tr);

    if (isActive) tbody.appendChild(makeDetailRow(p));
  });
}

function makeDetailRow(p) {
  const dr = document.createElement('tr');
  dr.className = 'detail-row';
  dr.dataset.detailFor = p.project_id;
  const srcId = ytId(p.source_url);
  const tags = p.tags.slice(0, 5).join(', ') + (p.tags.length > 5 ? '…' : '');
  dr.innerHTML = `<td colspan="6"><div class="detail-panel">
    <video controls src="${p.final_video_url_path || ''}"></video>
    <div class="meta-grid">
      <div><span class="lbl">Title: </span>${p.title || '—'}</div>
      <div><span class="lbl">Locale: </span>${p.locale}${p.niche ? ' · '+p.niche : ''}</div>
      <div><span class="lbl">YouTube: </span>${p.youtube_video_id
        ? `<a class="yt" href="https://www.youtube.com/watch?v=${p.youtube_video_id}" target="_blank">${p.youtube_video_id} ↗</a>`
        : '—'}</div>
      <div><span class="lbl">Published: </span>${fmtDate(p.published_at)}</div>
      <div><span class="lbl">Tags: </span><span style="color:#475569">${tags || '—'}</span></div>
      <div><span class="lbl">Source: </span>${srcId
        ? `<a href="https://www.youtube.com/watch?v=${srcId}" target="_blank">${srcId} ↗</a>`
        : '—'}</div>
    </div>
  </div></td>`;
  return dr;
}

function toggleDetail(p) {
  const existing = document.querySelector(`tr[data-detail-for="${p.project_id}"]`);
  if (existing) {
    existing.remove();
    document.querySelector(`tr[data-id="${p.project_id}"]`).classList.remove('active');
    activeId = null;
    return;
  }
  // Close any open panel
  const open = document.querySelector('tr.detail-row');
  if (open) {
    const prevId = open.dataset.detailFor;
    open.remove();
    document.querySelector(`tr[data-id="${prevId}"]`)?.classList.remove('active');
  }
  // Open new panel
  const tr = document.querySelector(`tr[data-id="${p.project_id}"]`);
  tr.classList.add('active');
  tr.insertAdjacentElement('afterend', makeDetailRow(p));
  activeId = p.project_id;
}

async function refresh() {
  const ind = document.getElementById('live');
  try {
    const resp = await fetch('/api/projects');
    if (!resp.ok) throw new Error(resp.status);
    render(await resp.json());
    ind.classList.add('pulse');
    setTimeout(() => ind.classList.remove('pulse'), 500);
    ind.textContent = '↻ live';
    ind.style.color = '';
  } catch (e) {
    ind.textContent = '↻ error';
    ind.style.color = '#ef4444';
  }
}

refresh();
setInterval(refresh, 30000);
</script>
</body>
</html>
```

- [ ] **Step 2: Run all server tests — all 4 should pass now**

```bash
uv run pytest tests/unit/test_dashboard_server.py -v
```

Expected: 4/4 PASS.

- [ ] **Step 3: Commit**

```bash
git add src/pipeline/dashboard/static/index.html
git commit -m "feat(dashboard): single-file frontend with table + video preview"
```

---

## Task 5: CLI integration

**Files:**
- Modify: `src/pipeline/cli.py`

- [ ] **Step 1: Add dashboard command to cli.py**

In `src/pipeline/cli.py`, add after the existing imports at the top:

No new imports needed at the top level — they go inside the function to keep startup fast.

Add this command after the `shorts` command (before `if __name__ == "__main__":`):

```python
@app.command()
def dashboard(
    port: int = typer.Option(8765, "--port", help="Port to serve on"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Skip auto-opening browser"),
) -> None:
    """Start the read-only project monitoring dashboard."""
    import webbrowser

    import uvicorn

    from pipeline.dashboard.server import create_app

    config = PipelineConfig()
    server_app = create_app(config.OUTPUT_DIR)

    url = f"http://localhost:{port}"
    typer.echo(f"Dashboard → {url}  (Ctrl+C to stop)")

    if not no_browser:
        webbrowser.open(url)

    uvicorn.run(server_app, host="localhost", port=port, log_level="warning")
```

- [ ] **Step 2: Verify --help works**

```bash
uv run pipeline dashboard --help
```

Expected output includes:
```
Usage: pipeline dashboard [OPTIONS]
  Start the read-only project monitoring dashboard.
Options:
  --port INTEGER   Port to serve on  [default: 8765]
  --no-browser     Skip auto-opening browser
```

- [ ] **Step 3: Run existing CLI tests to verify nothing broke**

```bash
uv run pytest tests/unit/test_cli.py -v
```

Expected: all pass (same as before this change).

- [ ] **Step 4: Commit**

```bash
git add src/pipeline/cli.py
git commit -m "feat(dashboard): wire pipeline dashboard CLI command"
```

---

## Task 6: Full test suite + smoke test

**Files:** none new

- [ ] **Step 1: Run all dashboard tests**

```bash
uv run pytest tests/unit/test_dashboard_scanner.py tests/unit/test_dashboard_server.py -v
```

Expected: all 14 tests PASS.

- [ ] **Step 2: Run linter and type checker**

```bash
uv run ruff check src/pipeline/dashboard/ tests/unit/test_dashboard_scanner.py tests/unit/test_dashboard_server.py
uv run ruff format src/pipeline/dashboard/ tests/unit/test_dashboard_scanner.py tests/unit/test_dashboard_server.py
uv run mypy src/pipeline/dashboard/
```

Fix any issues before proceeding.

- [ ] **Step 3: Smoke test against real output dir**

```bash
uv run pipeline dashboard --no-browser --port 8765 &
sleep 2
curl -s http://localhost:8765/api/projects | python3 -m json.tool | head -40
kill %1
```

Expected: JSON array with 7 project objects, first entry being `1776850327_B` with `"status": "published"`.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat(dashboard): read-only project monitoring dashboard complete"
```
