# Dashboard Timeline + Draggable Sections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the broken Preview Loop panel with a proportional scene timeline (with thumbnails, visual-type color coding, and a live playhead), and make the detail-panel sections below the video player drag-to-reorder with positions cached in localStorage.

**Architecture:** Option A — minimal in-place revamp. All changes are in `index.html` (CSS + JS) and `preview.py` (add scene metadata to API response). No new files. `makeDetailRow()` is refactored to wrap each major section in a `<div class="dash-section" data-sid="...">` wrapper; a single `initSectionDrag()` function handles H5 drag events and persists order. The timeline is built synchronously from `p.scenes` and thumbnails are filled in async from the existing `/api/projects/{id}/preview-loop` endpoint.

**Tech Stack:** Vanilla JS, CSS Flexbox/Grid, HTML5 Drag and Drop API, localStorage, existing FFmpeg thumbnail pipeline.

---

## File Map

| File | Change |
|------|--------|
| `src/pipeline/dashboard/static/index.html` | CSS additions, refactor `makeDetailRow`, add `buildTimelinePanel`, `loadTimelineThumbnails`, `initSectionDrag`, update `timeupdate` listener |
| `src/pipeline/dashboard/preview.py` | Add `visual_type`, `start_sec`, `duration_sec` to scene items in `build_project_preview_manifest` |

---

### Task 1: Add CSS for dash-section wrappers and timeline rail

**Files:**
- Modify: `src/pipeline/dashboard/static/index.html` (inside the `<style>` block, after line 156)

- [ ] **Step 1: Insert new CSS rules**

Add the following CSS block immediately before the closing `</style>` tag (currently line 157):

```css
    /* ── Draggable section wrappers ── */
    .dash-sections { display: flex; flex-direction: column; gap: 0; }
    .dash-section { border: 1px solid transparent; border-radius: 4px; transition: border-color .15s; }
    .dash-section.drag-over { border-color: #3b82f6; background: #1e3a5f22; }
    .dash-section.dragging { opacity: .4; }
    .dash-section-handle { display: inline-block; cursor: grab; color: #2d3748; padding: 0 6px 0 0;
      font-size: 14px; user-select: none; vertical-align: middle; transition: color .1s; }
    .dash-section-handle:hover { color: #64748b; }
    .dash-section-handle:active { cursor: grabbing; }

    /* ── Scene Timeline ── */
    .timeline-wrap { padding: 8px 0 4px; }
    .timeline-hdr { font-size: 11px; color: #cbd5e1; font-weight: 600; margin-bottom: 6px; }
    .timeline-rail { position: relative; display: flex; height: 76px; border: 1px solid #1e293b;
      border-radius: 4px; overflow: hidden; background: #0a0f1a; cursor: pointer; }
    .timeline-seg { position: relative; overflow: hidden; flex-shrink: 0; border-right: 1px solid #0a0f1a;
      transition: filter .1s; }
    .timeline-seg:hover { filter: brightness(1.2); }
    .timeline-seg-thumb { position: absolute; inset: 0; width: 100%; height: 100%;
      object-fit: cover; opacity: .72; display: none; }
    .timeline-seg-id { position: absolute; top: 3px; left: 4px; font-family: monospace;
      font-size: 9px; color: #e2e8f0; text-shadow: 0 1px 2px rgba(0,0,0,.9); z-index: 2;
      pointer-events: none; }
    .timeline-seg-type { position: absolute; bottom: 3px; left: 4px; font-size: 8px; color: #94a3b8;
      text-shadow: 0 1px 2px rgba(0,0,0,.9); z-index: 2; text-transform: uppercase;
      letter-spacing: .04em; pointer-events: none; }
    .timeline-playhead { position: absolute; top: 0; bottom: 0; width: 2px; background: rgba(255,255,255,.85);
      pointer-events: none; z-index: 10; transition: left .1s linear; }
```

- [ ] **Step 2: Verify the style block looks right**

Open `src/pipeline/dashboard/static/index.html`, confirm the new CSS sits just before the `</style>` tag and no existing rules were accidentally removed.

- [ ] **Step 3: Commit**

```bash
git add src/pipeline/dashboard/static/index.html
git commit -m "feat(dashboard): add CSS for timeline rail and draggable section wrappers"
```

---

### Task 2: Add `buildTimelinePanel(p)` function

**Files:**
- Modify: `src/pipeline/dashboard/static/index.html` (in the `<script>` block, after `buildOutlinePanel`)

- [ ] **Step 1: Add the function after `buildOutlinePanel` (currently ends around line 475)**

Add immediately after the closing `}` of `buildOutlinePanel`:

```js
const _VTYPE_COLOR = {
  article_image:   '#1a3050',
  generated_image: '#2d1060',
  text_card:       '#103825',
  slide:           '#1c1917',
  footage:         '#5c1f08',
};
const _VTYPE_LABEL = {
  article_image:   'source img',
  generated_image: 'gen img',
  text_card:       'text card',
  slide:           'slide',
  footage:         'footage',
};

function buildTimelinePanel(p) {
  const scenes = p.scenes || [];
  if (!scenes.length) return '<div class="timeline-wrap"><div class="timeline-hdr">Timeline</div><div style="font-size:11px;color:#475569">No scenes yet.</div></div>';
  const totalDur = scenes.reduce((sum, s) => sum + (s.duration_sec || 0), 0) || 1;
  const segs = scenes.map((s, i) => {
    const pct = ((s.duration_sec || 0) / totalDur * 100).toFixed(2);
    const color = _VTYPE_COLOR[s.visual_type] || '#1a1a2e';
    const label = _VTYPE_LABEL[s.visual_type] || (s.visual_type || '');
    return `<div class="timeline-seg" data-start="${s.start_sec}" data-idx="${i}" style="width:${pct}%;background:${color}">
      <img class="timeline-seg-thumb" data-scene-id="${s.id}" alt="">
      <span class="timeline-seg-id">${escapeHtml(s.id)}</span>
      <span class="timeline-seg-type">${escapeHtml(label)}</span>
    </div>`;
  }).join('');
  return `<div class="timeline-wrap">
    <div class="timeline-hdr">Timeline <span style="font-size:9px;color:#475569;font-weight:400">${Math.round(totalDur)}s total</span></div>
    <div class="timeline-rail">
      ${segs}
      <div class="timeline-playhead" style="left:0%"></div>
    </div>
  </div>`;
}
```

- [ ] **Step 2: Verify no syntax errors by opening the dashboard in a browser**

```bash
systemctl --user status content-dashboard
# Navigate to https://dashboard.keeppro.io, open any project detail
# Check browser console for JS errors
```

Expected: no errors in console.

- [ ] **Step 3: Commit**

```bash
git add src/pipeline/dashboard/static/index.html
git commit -m "feat(dashboard): add buildTimelinePanel() with proportional scene segments"
```

---

### Task 3: Add `loadTimelineThumbnails` and `initSectionDrag` functions

**Files:**
- Modify: `src/pipeline/dashboard/static/index.html` (in the `<script>` block, after `loadPreviewLoop`)

- [ ] **Step 1: Add `loadTimelineThumbnails` after the existing `loadPreviewLoop` function (around line 617)**

```js
async function loadTimelineThumbnails(projectId, detailRow) {
  try {
    const resp = await fetch(`/api/projects/${encodeURIComponent(projectId)}/preview-loop`);
    if (!resp.ok) return;
    const data = await resp.json();
    (data.scenes || []).forEach(item => {
      const img = detailRow.querySelector(`.timeline-seg-thumb[data-scene-id="${item.id}"]`);
      if (img && item.url) {
        img.src = `${item.url}?t=${Date.now()}`;
        img.style.display = 'block';
        img.onerror = () => { img.style.display = 'none'; };
      }
    });
  } catch (_) {}
}
```

- [ ] **Step 2: Add `initSectionDrag` after `loadTimelineThumbnails`**

```js
const _SECTION_ORDER_KEY = 'dashboard-section-order-v1';

function initSectionDrag(container) {
  function saveOrder() {
    const sids = [...container.querySelectorAll(':scope > .dash-section')].map(el => el.dataset.sid);
    try { localStorage.setItem(_SECTION_ORDER_KEY, JSON.stringify(sids)); } catch (_) {}
  }

  function applyOrder() {
    let saved;
    try { saved = JSON.parse(localStorage.getItem(_SECTION_ORDER_KEY) || '[]'); } catch (_) { return; }
    if (!Array.isArray(saved) || !saved.length) return;
    saved.forEach(sid => {
      const el = container.querySelector(`:scope > .dash-section[data-sid="${sid}"]`);
      if (el) container.appendChild(el);
    });
  }

  let dragSrc = null;

  container.addEventListener('dragstart', e => {
    const handle = e.target.closest('.dash-section-handle');
    if (!handle) { e.preventDefault(); return; }
    dragSrc = handle.closest('.dash-section');
    if (!dragSrc) return;
    dragSrc.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', dragSrc.dataset.sid);
  });

  container.addEventListener('dragover', e => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    const target = e.target.closest('.dash-section');
    if (!target || target === dragSrc) return;
    container.querySelectorAll(':scope > .dash-section').forEach(s => s.classList.remove('drag-over'));
    target.classList.add('drag-over');
  });

  container.addEventListener('dragleave', e => {
    if (!container.contains(e.relatedTarget)) {
      container.querySelectorAll(':scope > .dash-section').forEach(s => s.classList.remove('drag-over'));
    }
  });

  container.addEventListener('drop', e => {
    e.preventDefault();
    const target = e.target.closest('.dash-section');
    if (!target || !dragSrc || target === dragSrc) return;
    const sections = [...container.querySelectorAll(':scope > .dash-section')];
    const srcIdx = sections.indexOf(dragSrc);
    const tgtIdx = sections.indexOf(target);
    if (srcIdx < tgtIdx) target.after(dragSrc);
    else target.before(dragSrc);
    container.querySelectorAll(':scope > .dash-section').forEach(s => s.classList.remove('drag-over'));
    saveOrder();
  });

  container.addEventListener('dragend', () => {
    if (dragSrc) dragSrc.classList.remove('dragging');
    dragSrc = null;
    container.querySelectorAll(':scope > .dash-section').forEach(s => s.classList.remove('drag-over'));
  });

  applyOrder();
}
```

- [ ] **Step 3: Verify no syntax errors**

Check browser console after loading the dashboard — no JS errors expected at this stage (functions are defined but not yet called).

- [ ] **Step 4: Commit**

```bash
git add src/pipeline/dashboard/static/index.html
git commit -m "feat(dashboard): add loadTimelineThumbnails and initSectionDrag functions"
```

---

### Task 4: Refactor `makeDetailRow` to use `dash-sections` wrappers

**Files:**
- Modify: `src/pipeline/dashboard/static/index.html` — `makeDetailRow` function (lines ~477–551)

This is the largest change. The `meta-grid` div is dissolved; contract, timeline, and meta fields each become their own `dash-section`.

- [ ] **Step 1: Replace the `makeDetailRow` function body**

Find the entire `function makeDetailRow(p) { ... }` block and replace it with:

```js
function makeDetailRow(p) {
  const dr = document.createElement('tr');
  dr.className = 'detail-row';
  dr.dataset.detailFor = p.project_id;
  const srcId = ytId(p.source_url);
  const tags = p.tags.slice(0, 5).join(', ') + (p.tags.length > 5 ? '…' : '');
  const variants = p.video_variants || [];
  const firstUrl = variants.length ? variants[0].url : '';
  const tabsHtml = variants.length > 1
    ? `<div class="variant-tabs">${variants.map((v, i) =>
        `<button class="btn-variant${i===0?' active':''}" data-url="${v.url}">${v.label}</button>`
      ).join('')}</div>`
    : '';
  const locales = p.locales && p.locales.length ? p.locales : [p.locale];
  const localeTabsHtml = locales.length > 1
    ? `<div class="locale-tabs">${locales.map((loc, i) =>
        `<button class="btn-locale${i===0?' active':''}" data-locale="${loc}">${escapeHtml(loc)}</button>`
      ).join('')}</div>`
    : '';

  function sec(id, content) {
    if (!content) return '';
    return `<div class="dash-section" data-sid="${id}" draggable="true">
      <span class="dash-section-handle" title="Drag to reorder">⠿</span>${content}
    </div>`;
  }

  const transitionAssetsHtml = renderTransitionAssets(p);

  const sessionsHtml = p.session_logs && p.session_logs.length
    ? `<div style="grid-column:1/-1;margin-top:4px"><span class="lbl">Sessions: </span>${
        p.session_logs.map(s => {
          const color = s.outcome === 'failed' ? '#ef4444' : '#6366f1';
          const tip = [s.session_id, s.command, s.summary, s.timestamp].filter(Boolean).join(' | ');
          const label = /^[0-9a-f]{8}-/.test(s.session_id) ? s.session_id.slice(0, 8) : s.session_id;
          return `<span style="font-family:monospace;font-size:11px;color:${color};margin-right:12px;cursor:default" title="${tip}">${label}</span>`;
        }).join('')
      }</div>`
    : '';

  const metaHtml = `<div class="meta-grid">
    <div><span class="lbl">Project ID: </span><span style="font-family:monospace;color:#94a3b8">${p.project_id}</span></div>
    <div><span class="lbl">Locale: </span>${p.locale}${p.niche ? ' · '+p.niche : ''}</div>
    <div><span class="lbl">Title: </span>${p.title || '—'}</div>
    <div><span class="lbl">Published: </span>${fmtDate(p.published_at)}</div>
    <div><span class="lbl">YouTube: </span>${p.youtube_video_id
      ? `<a class="yt" href="https://www.youtube.com/watch?v=${p.youtube_video_id}" target="_blank">${p.youtube_video_id} ↗</a>`
      : '—'}</div>
    <div><span class="lbl">Source: </span>${srcId
      ? `<a href="https://www.youtube.com/watch?v=${srcId}" target="_blank">${srcId} ↗</a>`
      : '—'}</div>
    <div style="grid-column:1/-1"><span class="lbl">Tags: </span><span style="color:#475569">${tags || '—'}</span></div>
    ${sessionsHtml}
    <div class="recent-mutations" style="grid-column:1/-1" data-project-id="${p.project_id}"></div>
  </div>`;

  const contractHtml = `<div class="contract-panel" data-contract-project-id="${p.project_id}" style="padding-top:8px">
    <div class="contract-title">Production Contract</div>
    <div class="contract-grid">
      ${(p.render_freshness && p.render_freshness.warnings || []).map(w =>
        `<div class="contract-item missing"><div class="ci-label">Render freshness</div><div class="ci-detail">${w}</div></div>`
      ).join('') || '<div class="contract-item partial"><div class="ci-label">Production contract</div><div class="ci-detail">Loading checks...</div></div>'}
    </div>
  </div>`;

  dr.innerHTML = `<td colspan="7"><div class="detail-panel">
    <div class="detail-actions">
      <span class="inflight-host" data-project-host data-project-id="${p.project_id}"></span>
      <button class="compose-action-btn" type="button" data-compose-action="transitions" data-project-id="${p.project_id}">Recompose transitions</button>
      <button class="compose-action-btn" type="button" data-compose-action="frame" data-project-id="${p.project_id}">Recompose frame</button>
      <button class="compose-action-btn" type="button" data-compose-action="rescene" data-project-id="${p.project_id}">Recompose selected scene</button>
      <button class="compose-action-btn" type="button" data-compose-action="reburn" data-project-id="${p.project_id}">Rebuild final only</button>
      <button class="edit-mode-toggle" type="button" data-project-id="${p.project_id}">Edit mode</button>
    </div>
    ${tabsHtml}
    ${localeTabsHtml}
    <video controls src="${firstUrl}" data-edit-token="@s1/visual"></video>
    <audio class="locale-audio" hidden></audio>
    <div class="dash-sections">
      ${p.scenes && p.scenes.length ? sec('outline', buildOutlinePanel(p)) : ''}
      ${p.scenes && p.scenes.length ? sec('scene-strip', buildSceneStrip(p)) : ''}
      ${p.scenes && p.scenes.length ? sec('timeline', buildTimelinePanel(p)) : ''}
      ${transitionAssetsHtml ? sec('transition-assets', transitionAssetsHtml) : ''}
      ${sec('contract', contractHtml)}
      ${sec('meta', metaHtml)}
    </div>
  </div></td>`;
  return dr;
}
```

- [ ] **Step 2: Remove `loadPreviewLoop` call from `toggleDetail`**

In `toggleDetail(p)`, find the two lines:
```js
  loadProductionContract(p.project_id, detailRow);
  loadPreviewLoop(p.project_id, detailRow);
```
Replace with:
```js
  loadProductionContract(p.project_id, detailRow);
  loadTimelineThumbnails(p.project_id, detailRow);
  const sectionsContainer = detailRow.querySelector('.dash-sections');
  if (sectionsContainer) initSectionDrag(sectionsContainer);
```

- [ ] **Step 3: Verify in browser**

Open the dashboard, click Preview on a project. Confirm:
- Video player appears at top
- Below it: Storyline Outline, Scene strip, Timeline, (Transition Assets if any), Production Contract, Project metadata
- Each section has a faint `⠿` handle at its left
- No JS errors in console

- [ ] **Step 4: Commit**

```bash
git add src/pipeline/dashboard/static/index.html
git commit -m "feat(dashboard): refactor makeDetailRow into draggable dash-sections"
```

---

### Task 5: Wire timeline playhead to video `timeupdate`

**Files:**
- Modify: `src/pipeline/dashboard/static/index.html` — inside `toggleDetail`, the `timeupdate` listener (around line ~740)

- [ ] **Step 1: Add playhead update inside the existing `timeupdate` listener**

Find this block inside `toggleDetail`:
```js
    vid.addEventListener('timeupdate', () => {
      const t = vid.currentTime;
      let idx = 0;
      for (let i = 0; i < p.scenes.length; i++) {
        if (t >= p.scenes[i].start_sec) idx = i;
      }
      if (idx === activeSc) return;
      activeSc = idx;
      const chips = strip.querySelectorAll('.scene-chip');
      chips.forEach((c, i) => {
        c.classList.toggle('sc-past', i < idx);
        c.classList.toggle('sc-active', i === idx);
      });
      detailRow.querySelectorAll('.outline-row').forEach(r => {
        r.classList.toggle('sc-active', +r.dataset.idx === idx);
      });
      showSceneNar(idx);
    });
```

Replace with:

```js
    const totalTimelineDur = p.scenes.reduce((sum, s) => sum + (s.duration_sec || 0), 0) || 1;

    vid.addEventListener('timeupdate', () => {
      const t = vid.currentTime;
      let idx = 0;
      for (let i = 0; i < p.scenes.length; i++) {
        if (t >= p.scenes[i].start_sec) idx = i;
      }
      // Update timeline playhead (always, not gated on idx change)
      const playhead = detailRow.querySelector('.timeline-playhead');
      if (playhead) playhead.style.left = Math.min(100, t / totalTimelineDur * 100).toFixed(2) + '%';

      if (idx === activeSc) return;
      activeSc = idx;
      const chips = strip.querySelectorAll('.scene-chip');
      chips.forEach((c, i) => {
        c.classList.toggle('sc-past', i < idx);
        c.classList.toggle('sc-active', i === idx);
      });
      detailRow.querySelectorAll('.outline-row').forEach(r => {
        r.classList.toggle('sc-active', +r.dataset.idx === idx);
      });
      showSceneNar(idx);
    });
```

- [ ] **Step 2: Wire timeline segment clicks to seek video**

After the `strip.addEventListener('click', ...)` block (around line 759), add:

```js
    const rail = detailRow.querySelector('.timeline-rail');
    if (rail && p.scenes && p.scenes.length) {
      rail.addEventListener('click', e => {
        const seg = e.target.closest('.timeline-seg');
        if (!seg) return;
        vid.currentTime = parseFloat(seg.dataset.start);
      });
    }
```

- [ ] **Step 3: Verify in browser**

Play a project video. Confirm:
- The white `timeline-playhead` line moves from left to right as the video plays
- Clicking a timeline segment seeks the video to that scene's start time
- The active scene chip in the scene strip still updates correctly

- [ ] **Step 4: Commit**

```bash
git add src/pipeline/dashboard/static/index.html
git commit -m "feat(dashboard): wire timeline playhead to video currentTime + click-to-seek"
```

---

### Task 6: Test drag-and-drop reorder and localStorage persistence

**Files:**
- No code changes — verification only.

- [ ] **Step 1: Test reordering**

Open the dashboard, expand a project detail panel. Grab the `⠿` handle on the "Timeline" section and drag it above "Storyline outline". Confirm:
- The section visually moves
- No JS errors in console
- The new order is reflected immediately

- [ ] **Step 2: Test persistence**

After reordering, close and reopen the detail panel (click Preview again). Confirm the sections appear in the saved order (Timeline above Storyline Outline).

- [ ] **Step 3: Test across projects**

Open a different project's detail panel. Confirm it also respects the same saved order (order is global, not per-project).

- [ ] **Step 4: Test localStorage reset**

In browser devtools console, run:
```js
localStorage.removeItem('dashboard-section-order-v1'); location.reload();
```
Confirm sections return to default order (Outline → Scene Strip → Timeline → Transition Assets → Contract → Meta).

---

### Task 7: Extend preview-loop API to include scene metadata (optional enhancement)

**Files:**
- Modify: `src/pipeline/dashboard/preview.py` — `build_project_preview_manifest` (line ~85)

This adds `visual_type`, `start_sec`, `duration_sec` to the scene items returned by the API. Not required for the timeline to work (the JS already has `p.scenes`), but useful if other consumers query the endpoint.

- [ ] **Step 1: Load scenes.json alongside storyboard in `build_project_preview_manifest`**

Find the function `build_project_preview_manifest` and update the scene-building loop:

```python
def build_project_preview_manifest(project_root: Path) -> dict[str, list[dict[str, str]]]:
    storyboard_path = project_root / "storyboard.json"
    if not storyboard_path.exists():
        return {"scenes": [], "transitions": []}

    storyboard = Storyboard.load(storyboard_path)
    frame_style = storyboard.theme.frame_style or ""
    frame_suffix = f"_{frame_style}" if frame_style else ""
    scenes_dir = project_root / "compose" / "scenes"
    previews_dir = project_root / "compose" / "previews"

    # Build a lookup of rendered scene start/duration from scenes.json if available
    import json, contextlib
    scene_timing: dict[str, dict] = {}
    scenes_json = project_root / "compose" / "scenes.json"
    with contextlib.suppress(Exception):
        raw = json.loads(scenes_json.read_text(encoding="utf-8"))
        for s in raw:
            if isinstance(s, dict) and s.get("id"):
                scene_timing[str(s["id"])] = {
                    "start_sec": float(s.get("start_sec", 0)),
                    "duration_sec": float(s.get("duration_sec", 0)),
                }

    scene_items: list[dict[str, str]] = []
    for scene in storyboard.scenes:
        scene_video = scenes_dir / f"{scene.id}_final_no_overlay{frame_suffix}.mp4"
        if not scene_video.exists():
            scene_video = scenes_dir / f"{scene.id}_final{frame_suffix}.mp4"
        if not scene_video.exists():
            continue
        preview_path = previews_dir / "scenes" / f"{scene.id}.jpg"
        ensure_scene_preview(scene_video, preview_path)
        visual_type = ""
        if hasattr(scene, "visual") and scene.visual:
            visual_type = getattr(scene.visual, "type", "") or ""
        timing = scene_timing.get(str(scene.id), {})
        scene_items.append({
            "id": scene.id,
            "label": f"{scene.id} · {scene.section}",
            "path": preview_path.relative_to(project_root).as_posix(),
            "visual_type": visual_type,
            "start_sec": str(timing.get("start_sec", 0)),
            "duration_sec": str(timing.get("duration_sec", 0)),
        })
    # ... rest of function unchanged (transition_items, intro_item) ...
```

- [ ] **Step 2: Run existing tests to confirm no regressions**

```bash
cd /home/tim-huang/content-creation
uv run pytest tests/ -q
```

Expected: all previously passing tests still pass.

- [ ] **Step 3: Commit**

```bash
git add src/pipeline/dashboard/preview.py
git commit -m "feat(dashboard): add visual_type + timing to preview-loop scene items"
```

---

## Self-Review

**Spec coverage:**
- ✅ Q1 answered (Preview Loop documented as post-render visual QC; expected to be empty pre-render)
- ✅ Q2: Timeline with proportional segments, visual-type color coding, thumbnail images, playhead, click-to-seek
- ✅ Q3: Sections below video are draggable via `⠿` handle; order cached in `localStorage`

**Placeholder scan:** No TBDs. All code blocks are complete.

**Type consistency:**
- `buildTimelinePanel(p)` → called in `makeDetailRow(p)` ✅
- `loadTimelineThumbnails(projectId, detailRow)` → called in `toggleDetail` ✅
- `initSectionDrag(sectionsContainer)` → called in `toggleDetail` after building `dr` ✅
- `sec(id, content)` → local helper inside `makeDetailRow`, not exposed globally ✅
- `_SECTION_ORDER_KEY` → used by `initSectionDrag` ✅
- `.dash-section[data-sid]` → read by `initSectionDrag`, written by `sec()` ✅
- `.timeline-playhead` → written by `buildTimelinePanel`, read by `timeupdate` listener ✅
- `.timeline-seg-thumb[data-scene-id]` → written by `buildTimelinePanel`, read by `loadTimelineThumbnails` ✅
- `loadProductionContract` call is preserved in `toggleDetail` ✅
- `data-contract-project-id` attribute preserved in contract HTML ✅
- `.recent-mutations[data-project-id]` preserved in meta HTML ✅
